"""Model adapter. The runtime talks to this small interface so tests can use a
scripted fake and the Gemini specifics stay in one place.

Gemini function calling (manual mode): https://ai.google.dev/gemini-api/docs/function-calling
The model only *requests* function calls; the runtime validates and executes them,
then returns results as function_response parts. We append the model's original
candidate content to history unchanged so thought signatures are preserved.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from tools.base import Tool


@dataclass
class FunctionCall:
    name: str
    args: dict[str, Any]
    id: str | None = None


@dataclass
class LLMTurn:
    text: str
    calls: list[FunctionCall] = field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    raw: Any = None  # provider-specific content to replay in history
    model: str | None = None  # model that actually answered (may be a fallback)
    attempts: list[str] = field(default_factory=list)  # e.g. ["gemini-3.8-flash: 503 (1.9s)", ...]


# History items:
#   {"role": "user", "text": str}
#   {"role": "model", "turn": LLMTurn}
#   {"role": "tool", "results": list[tuple[FunctionCall, dict]]}
History = list[dict[str, Any]]


class LLM(Protocol):
    def generate(self, model: str, system: str, history: History, tools: list[Tool]) -> LLMTurn: ...


class LLMError(Exception):
    """Model call failed; message is safe to show."""


# gemini-2.5-flash returns 404 "no longer available to new users" (Oct 2026); run tools.check_keys --write.
DEFAULT_MODEL = os.getenv("GEMINI_MODEL") or "gemini-3.8-flash"
# A Gemini call with no timeout hung a live CLI run for minutes; fail the step instead.
LLM_TIMEOUT_S = float(os.getenv("GEMINI_TIMEOUT_S") or 60)
FALLBACK_MODELS = [m.strip() for m in (os.getenv("GEMINI_FALLBACK_MODELS") or "gemini-3.8-flash,gemini-3.7-flash,gemini-3.5-flash").split(",") if m.strip()]
RETRY_DELAY_S = 1.5
# Live 5:20 PM: 3.5 and 3.7 both 503'd within seconds and the run failed; spikes are short, so one more round.
SECOND_ROUND_DELAY_S = 4.0
# Live 5:25 PM: 429 "exceeded your current quota" on all three models. A per-minute limit says when to come back
# (retryDelay); wait that long once if it's short. A per-day limit won't recover today: skip that model.
MAX_QUOTA_WAIT_S = float(os.getenv("GEMINI_MAX_QUOTA_WAIT_S") or 35)


def _quota(e: Exception) -> tuple[str | None, float | None]:
    """(quotaId, retryDelay seconds) from a Gemini 429, if present."""
    text = str(e) + " " + str(getattr(e, "details", "") or "")
    q = re.search(r"quotaId['\"]?\s*:\s*['\"]([\w-]+)", text)
    d = re.search(r"retryDelay['\"]?\s*:\s*['\"](\d+(?:\.\d+)?)s", text)
    return (q.group(1) if q else None), (float(d.group(1)) if d else None)


def _overloaded(e: Exception) -> bool:
    """503 UNAVAILABLE / 429 RESOURCE_EXHAUSTED: worth retrying or switching model; anything else isn't."""
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    text = str(e)
    return code in (429, 503) or "UNAVAILABLE" in text or "RESOURCE_EXHAUSTED" in text


