"""Shared tool interface, result format and registry (Person 1).

Every tool has the same shape (docs/PLAN.md §3B):
    name, description, settingsSchema, run(input, settings) -> ToolResult

`parameters` is the JSON schema Gemini sees for the tool's *input*.
`settings_schema` describes per-agent configuration (e.g. customer_id, location)
that the builder UI edits and that is never chosen by the model.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

JsonSchema = dict[str, Any]


@dataclass
class ToolResult:
    ok: bool
    data: Any = None
    source: str = ""  # e.g. "serpapi:google_shopping", "nessie"
    cached: bool = False
    fixture: bool = False  # True when data came from local demo fixtures, never from the live API
    duration_ms: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "data": self.data,
            "source": self.source,
            "cached": self.cached,
            "fixture": self.fixture,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }

    @property
    def mode(self) -> str:
        """How to label this result in the UI: live, cached or fixture."""
        if self.fixture:
            return "fixture"
        return "cached" if self.cached else "live"


class ToolError(Exception):
    """Safe, user-displayable tool failure (no secrets in the message)."""


@dataclass
class Tool:
    name: str
    label: str  # shown on builder tool cards
    source: str  # which API powers it, shown on cards + dashboard
    description: str  # read by Gemini to decide when to call it
    parameters: JsonSchema
    run_fn: Callable[[dict[str, Any], dict[str, Any]], tuple[Any, bool, bool]]
    """run_fn(input, settings) -> (data, cached, fixture). Raise ToolError on failure."""
    settings_schema: JsonSchema = field(default_factory=lambda: {"type": "object", "properties": {}})
    category: str = "data"
    summarize_fn: Callable[[Any], str] | None = None
    """One-line, safe summary of a successful result for run steps / UI."""

    def summarize(self, result: "ToolResult") -> str:
        if not result.ok:
            return f"failed: {result.error}"
        if self.summarize_fn:
            try:
                return self.summarize_fn(result.data)
            except Exception:
                pass
        return "ok"

    def run(self, input: dict[str, Any], settings: dict[str, Any] | None = None) -> ToolResult:
        settings = settings or {}
        start = time.perf_counter()
        try:
            validate(input, self.parameters, what="input")
            validate(settings, self.settings_schema, what="settings")
            data, cached, fixture = self.run_fn(input, settings)
            return ToolResult(
                ok=True, data=data, source=self.source, cached=cached, fixture=fixture,
                duration_ms=_ms(start),
            )
        except ToolError as e:
            return ToolResult(ok=False, source=self.source, duration_ms=_ms(start), error=str(e))
        except Exception as e:  # never leak internals/secrets to the model or UI
            return ToolResult(
                ok=False, source=self.source, duration_ms=_ms(start),
                error=f"{self.name} failed ({type(e).__name__})",
            )

    def metadata(self) -> dict[str, Any]:
        """Shape returned by GET /api/tools."""
        return {
            "name": self.name,
            "label": self.label,
            "source": self.source,
            "category": self.category,
            "description": self.description,
            "parameters": self.parameters,
            "settingsSchema": self.settings_schema,
        }


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
}


def validate(value: Any, schema: JsonSchema, what: str = "value") -> None:
    """Minimal JSON-schema check: object, required keys, property types, enums.
    Unknown keys are rejected so the model can't smuggle extra arguments."""
    if not isinstance(value, dict):
        raise ToolError(f"{what} must be an object")
    props: dict[str, Any] = schema.get("properties", {})
    for key in schema.get("required", []):
        if key not in value or value[key] in (None, ""):
            raise ToolError(f"missing required {what} '{key}'")
    for key, v in value.items():
        if key not in props:
            raise ToolError(f"unknown {what} '{key}'")
        expected = props[key].get("type")
        if expected and v is not None:
            ok_types = _TYPES.get(expected, (object,))
            if isinstance(v, bool) and expected in ("integer", "number"):
                raise ToolError(f"{what} '{key}' must be {expected}")
            if not isinstance(v, ok_types):
                raise ToolError(f"{what} '{key}' must be {expected}")
        if "enum" in props[key] and v not in props[key]["enum"]:
            raise ToolError(f"{what} '{key}' must be one of {props[key]['enum']}")


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        if tool.name in self._tools:
            raise ValueError(f"duplicate tool {tool.name}")
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def list_metadata(self) -> list[dict[str, Any]]:
        return [t.metadata() for t in self._tools.values()]
