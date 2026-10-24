"""Model adapter. The runtime talks to this small interface so tests can use a
scripted fake and the Gemini specifics stay in one place.

Gemini function calling (manual mode): https://ai.google.dev/gemini-api/docs/function-calling
The model only *requests* function calls; the runtime validates and executes them,
then returns results as function_response parts. We append the model's original
candidate content to history unchanged so thought signatures are preserved.
"""

from __future__ import annotations

import os
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


# History items:
#   {"role": "user", "text": str}
#   {"role": "model", "turn": LLMTurn}
#   {"role": "tool", "results": list[tuple[FunctionCall, dict]]}
History = list[dict[str, Any]]


class LLM(Protocol):
    def generate(self, model: str, system: str, history: History, tools: list[Tool]) -> LLMTurn: ...


class LLMError(Exception):
    """Model call failed; message is safe to show."""


DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


class GeminiLLM:
    def __init__(self, api_key: str | None = None):
        from google import genai  # imported lazily so tests don't need credentials

        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise LLMError("GEMINI_API_KEY is not set")
        self._client = genai.Client(api_key=key)

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

        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=[types.Tool(function_declarations=decls)] if decls else None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            temperature=0.2,
        )
        try:
            resp = self._client.models.generate_content(model=model, contents=contents, config=config)
        except Exception as e:  # SDK raises various errors; keep internals out of user-facing text
            raise LLMError(f"Gemini request failed ({type(e).__name__}: {str(e)[:200]})") from e

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
        )
