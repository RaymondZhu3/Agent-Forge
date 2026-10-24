"""DB-backed RunHooks and tool_cache backend (Person 2)."""

from __future__ import annotations

import os
from datetime import timedelta
from typing import Any

from server.db import RunRow, RunStepRow, SessionLocal, ToolCacheRow, aware, utcnow
from server.schemas import ChatResponse, RunStep
from tools.cache import set_cache_backend


def estimate_cost(input_tokens: int | None, output_tokens: int | None) -> float | None:
    """Only when pricing is configured (USD per 1M tokens) AND usage is known. Never guessed."""
    try:
        p_in = float(os.environ["PRICE_INPUT_PER_MTOK"])
        p_out = float(os.environ["PRICE_OUTPUT_PER_MTOK"])
    except (KeyError, ValueError):
        return None
    if input_tokens is None or output_tokens is None:
        return None
    return round((input_tokens * p_in + output_tokens * p_out) / 1_000_000, 6)


class DbHooks:
    def on_run_start(self, run_id: str, agent_id: str, session_id: str | None, user_message: str) -> None:
        with SessionLocal() as s:
            s.add(RunRow(id=run_id, agent_id=agent_id, session_id=session_id,
                         user_message=user_message, status="running", started_at=utcnow()))
            s.commit()

    def on_step(self, step: RunStep) -> None:
        with SessionLocal() as s:
            s.add(RunStepRow(
                run_id=step.run_id, agent_id=step.agent_id, step_number=step.step, type=step.type,
                tool_name=step.tool_name, input=step.input, output=step.output, duration_ms=step.ms,
                tokens=step.tokens, input_tokens=step.input_tokens, output_tokens=step.output_tokens,
                estimated_cost_usd=estimate_cost(step.input_tokens, step.output_tokens),
                success=step.success, cached=step.cached, fixture=step.fixture, error=step.error,
            ))
            s.commit()

    def on_run_finish(self, response: ChatResponse) -> None:
        with SessionLocal() as s:
            run = s.get(RunRow, response.run_id)
            if run is None:
                return
            run.status = response.status
            run.assistant_message = response.assistant_message
            run.completed_at = utcnow()
            run.total_latency_ms = response.total_latency_ms
            run.input_tokens = response.usage.input_tokens
            run.output_tokens = response.usage.output_tokens
            run.estimated_cost_usd = estimate_cost(response.usage.input_tokens, response.usage.output_tokens)
            run.claims = [c.model_dump() for c in response.claims]
            run.claims_total = len(response.claims)
            run.claims_verified = sum(1 for c in response.claims if c.verified)
            run.blocked = response.blocked
            run.data_modes = list(response.data_modes)
            run.error = response.error
            s.commit()


def db_cache_get(key: str) -> dict[str, Any] | None:
    try:
        with SessionLocal() as s:
            row = s.query(ToolCacheRow).filter(ToolCacheRow.cache_key == key).one_or_none()
            if row is None or aware(row.expires_at) <= utcnow():
                return None
            return row.result
    except Exception:
        return None  # cache is best-effort


def db_cache_set(key: str, tool_name: str, result: dict[str, Any], ttl_seconds: int) -> None:
    now = utcnow()
    with SessionLocal() as s:
        row = s.query(ToolCacheRow).filter(ToolCacheRow.cache_key == key).one_or_none()
        if row is None:
            s.add(ToolCacheRow(cache_key=key, tool_name=tool_name, result=result,
                               created_at=now, expires_at=now + timedelta(seconds=ttl_seconds)))
        else:
            row.result, row.created_at, row.expires_at = result, now, now + timedelta(seconds=ttl_seconds)
        try:
            s.commit()
        except Exception:
            s.rollback()  # a lost cache write must never fail a run


def register_cache_backend() -> None:
    set_cache_backend(get=db_cache_get, set=db_cache_set)
