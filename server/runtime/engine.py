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
from .verify import verify_answer

RUN_TIMEOUT_S = float(os.getenv("RUN_TIMEOUT_S", "90"))


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
    final_text = ""

    for _turn in range(max_calls + 3):
        if time.perf_counter() - started > RUN_TIMEOUT_S:
            return finish("failed", "", error="The agent took too long and was stopped.")

        offer = tools if tool_calls < max_calls else []  # at the limit, force a final answer
        t0 = time.perf_counter()
        try:
            turn: LLMTurn = model_client.generate(agent.model, system, history, offer)
        except LLMError as e:
            add_step(type="llm", input={"tools_offered": len(offer)}, ms=int((time.perf_counter() - t0) * 1000),
                     success=False, error=str(e)[:300])
            return finish("failed", "", error="The AI model request failed. Please try again.")
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
            final_text = turn.text.strip()
            break

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
                output={"summary": tool.summarize(res), "mode": res.mode if res.ok else None, "preview": _preview(res.data)},
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
    else:
        return finish("failed", "", error="The agent didn't reach an answer within its limits.")

    if not final_text:
        return finish("failed", "", error="The model returned an empty answer.")

    t0 = time.perf_counter()
    answer, claims, blocked = verify_answer(final_text, tool_outputs, agent.guardrails.fact_check)
    if agent.guardrails.fact_check != "off":
        unverified = [c.text for c in claims if not c.verified]
        add_step(
            type="verify",
            input={"mode": agent.guardrails.fact_check},
            output={"claims": len(claims), "verified": len(claims) - len(unverified), "unverified": unverified, "blocked": blocked},
            ms=int((time.perf_counter() - t0) * 1000),
        )
    return finish("completed", answer, claims=claims, blocked=blocked)
