"""Agent runtime: load config → Gemini function-calling loop → verify → result.

    response = run_agent(agent, message, session_id, hooks)

Never raises for model/tool problems: returns status="failed" with a user-safe
error and still calls hooks.on_run_finish so failures show on the dashboard.
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any, Protocol

from server.schemas import AgentConfig, ChatResponse, RunStep, Usage
from tools.base import Tool, ToolRegistry, ToolResult
from tools.registry import registry as default_registry

from .llm import LLM, FunctionCall, GeminiLLM, LLMError, LLMTurn
from .receipt import chain as receipt_chain
from .receipt import data_hash
from .verify import USER_SOURCE, explain_figures, mark_user_figures, verify_answer

RUN_TIMEOUT_S = float(os.getenv("RUN_TIMEOUT_S", "90"))
# Self-correction: when the model states figures no tool returned, send them back once to be sourced or removed.
# One extra model call, only when something was made up. FACT_CHECK_REPAIR=0 turns it off.
REPAIR_ENABLED = os.getenv("FACT_CHECK_REPAIR", "1") != "0"
REPAIR_MIN_S = 25.0  # don't start a correction this close to the run timeout


def repair_request(invented) -> str:
    lines = "\n".join(f'- {c.text} in "{c.context[:160]}"' for c in invented)
    return (
        "Fact-check before your answer is shown: these figures don't appear in any tool result from this conversation:\n"
        f"{lines}\n\n"
        "Rewrite your complete answer. For each figure: if one of your tools can provide it, call the tool and use the "
        "exact value it returns; otherwise remove the figure or say you couldn't verify it. Don't introduce figures no "
        "tool returned. Keep figures the user gave you, attributed to them. Reply with the full corrected answer only."
    )


class RunHooks(Protocol):
    def on_run_start(self, run_id: str, agent_id: str, session_id: str | None, user_message: str) -> None: ...
    def on_step(self, step: RunStep) -> None: ...
    def on_run_finish(self, response: ChatResponse) -> None: ...


class InMemoryHooks:
    """Default hooks for CLI/tests. Person 2 replaces with DB-backed hooks."""

    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}
        self.steps: list[RunStep] = []

    def on_run_start(self, run_id, agent_id, session_id, user_message):
        self.runs[run_id] = {"agent_id": agent_id, "session_id": session_id, "user_message": user_message, "status": "running"}

    def on_step(self, step):
        self.steps.append(step)

    def on_run_finish(self, response):
        self.runs[response.run_id].update(status=response.status, response=response)


_default_llm: LLM | None = None


def _get_llm() -> LLM:
    global _default_llm
    if _default_llm is None:
        _default_llm = GeminiLLM()
    return _default_llm


def build_system_prompt(agent: AgentConfig, tools: list[Tool]) -> str:
    g = agent.guardrails
    rules = [
        "Only state facts, prices, totals and dates that appear in tool results from this conversation. "
        "If you don't have the data, say so instead of guessing.",
        "If the user gives you a figure (e.g. a price someone quoted them), you may use it in your answer and math, "
        "but attribute it to the user ('the $X you mentioned') and say whether your tools confirm it. "
        "If your tools found a different or better price, give that verified price and the saving from it too.",
        "When you compare prices or compute a difference, show both original figures so the math can be checked.",
        "Label estimates as estimates. Cite sources with the URLs the tools returned.",
        "Tool results have data_mode 'live' or 'cached' (both are real data from the API; cached is just a recent copy, "
        "don't mention it) or 'fixture' (demo data: only then say the answer uses demo data).",
        "If a tool fails, say what you couldn't check and continue with what you have.",
        "You are not a financial adviser; frame suggestions as information, not advice.",
    ]
    if g.read_only_financial_data:
        rules.append("Financial data is read-only. Never offer to move money, pay bills or change accounts.")
    if g.require_confirmation_for_external_actions:
        rules.append("Never take or promise any external action; only report findings.")
    tool_list = "\n".join(f"- {t.name}: {t.label} ({t.source})" for t in tools) or "- (no tools enabled)"
    return (
        f"You are '{agent.name}', an agent deployed on Agent Forge.\n\n"
        f"## Your instructions\n{agent.instructions.strip()}\n\n"
        f"## Tools enabled for you\n{tool_list}\n\n"
        "## Platform rules (always apply)\n" + "\n".join(f"- {r}" for r in rules) +
        "\n\nFormat answers in short Markdown sections or lists."
    )


def _safe(fn, *args):
    """Receipts are best-effort: odd data (e.g. NaN) skips the receipt instead of failing the run."""
    try:
        return fn(*args)
    except Exception:
        return None


def _preview(data: Any) -> Any:
    """Small, safe preview of search results for the run trace (no bank data)."""
    if not isinstance(data, dict):
        return None
    for key, fields in (
        ("products", ("title", "price", "merchant", "url")),
        ("stories", ("title", "source", "published", "url")),
        ("results", ("title", "url")),
        ("places", ("name", "address", "rating")),
    ):
        if isinstance(data.get(key), list):
            return [{f: item.get(f) for f in fields} for item in data[key][:3]]
    return None


def run_agent(
    agent: AgentConfig,
    message: str,
    session_id: str | None = None,
    hooks: RunHooks | None = None,
    llm: LLM | None = None,
    registry: ToolRegistry = default_registry,
) -> ChatResponse:
    hooks = hooks or InMemoryHooks()
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    started = time.perf_counter()
    steps: list[RunStep] = []
    tool_outputs: list[tuple[int, str, Any]] = []
    modes: set[str] = set()
    in_tokens = out_tokens = 0
    tokens_known = False

    hooks.on_run_start(run_id, agent.id, session_id, message)

    def add_step(**kw: Any) -> RunStep:
        s = RunStep(run_id=run_id, agent_id=agent.id, step=len(steps) + 1, **kw)
        steps.append(s)
        try:
            hooks.on_step(s)
        except Exception:
            pass  # logging must never break a run
        return s

    def finish(status: str, answer: str, error: str | None = None, claims=None, blocked=False) -> ChatResponse:
        resp = ChatResponse(
            run_id=run_id,
            assistant_message=answer,
            status=status,  # type: ignore[arg-type]
            usage=Usage(input_tokens=in_tokens if tokens_known else None, output_tokens=out_tokens if tokens_known else None),
            total_latency_ms=int((time.perf_counter() - started) * 1000),
            steps=steps,
            claims=claims or [],
            blocked=blocked,
            data_modes=sorted(modes),  # type: ignore[arg-type]
            error=error,
        )
        try:
            hooks.on_run_finish(resp)
        except Exception:
            pass
        return resp

    if agent.status != "deployed":
        return finish("failed", "", error="This agent isn't deployed yet.")

    # Only registered tools that are enabled for this agent are offered or executable.
    enabled: dict[str, tuple[Tool, dict[str, Any]]] = {}
    for tc in agent.tools:
        tool = registry.get(tc.name)
        if tool:
            enabled[tc.name] = (tool, tc.settings)
    tools = [t for t, _ in enabled.values()]

    try:
        model_client = llm or _get_llm()
    except LLMError as e:
        return finish("failed", "", error=f"The AI model isn't configured ({e}).")

    system = build_system_prompt(agent, tools)
    history: list[dict[str, Any]] = [{"role": "user", "text": message}]
    max_calls = max(0, agent.guardrails.max_tool_calls)
    tool_calls = 0

    def agent_loop() -> tuple[LLMTurn | None, str | None]:
        """Model/tool loop until a final answer. Returns (final turn, None) or (None, user-safe error)."""
        nonlocal tool_calls, in_tokens, out_tokens, tokens_known
        for _turn in range(max_calls + 3):
            if time.perf_counter() - started > RUN_TIMEOUT_S:
                return None, "The agent took too long and was stopped."

            offer = tools if tool_calls < max_calls else []  # at the limit, force a final answer
            t0 = time.perf_counter()
            try:
                turn: LLMTurn = model_client.generate(agent.model, system, history, offer)
            except LLMError as e:
                add_step(type="llm", input={"tools_offered": len(offer)}, ms=int((time.perf_counter() - t0) * 1000),
                         success=False, error=str(e)[:300])
                return None, "The AI model request failed. Please try again."
            if turn.input_tokens is not None or turn.output_tokens is not None:
                tokens_known = True
                in_tokens += turn.input_tokens or 0
                out_tokens += turn.output_tokens or 0
            add_step(
                type="llm",
                input={"tools_offered": len(offer), "history_items": len(history)},
                output={
                    **({"function_calls": [c.name for c in turn.calls]} if turn.calls else {"final_answer_chars": len(turn.text)}),
                    **({"model": turn.model} if turn.model else {}),
                    **({"retries": turn.attempts} if turn.attempts else {}),
                },
                ms=int((time.perf_counter() - t0) * 1000),
                tokens=((turn.input_tokens or 0) + (turn.output_tokens or 0)) if turn.input_tokens is not None else None,
                input_tokens=turn.input_tokens,
                output_tokens=turn.output_tokens,
            )

            if not turn.calls:
                return turn, None

            history.append({"role": "model", "turn": turn})
            results: list[tuple[FunctionCall, dict[str, Any]]] = []
            for call in turn.calls:
                if call.name not in enabled:
                    err = f"Tool '{call.name}' is not enabled for this agent."
                    add_step(type="tool", tool_name=call.name, input=call.args, output={"summary": "rejected"},
                             ms=0, success=False, error=err)
                    results.append((call, {"ok": False, "error": err}))
                    continue
                if tool_calls >= max_calls:
                    err = "Tool-call limit reached. Answer with the data you already have."
                    add_step(type="tool", tool_name=call.name, input=call.args, output={"summary": "skipped: limit"},
                             ms=0, success=False, error=err)
                    results.append((call, {"ok": False, "error": err}))
                    continue
                tool, settings = enabled[call.name]
                res: ToolResult = tool.run(call.args or {}, settings)
                tool_calls += 1
                s = add_step(
                    type="tool",
                    tool_name=call.name,
                    input=call.args,
                    output={"summary": tool.summarize(res), "mode": res.mode if res.ok else None, "preview": _preview(res.data),
                        # fingerprint of the full raw tool data (not stored); covered by the run's receipt
                        **({"data_sha256": _safe(data_hash, res.data)} if res.ok else {})},
                    ms=res.duration_ms,
                    success=res.ok,
                    cached=res.cached,
                    fixture=res.fixture,
                    error=res.error,
                )
                if res.ok:
                    modes.add(res.mode)
                    tool_outputs.append((s.step, call.name, res.data))
                    results.append((call, {"ok": True, "data_mode": res.mode, "real_data": not res.fixture, "data": res.data}))
                else:
                    results.append((call, {"ok": False, "error": res.error}))
            history.append({"role": "tool", "results": results})
        return None, "The agent didn't reach an answer within its limits."

    final_turn, err = agent_loop()
    if err:
        return finish("failed", "", error=err)
    final_text = final_turn.text.strip() if final_turn else ""
    if not final_text:
        return finish("failed", "", error="The model returned an empty answer.")

    mode = agent.guardrails.fact_check
    if mode == "off":
        return finish("completed", final_text)

    def check(text: str):
        _, cl, _ = verify_answer(text, tool_outputs, "flag")
        mark_user_figures(cl, message)
        return cl, [c for c in cl if not c.verified and c.source_tool != USER_SOURCE]

    # 1) Check the draft. 2) If the model stated figures no tool returned, send them back once to be sourced or
    # removed (self-correction), and keep the corrected answer if it is no worse. 3) Apply flag/block to the result
    # and record it in ONE final verify step, with the figure list and the audit receipt. Steps are persisted as they
    # are added (hooks.on_step), so nothing may be changed after add_step or the stored record won't match.
    t0 = time.perf_counter()
    claims, invented = check(final_text)
    attempt = bool(invented) and REPAIR_ENABLED and time.perf_counter() - started < RUN_TIMEOUT_S - REPAIR_MIN_S
    chosen, stage, correction = final_text, "final", {}
    if attempt:
        add_step(
            type="verify",
            input={"mode": mode, "stage": "draft"},
            output={
                "claims": len(claims), "verified": sum(c.verified for c in claims),
                "unverified": [c.text for c in claims if not c.verified], "blocked": False,
                "invented": [c.text for c in invented], "user_supplied": [c.text for c in claims if c.source_tool == USER_SOURCE],
                "draft": final_text, "correcting": True,
            },
            ms=int((time.perf_counter() - t0) * 1000),
        )
        history.append({"role": "model", "turn": final_turn})
        history.append({"role": "user", "text": repair_request(invented)})
        try:
            fixed_turn, _ = agent_loop()
        except Exception:  # a failed correction must never cost the user the answer they already have
            fixed_turn = None
        fixed_text = fixed_turn.text.strip() if fixed_turn else ""
        if fixed_text:
            t0 = time.perf_counter()
            _, invented2 = check(fixed_text)
            kept = len(invented2) <= len(invented)
            if kept:
                chosen = fixed_text
            stage = "corrected"
            correction = {"fixed": sorted({c.text for c in invented} - {c.text for c in invented2}), "used_correction": kept}

    answer, claims, blocked = verify_answer(chosen, tool_outputs, mode)
    mark_user_figures(claims, message)
    _, left = check(chosen)
    out = {
        "claims": len(claims), "verified": sum(c.verified for c in claims),
        "unverified": [c.text for c in claims if not c.verified], "blocked": blocked,
        "invented": [c.text for c in left], "user_supplied": [c.text for c in claims if c.source_tool == USER_SOURCE],
        **correction,
        # The per-figure result and its evidence (the record it matched, or the two figures it came from),
        # stored with the run and covered by the receipt.
        "figures": [[c.text, c.verified, c.source_tool, c.source_step, c.how, d]
                    for c, d in zip(claims, _safe(explain_figures, chosen, tool_outputs) or [None] * len(claims))],
    }
    record = {"step": len(steps) + 1, "type": "verify", "tool_name": None, "input": {"mode": mode, "stage": stage},
              "output": out, "success": True, "error": None}
    rc = _safe(receipt_chain, run_id, agent.id, message, [s.model_dump() for s in steps] + [record], answer)
    if rc is not None:  # a receipt must never cost the user their answer
        out["receipt"] = rc
    add_step(type="verify", input=record["input"], output=out, ms=int((time.perf_counter() - t0) * 1000))
    return finish("completed", answer, claims=claims, blocked=blocked)
