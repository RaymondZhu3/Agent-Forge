"""Seed the two demo agents (deployed) at startup if missing."""

from __future__ import annotations

import os

from server.db import AgentRow, SessionLocal, utcnow
from server.runtime import TEMPLATES

SEED_IDS = {"smart_spend": "agent-smart-spend", "news_monitor": "agent-news-monitor"}


def seed_agents() -> None:
    customer_id = os.getenv("DEMO_CUSTOMER_ID")  # optional; seed_nessie.py stores the real one in the DB
    with SessionLocal() as s:
        for t in TEMPLATES:
            agent_id = SEED_IDS.get(t.template)
            if not agent_id or s.get(AgentRow, agent_id):
                continue
            tools = [x.model_dump() for x in t.tools]
            if customer_id:
                for x in tools:
                    if x["name"].startswith("nessie_"):
                        x["settings"] = {**x["settings"], "customer_id": customer_id}
            now = utcnow()
            s.add(AgentRow(
                id=agent_id, name=t.name, template=t.template, model=t.model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                instructions=t.instructions, tools=tools, guardrails=t.guardrails.model_dump(),
                status="deployed", version=1, created_at=now, updated_at=now, deployed_at=now,
            ))
        s.commit()
