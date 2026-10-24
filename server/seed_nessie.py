"""Seed Capital One Nessie with the demo customer, then point Smart Spend at it.

    python -m server.seed_nessie            # creates data, prints customer_id, updates the DB agent

Uses the same purchases/bills/amounts as tools/fixtures.py. Needs NESSIE_API_KEY.
Not idempotent on the Nessie side: each run creates a NEW customer (Nessie has no upsert);
the latest customer_id is what Smart Spend gets pointed at.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import httpx
from dotenv import load_dotenv

from tools import fixtures as fx

load_dotenv()

TIMEOUT_S = 20


def _post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    base = os.getenv("NESSIE_BASE_URL", "https://api.nessieisreal.com").rstrip("/")
    res = httpx.post(f"{base}{path}", params={"key": os.environ["NESSIE_API_KEY"]}, json=body, timeout=TIMEOUT_S)
    if res.status_code >= 400:
        raise SystemExit(f"Nessie POST {path} failed: HTTP {res.status_code} {res.text[:200]}")
    return res.json()["objectCreated"]


def seed() -> str:
    c = fx.DEMO_CUSTOMER
    customer = _post("/customers", {
        "first_name": c["first_name"], "last_name": c["last_name"],
        "address": {"street_number": "100", "street_name": "Congress Ave", "city": "Austin", "state": "TX", "zip": "78701"},
    })
    cid = customer["_id"]

    accounts: dict[str, str] = {}  # fixture account id -> real id
    for a in fx.DEMO_ACCOUNTS:
        created = _post(f"/customers/{cid}/accounts", {
            "type": a["type"], "nickname": a["nickname"], "rewards": 0, "balance": int(round(a["balance"])),
        })
        accounts[a["_id"]] = created["_id"]

    merchants: dict[str, str] = {}
    for key, name in fx.DEMO_MERCHANTS.items():
        merchants[key] = _post("/merchants", {
            "name": name, "category": "demo",
            "address": {"street_number": "1", "street_name": "Main St", "city": "Austin", "state": "TX", "zip": "78701"},
            "geocode": {"lat": 30.2672, "lng": -97.7431},
        })["_id"]

    for fx_acct, purchases in fx.DEMO_PURCHASES.items():
        for p in purchases:
            _post(f"/accounts/{accounts[fx_acct]}/purchases", {
                "merchant_id": merchants[p["merchant_id"]], "medium": "balance", "status": "completed",
                "purchase_date": p["purchase_date"], "amount": p["amount"], "description": p["description"],
            })

    for fx_acct, bills in fx.DEMO_BILLS.items():
        for b in bills:
            _post(f"/accounts/{accounts[fx_acct]}/bills", {
                "status": "recurring", "payee": b["payee"], "nickname": b["nickname"],
                "payment_date": f"2026-10-{b['recurring_date']:02d}",
                "recurring_date": b["recurring_date"], "payment_amount": b["payment_amount"],
            })
    return cid


def point_smart_spend_at(customer_id: str) -> bool:
    """Store customer_id in the Smart Spend agent's Nessie tool settings."""
    from server.db import AgentRow, SessionLocal, init_db, utcnow
    from server.seed import seed_agents

    init_db()
    seed_agents()
    with SessionLocal() as s:
        row = s.get(AgentRow, "agent-smart-spend")
        if row is None:
            return False
        row.tools = [
            {**t, "settings": {**t.get("settings", {}), "customer_id": customer_id}} if t["name"].startswith("nessie_") else t
            for t in row.tools
        ]
        row.updated_at = utcnow()
        s.commit()
    return True


if __name__ == "__main__":
    if not os.getenv("NESSIE_API_KEY"):
        sys.exit("NESSIE_API_KEY is not set")
    customer_id = seed()
    print(f"customer_id: {customer_id}")
    print("Smart Spend updated in DB" if point_smart_spend_at(customer_id)
          else "Smart Spend agent not found; set DEMO_CUSTOMER_ID in the environment instead")
