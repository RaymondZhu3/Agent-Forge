"""Agent Forge API. Run from the repo root:  uvicorn server.main:app --reload"""

from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, HTTPException, Request  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from server import analytics  # noqa: E402
from server.db import AgentRow, RunRow, RunStepRow, aware, db_ok, get_session, init_db, utcnow  # noqa: E402
from server.hooks import DbHooks, register_cache_backend  # noqa: E402
from server.runtime import TEMPLATES, run_agent  # noqa: E402
from server.runtime.llm import LLM  # noqa: E402
from server.schemas import (  # noqa: E402
    AgentConfig, AgentCreate, AgentUpdate, AnalyticsSummary, ChatRequest, ChatResponse, Guardrails, Run, RunStep,
    ToolAnalytics, ToolConfig,
)
from server.seed import SEED_IDS, seed_agents  # noqa: E402
from tools.base import ToolError, validate  # noqa: E402
from tools.registry import registry  # noqa: E402

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    register_cache_backend()
    seed_agents()
    yield


app = FastAPI(title="Agent Forge", lifespan=lifespan)

_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in _origins if o.strip()],
                   allow_origin_regex=os.getenv("CORS_ORIGIN_REGEX") or None,
                   allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
    return JSONResponse(status_code=400, content={"detail": f"Invalid request: {loc} {first.get('msg', '')}".strip()})


def get_llm() -> Optional[LLM]:
    """None = runtime default (Gemini). Tests override this dependency with a fake."""
    return None


# ---------- helpers ----------


def _to_config(r: AgentRow) -> AgentConfig:
    return AgentConfig(
        id=r.id, name=r.name, template=r.template, model=r.model, instructions=r.instructions,
        tools=[ToolConfig(**t) for t in (r.tools or [])],
        guardrails=Guardrails(**(r.guardrails or {})),
        status=r.status, version=r.version,
        created_at=aware(r.created_at), updated_at=aware(r.updated_at), deployed_at=aware(r.deployed_at),
    )


def _validate_tools(tools: list[ToolConfig]) -> None:
    for tc in tools:
        tool = registry.get(tc.name)
        if tool is None:
            raise HTTPException(400, f"Unknown tool '{tc.name}'")
        try:
            validate(tc.settings, tool.settings_schema, what=f"setting for {tc.name}")
        except ToolError as e:
            raise HTTPException(400, str(e))


def _get_agent(s: Session, agent_id: str) -> AgentRow:
    row = s.get(AgentRow, agent_id)
    if row is None:
        raise HTTPException(404, "Agent not found")
    return row


def _step(r: RunStepRow) -> RunStep:
    return RunStep(
        run_id=r.run_id, agent_id=r.agent_id, step=r.step_number, type=r.type, tool_name=r.tool_name,
        input=r.input, output=r.output, ms=r.duration_ms, tokens=r.tokens, input_tokens=r.input_tokens,
        output_tokens=r.output_tokens, success=r.success, cached=r.cached, fixture=r.fixture, error=r.error,
    )


def _run(r: RunRow, steps: list[RunStepRow] | None = None) -> Run:
    return Run(
        id=r.id, agent_id=r.agent_id, session_id=r.session_id, status=r.status, user_message=r.user_message,
        assistant_message=r.assistant_message, started_at=aware(r.started_at), completed_at=aware(r.completed_at),
        total_latency_ms=r.total_latency_ms, input_tokens=r.input_tokens, output_tokens=r.output_tokens,
        estimated_cost_usd=r.estimated_cost_usd, claims_total=r.claims_total or 0,
        claims_verified=r.claims_verified or 0, blocked=bool(r.blocked), error=r.error,
        steps=None if steps is None else [_step(x) for x in steps],
    )


# ---------- endpoints ----------


@app.get("/api/health")
def health():
    db = db_ok()
    live = lambda key, mock: "live" if os.getenv(key) and os.getenv(mock) != "1" else "fixture"  # noqa: E731
    return {
        "ok": db, "db": db,
        "gemini": bool(os.getenv("GEMINI_API_KEY")),
        "serpapi": live("SERPAPI_KEY", "SERPAPI_MOCK"),
        "nessie": live("NESSIE_API_KEY", "NESSIE_MOCK"),
    }


@app.get("/api/tools")
def list_tools():
    return registry.list_metadata()


@app.get("/api/templates")
def list_templates():
    return [t.model_dump() for t in TEMPLATES]


@app.get("/api/agents", response_model=list[AgentConfig])
def list_agents(s: Session = Depends(get_session)):
    return [_to_config(r) for r in s.query(AgentRow).order_by(AgentRow.created_at).all()]


@app.post("/api/agents", response_model=AgentConfig)
def create_agent(body: AgentCreate, s: Session = Depends(get_session)):
    _validate_tools(body.tools)
    now = utcnow()
    row = AgentRow(
        id=f"agent-{uuid.uuid4().hex[:8]}", name=body.name, template=body.template,
        model=body.model or DEFAULT_MODEL, instructions=body.instructions,
        tools=[t.model_dump() for t in body.tools], guardrails=body.guardrails.model_dump(),
        status="draft", version=1, created_at=now, updated_at=now,
    )
    s.add(row)
    s.commit()
    return _to_config(row)


@app.get("/api/agents/{agent_id}", response_model=AgentConfig)
def get_agent(agent_id: str, s: Session = Depends(get_session)):
    return _to_config(_get_agent(s, agent_id))


