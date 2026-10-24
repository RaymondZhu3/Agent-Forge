"""Shared contracts — the ONE canonical definition (docs/PLAN.md §3).

FROZEN: change only with team agreement, and update web/src/types.ts and
docs/API.md in the same commit.

JSON field names follow docs/PLAN.md exactly: run steps use camelCase
(runId, toolName, ...), everything else uses snake_case.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

# ---------- Agent configuration (§3A) ----------


class ToolConfig(BaseModel):
    name: str  # must exist in the tool registry (GET /api/tools)
    settings: dict[str, Any] = Field(default_factory=dict)  # validated against the tool's settingsSchema


class Guardrails(BaseModel):
    read_only_financial_data: bool = True
    max_tool_calls: int = 8
    require_confirmation_for_external_actions: bool = True
    # Trust feature: check numbers in the final answer against tool outputs.
    # "flag" = send answer, mark unverified claims; "block" = redact unverified figures; "off" = skip.
    fact_check: Literal["flag", "block", "off"] = "flag"


AgentStatus = Literal["draft", "deployed"]


class AgentConfig(BaseModel):
    id: str
    name: str
    template: str  # "smart_spend" | "news_monitor" | "blank"
    model: str  # configurable; default from GEMINI_MODEL
    instructions: str
    tools: list[ToolConfig]
    guardrails: Guardrails = Field(default_factory=Guardrails)
    status: AgentStatus = "draft"
    version: int = 1
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    deployed_at: Optional[datetime] = None


class AgentCreate(BaseModel):
    """POST /api/agents body. id/status/timestamps are set by the server."""

    name: str
    template: str
    model: Optional[str] = None
    instructions: str
    tools: list[ToolConfig]
    guardrails: Guardrails = Field(default_factory=Guardrails)


class AgentUpdate(BaseModel):
    """PATCH /api/agents/{id} body. Only provided fields change."""

    name: Optional[str] = None
    model: Optional[str] = None
    instructions: Optional[str] = None
    tools: Optional[list[ToolConfig]] = None
    guardrails: Optional[Guardrails] = None


# ---------- Tools (§3B) ----------


class ToolMetadata(BaseModel):
    """GET /api/tools item. Comes from tools.registry.list_metadata()."""

    name: str
    label: str
    source: str
    category: str
    description: str
    parameters: dict[str, Any]
    settingsSchema: dict[str, Any]


class ToolResult(BaseModel):
    ok: bool
    data: Any = None
    source: str
    cached: bool = False
    fixture: bool = False  # True = local demo fixture, never claimed as live
    duration_ms: int
    error: Optional[str] = None


# ---------- Runs (§3C) ----------

StepType = Literal["llm", "tool", "verify"]
RunStatus = Literal["running", "completed", "failed"]
DataMode = Literal["live", "cached", "fixture"]


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True)


class RunStep(_Camel):
    run_id: str
    agent_id: str
    step: int  # 1-based, chronological
    type: StepType
    tool_name: Optional[str] = None
    input: Any = None  # safe summary; no secrets or raw bank identifiers
    output: Any = None  # safe summary (see docs/API.md)
    ms: int
    tokens: Optional[int] = None  # input+output, from real usage metadata; null if unknown
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    success: bool = True
    cached: Optional[bool] = None  # tool steps only
    fixture: Optional[bool] = None  # tool steps only
    error: Optional[str] = None


class Claim(BaseModel):
    """A figure in the final answer and whether tool data backs it (verify step)."""

    text: str  # the figure as written, e.g. "$189.99"
    context: str  # sentence it appears in
    verified: bool
    source_step: Optional[int] = None  # step number of the backing tool result
    source_tool: Optional[str] = None
    how: Optional[str] = None  # "exact" | "difference" | "sum" | "annualized" | None


class Usage(BaseModel):
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    demo_user_id: Optional[str] = None


class ChatResponse(BaseModel):
    """POST /api/agents/{id}/chat response. Returned by server.runtime.run_agent()."""

    run_id: str
    assistant_message: str
    status: RunStatus
    usage: Usage = Field(default_factory=Usage)
    total_latency_ms: int = 0
    steps: list[RunStep] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    blocked: bool = False  # True if fact_check="block" redacted figures
    data_modes: list[DataMode] = Field(default_factory=list)  # which kinds of data this answer used
    error: Optional[str] = None  # user-safe message when status == "failed"


class Run(BaseModel):
    """GET /api/runs/{id} (with steps) and GET /api/runs items (steps omitted)."""

    id: str
    agent_id: str
    session_id: Optional[str] = None
    status: RunStatus
    user_message: str
    assistant_message: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    total_latency_ms: Optional[int] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    estimated_cost_usd: Optional[float] = None  # null unless pricing configured AND usage known
    claims_total: int = 0
    claims_verified: int = 0
    blocked: bool = False
    error: Optional[str] = None
    steps: Optional[list[RunStep]] = None


# ---------- Analytics ----------


class RunsOverTimePoint(BaseModel):
    bucket: datetime
    runs: int
    failed: int


class AnalyticsSummary(BaseModel):
    """GET /api/analytics/summary[?agent_id=]"""

    total_runs: int
    completed_runs: int
    failed_runs: int
    error_rate: float  # failed / (completed + failed); 0 when no runs
    avg_latency_ms: Optional[float] = None
    input_tokens: int = 0  # sum of known usage
    output_tokens: int = 0
    estimated_cost_usd: Optional[float] = None
    serpapi_calls: int = 0  # live (non-cached, non-fixture) SerpApi requests
    cache_hits: int = 0
    claims_total: int = 0
    claims_verified: int = 0
    runs_over_time: list[RunsOverTimePoint] = Field(default_factory=list)


class ToolAnalytics(BaseModel):
    """GET /api/analytics/tools item."""

    tool_name: str
    calls: int
    errors: int
    avg_ms: Optional[float] = None
    cache_hits: int = 0
    fixture_calls: int = 0