class GeminiLLM:
    def __init__(self, api_key: str | None = None):
        from google import genai  # imported lazily so tests don't need credentials

        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise LLMError("GEMINI_API_KEY is not set")
        from google.genai import types

        self._sleep = time.sleep
        self._client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=int(LLM_TIMEOUT_S * 1000)))

    def generate(self, model: str, system: str, history: History, tools: list[Tool]) -> LLMTurn:
        from google.genai import types

        contents: list[types.Content] = []
        for item in history:
            if item["role"] == "user":
                contents.append(types.Content(role="user", parts=[types.Part(text=item["text"])]))
            elif item["role"] == "model":
                turn: LLMTurn = item["turn"]
                if turn.raw is not None:
                    contents.append(turn.raw)
                else:
                    parts = [types.Part(text=turn.text)] if turn.text else []
                    parts += [types.Part(function_call=types.FunctionCall(id=c.id, name=c.name, args=c.args)) for c in turn.calls]
                    contents.append(types.Content(role="model", parts=parts))
            elif item["role"] == "tool":
                contents.append(types.Content(role="user", parts=[
                    types.Part(function_response=types.FunctionResponse(id=c.id, name=c.name, response=resp))
                    for c, resp in item["results"]
                ]))

        decls = []
        for t in tools:
            d: dict[str, Any] = {"name": t.name, "description": t.description}
            if t.parameters.get("properties"):
                d["parameters_json_schema"] = t.parameters
            decls.append(types.FunctionDeclaration(**d))

        def config_for(m: str) -> types.GenerateContentConfig:
            return types.GenerateContentConfig(
                system_instruction=system,
                tools=[types.Tool(function_declarations=decls)] if decls else None,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                temperature=0.2,
                # Gemini 3 models think by default; "low" keeps tool-calling turns fast.
                thinking_config=types.ThinkingConfig(thinking_level="low") if m.startswith("gemini-3") else None,
            )

        # Live runs hit 503 "high demand" on the newest Flash: retry once, then try the fallback models.
        candidates = [model] + [m for m in FALLBACK_MODELS if m != model]
        last: Exception | None = None
        resp = None
        used = model
        attempts: list[str] = []
        daily_out: set[str] = set()  # models whose per-day quota is spent
        quota_ids: dict[str, str] = {}
        wait_s: float | None = None  # shortest per-minute retryDelay seen
        for i, m in enumerate(candidates + candidates):
            if i == len(candidates):
                if wait_s is not None and wait_s > MAX_QUOTA_WAIT_S:
                    break
                self._sleep(max(SECOND_ROUND_DELAY_S, wait_s or 0))
            if m in daily_out:
                continue
            for attempt in range(2 if i < len(candidates) else 1):
                t0 = time.perf_counter()
                try:
                    resp = self._client.models.generate_content(model=m, contents=contents, config=config_for(m))
                    used = m
                    break
                except Exception as e:  # SDK raises various errors; keep internals out of user-facing text
                    code = getattr(e, "code", None) or type(e).__name__
                    attempts.append(f"{m}: {code} ({time.perf_counter() - t0:.1f}s)")
                    if "timeout" in type(e).__name__.lower() or "timed out" in str(e).lower():
                        raise LLMError(f"Gemini did not answer within {LLM_TIMEOUT_S:.0f}s") from e
                    last = e
                    if not _overloaded(e):
                        raise LLMError(f"Gemini request failed ({type(e).__name__}: {str(e)[:200]})") from e
                    qid, delay = _quota(e)
                    if qid:
                        quota_ids[m] = qid
                        if "PerDay" in qid:
                            daily_out.add(m)
                            break
                    if delay is not None:  # rate-limited: retrying now just burns another request
                        wait_s = delay if wait_s is None else min(wait_s, delay)
                        break
                    if attempt == 0:
                        self._sleep(RETRY_DELAY_S)
            if resp is not None:
                break
        if resp is None:
            if quota_ids:
                which = "; ".join(f"{m}: {q}" for m, q in quota_ids.items())
                when = f" Per-minute limit: retry in {wait_s:.0f}s." if wait_s is not None else ""
                raise LLMError(f"Gemini quota exceeded ({which}).{when}") from last
            raise LLMError(f"Gemini is overloaded; tried {', '.join(candidates)} ({str(last)[:120]})") from last

        cand = (resp.candidates or [None])[0]
        content = cand.content if cand else None
        text = "".join(p.text for p in (content.parts or []) if getattr(p, "text", None) and not getattr(p, "thought", False)) if content else ""
        calls = [FunctionCall(name=fc.name, args=dict(fc.args or {}), id=fc.id) for fc in (resp.function_calls or [])]
        um = resp.usage_metadata
        out_tokens = None
        if um and um.candidates_token_count is not None:
            out_tokens = (um.candidates_token_count or 0) + (um.thoughts_token_count or 0)
        return LLMTurn(
            text=text,
            calls=calls,
            input_tokens=um.prompt_token_count if um else None,
            output_tokens=out_tokens,
            raw=content,
            model=used,
            attempts=attempts,
        )
