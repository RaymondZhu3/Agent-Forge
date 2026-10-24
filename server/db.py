"""Database engine, models and repeatable schema setup (docs/PLAN.md §4).

Postgres (Tiger Data) in production via DATABASE_URL; any SQLAlchemy URL works
(tests use SQLite). JSONB on Postgres, plain JSON elsewhere.

Schema setup is idempotent:  python -m server.db
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Iterator, Optional

from sqlalchemy import (
    JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, create_engine, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

Json = JSON().with_variant(JSONB(), "postgresql")

DEFAULT_URL = "sqlite:///./agentforge.db"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_url(url: str) -> str:
    """Use the psycopg v3 driver for plain postgres URLs."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


class Base(DeclarativeBase):
    pass


class AgentRow(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    template: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    instructions: Mapped[str] = mapped_column(Text)
    tools: Mapped[Any] = mapped_column(Json, default=list)
    guardrails: Mapped[Any] = mapped_column(Json, default=dict)
    status: Mapped[str] = mapped_column(String, default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deployed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class RunRow(Base):
    __tablename__ = "runs"
    __table_args__ = (Index("ix_runs_agent_started", "agent_id", "started_at"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    agent_id: Mapped[str] = mapped_column(String, ForeignKey("agents.id"))
    session_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="running")  # running | completed | failed
    user_message: Mapped[str] = mapped_column(Text)
    assistant_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    total_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    claims_total: Mapped[int] = mapped_column(Integer, default=0)
    claims_verified: Mapped[int] = mapped_column(Integer, default=0)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    claims: Mapped[Any] = mapped_column(Json, default=list)
    data_modes: Mapped[Any] = mapped_column(Json, default=list)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class RunStepRow(Base):
    __tablename__ = "run_steps"
    __table_args__ = (Index("ix_run_steps_run", "run_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("runs.id"))
    agent_id: Mapped[str] = mapped_column(String)
    step_number: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String)  # llm | tool | verify
    tool_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    input: Mapped[Any] = mapped_column(Json, nullable=True)
    output: Mapped[Any] = mapped_column(Json, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    cached: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    fixture: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ToolCacheRow(Base):
    __tablename__ = "tool_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cache_key: Mapped[str] = mapped_column(String, unique=True, index=True)
    tool_name: Mapped[str] = mapped_column(String)
    result: Mapped[Any] = mapped_column(Json)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


@lru_cache(maxsize=1)
def get_engine():
    url = normalize_url(os.getenv("DATABASE_URL") or DEFAULT_URL)
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


@lru_cache(maxsize=1)
def _sessionmaker() -> sessionmaker:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def SessionLocal() -> Session:
    return _sessionmaker()()


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def init_db() -> None:
    """Idempotent schema setup (CREATE TABLE/INDEX IF NOT EXISTS)."""
    Base.metadata.create_all(get_engine())


def db_ok() -> bool:
    try:
        with get_engine().connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def aware(dt: datetime | None) -> datetime | None:
    """SQLite drops tzinfo; everything we store is UTC."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    get_engine.cache_clear()
    init_db()
    print("schema ready")
