"""Real-data bug: Windows consoles (cp1252) crashed on ✓/✗ and on unusual characters in model answers."""

from __future__ import annotations

import io
import sys

from server.runtime import cli
from server.schemas import ChatResponse, Claim, Usage


def _cp1252_stdout(monkeypatch) -> io.BytesIO:
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1252", errors="strict"))
    return raw


def test_cli_prints_on_cp1252_console(monkeypatch):
    raw = _cp1252_stdout(monkeypatch)
    resp = ChatResponse(
        run_id="run_x", status="completed", usage=Usage(input_tokens=1, output_tokens=1),
        assistant_message="Savings ≈ $40 ✓ → switch plans 🚀",
        claims=[Claim(text="$40", context="Savings ≈ $40", verified=False)],
    )
    monkeypatch.setattr(cli, "run_agent", lambda *a, **k: resp)
    monkeypatch.setattr(sys, "argv", ["cli", "smart_spend", "hi", "--no-file-cache"])
    assert cli.main() == 0
    sys.stdout.flush()
    assert b"Fact-check: 0/1" in raw.getvalue()


def test_check_keys_prints_on_cp1252_console(monkeypatch):
    from tools import check_keys

    raw = _cp1252_stdout(monkeypatch)

    class R:
        status_code = 200

        def json(self):
            return {"plan_name": "Free Plan", "this_month_usage": 3, "searches_per_month": 250,
                    "total_searches_left": 247, "plan_searches_left": 247}

    monkeypatch.setenv("SERPAPI_KEY", "k")
    monkeypatch.setattr(check_keys.httpx, "get", lambda *a, **k: R())
    check_keys._safe_stdout()
    check_keys.check_serpapi()
    sys.stdout.flush()
    assert b"searches left: 247" in raw.getvalue()
