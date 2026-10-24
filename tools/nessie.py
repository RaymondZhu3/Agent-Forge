"""Capital One Nessie tools: accounts, purchases, bills (Person 1). Read-only.

Docs: http://api.nessieisreality.com/documentation
Routes used (GET only):
  /customers                      list customers (fallback when no customer_id configured)
  /customers/{id}                 customer
  /customers/{id}/accounts        accounts
  /accounts/{id}/purchases        purchases
  /accounts/{id}/bills            bills
  /merchants/{id}                 merchant name

All totals are computed here in code (deterministic) so Gemini explains numbers
instead of inventing them. Account ids/numbers are never returned to the model.

Env: NESSIE_API_KEY (missing -> labeled fixtures), NESSIE_BASE_URL, NESSIE_MOCK=1.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict
from typing import Any

import httpx

from . import fixtures as fx
from .base import Tool, ToolError

TIMEOUT_S = 15

CUSTOMER_SETTING = {
    "type": "object",
    "properties": {"customer_id": {"type": "string", "description": "Nessie customer id for this agent's demo user"}},
}


# When Nessie can't be reached (hackathon Wi-Fi, outage), serve labeled fixtures for a minute, then retry.
# NESSIE_FALLBACK=0 turns this off (tools then fail with "Could not reach Nessie").
OFFLINE_RETRY_S = 60
_offline_until = 0.0


class NessieUnreachable(ToolError):
    pass


def _use_fixtures() -> bool:
    return (
        not os.getenv("NESSIE_API_KEY")
        or os.getenv("NESSIE_MOCK") == "1"
        or _offline_until > time.time()
    )


def _base() -> str:
    return os.getenv("NESSIE_BASE_URL", "http://api.nessieisreality.com").rstrip("/")


def _get(path: str) -> Any:
    try:
        res = httpx.get(f"{_base()}{path}", params={"key": os.environ["NESSIE_API_KEY"]}, timeout=TIMEOUT_S)
    except httpx.TimeoutException:
        raise NessieUnreachable("Nessie timed out")
    except httpx.HTTPError:
        raise NessieUnreachable("Could not reach Nessie")
    if res.status_code == 404:
        raise ToolError("Nessie record not found (check customer_id)")
    if res.status_code in (401, 403):
        raise ToolError("Nessie rejected the API key")
    if res.status_code >= 400:
        raise ToolError(f"Nessie returned HTTP {res.status_code}")
    return res.json()


# ---- data access (live or fixture), returns (value, fixture) ----

def _customer(customer_id: str | None) -> tuple[dict[str, Any], bool]:
    global _offline_until
    if _use_fixtures():
        return fx.DEMO_CUSTOMER, True
    try:
        if customer_id:
            return _get(f"/customers/{customer_id}"), False
        customers = _get("/customers")
    except NessieUnreachable:
        if os.getenv("NESSIE_FALLBACK") == "0":
            raise
        _offline_until = time.time() + OFFLINE_RETRY_S
        return fx.DEMO_CUSTOMER, True
    if not customers:
        raise ToolError("No Nessie customers exist yet (run the seed script)")
    return customers[0], False


def _accounts(customer_id: str) -> list[dict[str, Any]]:
    if _use_fixtures():
        return fx.DEMO_ACCOUNTS
    return _get(f"/customers/{customer_id}/accounts")


def _purchases(account_id: str) -> list[dict[str, Any]]:
    if _use_fixtures():
        return fx.DEMO_PURCHASES.get(account_id, [])
    return _get(f"/accounts/{account_id}/purchases")


def _bills(account_id: str) -> list[dict[str, Any]]:
    if _use_fixtures():
        return fx.DEMO_BILLS.get(account_id, [])
    return _get(f"/accounts/{account_id}/bills")


_merchant_cache: dict[str, str] = {}


def _merchant_name(merchant_id: str | None) -> str | None:
    if not merchant_id:
        return None
    if _use_fixtures():
        return fx.DEMO_MERCHANTS.get(merchant_id)
    if merchant_id not in _merchant_cache:
        try:
            _merchant_cache[merchant_id] = _get(f"/merchants/{merchant_id}").get("name") or "Unknown merchant"
        except ToolError:
            _merchant_cache[merchant_id] = "Unknown merchant"
    return _merchant_cache[merchant_id]


def _money(x: Any) -> float:
    return round(float(x or 0), 2)


def _customer_and_accounts(settings: dict[str, Any]):
    customer, fixture = _customer(settings.get("customer_id"))
    return customer, _accounts(customer["_id"]), fixture


def _acct_label(a: dict[str, Any]) -> str:
    return a.get("nickname") or a.get("type") or "Account"


# ---------------- nessie_accounts ----------------

def _run_accounts(input: dict[str, Any], settings: dict[str, Any]):
    customer, accounts, fixture = _customer_and_accounts(settings)
    rows = [{"account": _acct_label(a), "type": a.get("type"), "balance": _money(a.get("balance"))} for a in accounts]
    data = {
        "customer_name": f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip(),
        "accounts": rows,
        "account_count": len(rows),
    }
    return data, False, fixture


nessie_accounts = Tool(
    name="nessie_accounts",
    label="Accounts",
    source="nessie",
    category="banking",
    description="Get the customer's bank accounts with type and current balance. Read-only.",
    parameters={"type": "object", "properties": {}},
    settings_schema=CUSTOMER_SETTING,
    run_fn=_run_accounts,
    summarize_fn=lambda d: f"{d['account_count']} accounts",
)


# ---------------- nessie_purchases ----------------

def _run_purchases(input: dict[str, Any], settings: dict[str, Any]):
    _, accounts, fixture = _customer_and_accounts(settings)
    purchases = []
    for a in accounts:
        for p in _purchases(a["_id"]):
            purchases.append({
                "description": p.get("description"),
                "amount": _money(p.get("amount")),
                "merchant": _merchant_name(p.get("merchant_id")),
                "date": p.get("purchase_date"),
                "account": _acct_label(a),
                "status": p.get("status"),
            })
    purchases.sort(key=lambda p: p.get("date") or "", reverse=True)

    by_merchant: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "total": 0.0})
    for p in purchases:
        m = p["merchant"] or "Unknown merchant"
        by_merchant[m]["count"] += 1
        by_merchant[m]["total"] = _money(by_merchant[m]["total"] + p["amount"])
    merchants = sorted(
        ({"merchant": m, **v} for m, v in by_merchant.items()), key=lambda r: r["total"], reverse=True
    )
    total = _money(sum(p["amount"] for p in purchases))
    dates = [p["date"] for p in purchases if p["date"]]
    data = {
        "purchase_count": len(purchases),
        "total_spent": total,
        "date_range": {"from": min(dates), "to": max(dates)} if dates else None,
        "by_merchant": merchants,  # deterministic totals
        "repeat_merchants": [m["merchant"] for m in merchants if m["count"] >= 3],
        "purchases": purchases[:50],
    }
    return data, False, fixture


nessie_purchases = Tool(
    name="nessie_purchases",
    label="Purchases",
    source="nessie",
    category="banking",
    description=(
        "Get the customer's recent purchases (item, amount, merchant, date) across all accounts, "
        "with totals already calculated per merchant. Use these totals; do not recompute or estimate them. Read-only."
    ),
    parameters={"type": "object", "properties": {}},
    settings_schema=CUSTOMER_SETTING,
    run_fn=_run_purchases,
    summarize_fn=lambda d: f"{d['purchase_count']} purchases, total ${d['total_spent']:.2f}",
)


# ---------------- nessie_bills ----------------

def _run_bills(input: dict[str, Any], settings: dict[str, Any]):
    _, accounts, fixture = _customer_and_accounts(settings)
    bills = []
    for a in accounts:
        for b in _bills(a["_id"]):
            bills.append({
                "payee": b.get("payee"),
                "name": b.get("nickname"),
                "amount": _money(b.get("payment_amount")),
                "status": b.get("status"),
                "recurring_day_of_month": b.get("recurring_date"),
                "account": _acct_label(a),
            })
    recurring = [b for b in bills if b["status"] == "recurring" or b["recurring_day_of_month"]]
    data = {
        "bill_count": len(bills),
        "recurring_count": len(recurring),
        "recurring_monthly_total": _money(sum(b["amount"] for b in recurring)),
        "bills": bills,
    }
    return data, False, fixture


nessie_bills = Tool(
    name="nessie_bills",
    label="Bills",
    source="nessie",
    category="banking",
    description=(
        "Get the customer's bills and recurring payments (payee, amount, status) with the recurring monthly total "
        "already calculated. Read-only."
    ),
    parameters={"type": "object", "properties": {}},
    settings_schema=CUSTOMER_SETTING,
    run_fn=_run_bills,
    summarize_fn=lambda d: f"{d['bill_count']} bills, ${d['recurring_monthly_total']:.2f}/mo recurring",
)

NESSIE_TOOLS = [nessie_accounts, nessie_purchases, nessie_bills]
