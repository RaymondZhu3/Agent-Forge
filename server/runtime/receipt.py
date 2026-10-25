"""Tamper-evident audit receipts.

Every fact-checked run gets a SHA-256 hash chain over exactly what is stored:

    h0 = sha256("agentforge-receipt-v1\\n" + canonical({run_id, agent_id, user_message}))
    hi = sha256(h(i-1) + "\\n" + canonical(step i))        for every step, in order
    receipt = sha256(h_n + "\\n" + canonical({answer}))

The final verify step stores {"receipt": {"hash", "steps": [h1..hn]}}; its own record is hashed without the
"receipt" key. Tool steps also store data_sha256, a hash of the full raw tool data (which is not stored).
Change anything in a stored step, the answer, or a figure's verified/flagged label and the chain no longer
matches. web/src/lib/receipt.ts implements the same canonical form, so the browser can check it too.

What it proves: the stored record wasn't altered after the run. What it doesn't: that tool data was true
(that's the fact-check), or that someone with database access didn't recompute the whole chain (signing the
receipt with a server key, or publishing it elsewhere, would close that).

    python -m server.runtime.receipt RUN_ID [--api http://144.202.28.129:8000]
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from decimal import Decimal
from typing import Any

VERSION = "agentforge-receipt-v1"


def _js_number(x: float) -> str:
    """Format a float exactly like JavaScript's Number.prototype.toString, so Python and the browser agree."""
    if not math.isfinite(x):
        raise ValueError("non-finite number in receipt data")
    if x == int(x) and abs(x) < 1e21:
        return str(int(x))
    sign, digits, exp = Decimal(repr(x)).as_tuple()
    ds = "".join(map(str, digits)).rstrip("0") or "0"
    exp += len(digits) - len(ds)  # account for stripped zeros
    k, n = len(ds), len(ds) + exp  # value = 0.ds x 10^n
    if k <= n <= 21:
        s = ds + "0" * (n - k)
    elif 0 < n <= 21:
        s = ds[:n] + "." + ds[n:]
    elif -6 < n <= 0:
        s = "0." + "0" * (-n) + ds
    else:
        e = n - 1
        s = ds[0] + ("." + ds[1:] if k > 1 else "") + ("e+" if e >= 0 else "e-") + str(abs(e))
    return ("-" if sign else "") + s


def canonical(v: Any) -> str:
    """Deterministic JSON: sorted keys, no whitespace, JS number formatting, non-ASCII kept as-is."""
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return _js_number(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(canonical(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ",".join(json.dumps(str(k), ensure_ascii=False) + ":" + canonical(v[k]) for k in sorted(v, key=str)) + "}"
    return canonical(str(v))


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def data_hash(data: Any) -> str:
    return sha256(canonical(data))


def step_record(step: dict[str, Any]) -> dict[str, Any]:
    """The hashed part of a step. Accepts the runtime's snake_case or the API's camelCase keys."""
    out = step.get("output")
    if isinstance(out, dict) and "receipt" in out:
        out = {k: v for k, v in out.items() if k != "receipt"}
    return {
        "step": step.get("step"),
        "type": step.get("type"),
        "tool": step.get("tool_name", step.get("toolName")),
        "input": step.get("input"),
        "output": out,
        "success": bool(step.get("success", True)),
        "error": step.get("error"),
    }


def chain(run_id: str, agent_id: str, user_message: str, steps: list[dict[str, Any]], answer: str | None) -> dict[str, Any]:
    h = sha256(VERSION + "\n" + canonical({"run_id": run_id, "agent_id": agent_id, "user_message": user_message}))
    links = []
    for st in steps:
        h = sha256(h + "\n" + canonical(step_record(st)))
        links.append(h)
    return {"version": 1, "algo": "sha256", "hash": sha256(h + "\n" + canonical({"answer": answer or ""})), "steps": links}


def verify_run(run: dict[str, Any]) -> dict[str, Any]:
    """Recompute a stored run's receipt (GET /api/runs/{id} JSON). Returns {ok, reason, hash, ...}."""
    steps = run.get("steps") or []
    idx = next((i for i in range(len(steps) - 1, -1, -1)
                if isinstance(steps[i].get("output"), dict) and isinstance(steps[i]["output"].get("receipt"), dict)), None)
    if idx is None:
        return {"ok": False, "reason": "This run has no receipt (fact-check was off, or it ran before receipts existed)."}
    stored = steps[idx]["output"]["receipt"]
    got = chain(run.get("id") or run.get("run_id") or "", run.get("agent_id") or run.get("agentId") or "",
                run.get("user_message") or run.get("userMessage") or "", steps[: idx + 1],
                run.get("assistant_message") if "assistant_message" in run else run.get("assistantMessage"))
    if got["hash"] == stored.get("hash"):
        return {"ok": True, "reason": f"The record is intact. All {idx + 1} steps and the answer match the receipt.", "hash": got["hash"]}
    for i, (a, b) in enumerate(zip(got["steps"], stored.get("steps") or [])):
        if a != b:
            return {"ok": False, "reason": f"Record changed at step {steps[i].get('step', i + 1)}.", "hash": got["hash"]}
    return {"ok": False, "reason": "The answer was changed after the run.", "hash": got["hash"]}


def main(argv: list[str] | None = None) -> int:
    import argparse

    import httpx

    p = argparse.ArgumentParser(description="Check a stored run against its audit receipt.")
    p.add_argument("run_id")
    p.add_argument("--api", default="http://127.0.0.1:8000")
    a = p.parse_args(argv)
    r = httpx.get(f"{a.api.rstrip('/')}/api/runs/{a.run_id}", timeout=20)
    if r.status_code != 200:
        print(f"Couldn't load run {a.run_id}: HTTP {r.status_code}")
        return 2
    res = verify_run(r.json())
    print(("OK   " if res["ok"] else "FAIL ") + res["reason"] + (f"\n     receipt {res['hash']}" if res.get("hash") else ""))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