@app.patch("/api/agents/{agent_id}", response_model=AgentConfig)
def update_agent(agent_id: str, body: AgentUpdate, s: Session = Depends(get_session)):
    row = _get_agent(s, agent_id)
    if body.tools is not None:
        _validate_tools(body.tools)
        row.tools = [t.model_dump() for t in body.tools]
    if body.name is not None:
        row.name = body.name
    if body.model is not None:
        row.model = body.model
    if body.instructions is not None:
        row.instructions = body.instructions
    if body.guardrails is not None:
        row.guardrails = body.guardrails.model_dump()
    row.version += 1
    row.updated_at = utcnow()
    s.commit()
    return _to_config(row)


@app.delete("/api/agents/{agent_id}")
def delete_agent(agent_id: str, s: Session = Depends(get_session)):
    row = _get_agent(s, agent_id)
    if agent_id in SEED_IDS.values():
        raise HTTPException(409, "The built-in demo agents can't be deleted.")
    run_ids = [r.id for r in s.query(RunRow.id).filter(RunRow.agent_id == agent_id)]
    steps = s.query(RunStepRow).filter(RunStepRow.run_id.in_(run_ids)).delete(synchronize_session=False) if run_ids else 0
    runs = s.query(RunRow).filter(RunRow.agent_id == agent_id).delete(synchronize_session=False)
    s.delete(row)
    s.commit()
    return {"deleted": agent_id, "runs_deleted": runs, "steps_deleted": steps}


@app.post("/api/agents/{agent_id}/deploy", response_model=AgentConfig)
def deploy_agent(agent_id: str, s: Session = Depends(get_session)):
    row = _get_agent(s, agent_id)
    row.status = "deployed"
    row.deployed_at = row.updated_at = utcnow()
    s.commit()
    return _to_config(row)


@app.post("/api/agents/{agent_id}/chat", response_model=ChatResponse)
def chat(agent_id: str, body: ChatRequest, s: Session = Depends(get_session), llm: Optional[LLM] = Depends(get_llm)):
    row = _get_agent(s, agent_id)
    if row.status != "deployed":
        raise HTTPException(409, "This agent isn't deployed yet. Deploy it before chatting.")
    config = _to_config(row)
    s.close()  # don't hold a connection during the model loop
    return run_agent(config, body.message, body.session_id, hooks=DbHooks(), llm=llm)


@app.get("/api/runs", response_model=list[Run])
def list_runs(agent_id: Optional[str] = None, limit: int = 50, s: Session = Depends(get_session)):
    q = s.query(RunRow)
    if agent_id:
        q = q.filter(RunRow.agent_id == agent_id)
    rows = q.order_by(RunRow.started_at.desc()).limit(max(1, min(limit, 500))).all()
    return [_run(r) for r in rows]


@app.get("/api/runs/{run_id}", response_model=Run)
def get_run(run_id: str, s: Session = Depends(get_session)):
    r = s.get(RunRow, run_id)
    if r is None:
        raise HTTPException(404, "Run not found")
    steps = s.query(RunStepRow).filter(RunStepRow.run_id == run_id).order_by(RunStepRow.step_number).all()
    return _run(r, steps)


@app.get("/api/analytics/summary", response_model=AnalyticsSummary)
def analytics_summary(agent_id: Optional[str] = None, s: Session = Depends(get_session)):
    return analytics.summary(s, agent_id)


@app.get("/api/analytics/tools", response_model=list[ToolAnalytics])
def analytics_tools(agent_id: Optional[str] = None, s: Session = Depends(get_session)):
    return analytics.by_tool(s, agent_id)


# ---------- Person 1 additions (experimental, Oct 25): agent drafting + demo account ----------
# Logic lives in server/runtime/drafting.py; these routes only adapt it to HTTP.
from pydantic import BaseModel as _BaseModel  # noqa: E402

from server.runtime.drafting import demo_account, draft_agent  # noqa: E402
from server.runtime.llm import LLMError  # noqa: E402


class _DraftRequest(_BaseModel):
    description: str


@app.post("/api/agents/draft", response_model=AgentCreate)
def draft_agent_route(body: _DraftRequest, llm: Optional[LLM] = Depends(get_llm)):
    """One sentence -> a reviewed-before-deploy agent config (nothing is saved)."""
    try:
        return draft_agent(body.description, llm=llm)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except LLMError as e:
        raise HTTPException(502, str(e))


@app.get("/api/runs/{run_id}/verify")
def verify_run_route(run_id: str, s: Session = Depends(get_session)):
    """Recompute a stored run's audit receipt and check its signature with the server's RECEIPT_SECRET."""
    from server.runtime.receipt import verify_run

    r = s.get(RunRow, run_id)
    if r is None:
        raise HTTPException(404, "Run not found")
    steps = s.query(RunStepRow).filter(RunStepRow.run_id == run_id).order_by(RunStepRow.step_number).all()
    return verify_run(_run(r, steps).model_dump(mode="json", by_alias=True))


@app.get("/api/demo-account")
def demo_account_route(agent_id: str, s: Session = Depends(get_session)):
    """The demo customer's accounts, purchases and bills, read with the agent's own Nessie settings."""
    config = _to_config(_get_agent(s, agent_id))
    try:
        return demo_account(config)
    except ValueError as e:
        raise HTTPException(404, str(e))
