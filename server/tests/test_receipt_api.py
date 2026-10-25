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


def test_demo_account_and_draft_routes(client):  # noqa: F811
    from server.runtime.llm import LLMTurn
    from server.tests.test_api import ScriptedLLM

    r = client.get("/api/demo-account", params={"agent_id": "agent-smart-spend"})
    assert r.status_code == 200 and r.json()["purchases"]["purchase_count"] == 11
    assert client.get("/api/demo-account", params={"agent_id": "agent-news-monitor"}).status_code == 404

    use_llm(ScriptedLLM(LLMTurn('{"name": "Court Scout", "instructions": "1. Find courts.", "tools": ["serpapi_local_places"]}', [])))
    d = client.post("/api/agents/draft", json={"description": "finds tennis courts near campus"})
    assert d.status_code == 200 and d.json()["tools"][0]["name"] == "serpapi_local_places"
