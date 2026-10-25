"""A receipt still verifies after the run is saved to the database and read back through the API."""

from __future__ import annotations

from server.runtime.receipt import verify_run
from server.tests.test_api import client, smart_spend_script, use_llm  # noqa: F401  (pytest fixture)


def test_receipt_survives_db_round_trip(client):  # noqa: F811
    use_llm(smart_spend_script())
    r = client.post("/api/agents/agent-smart-spend/chat", json={"message": "Find savings", "session_id": "rcpt"})
    assert r.status_code == 200, r.text
    run = client.get(f"/api/runs/{r.json()['run_id']}").json()
    res = verify_run(run)
    assert res["ok"], res
