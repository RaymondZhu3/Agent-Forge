"""End-to-end API tests: create -> deploy -> chat -> run saved -> analytics. Fake LLM, fixture tools."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server.main import app, get_llm
from server.runtime.llm import FunctionCall, LLMTurn


class ScriptedLLM:
    def __init__(self, *turns):
        self.turns = list(turns)

    def generate(self, model, system, history, tools):
        return self.turns.pop(0)


def smart_spend_script():
    return ScriptedLLM(
        LLMTurn("", [FunctionCall("nessie_purchases", {}, "c1")], 100, 10),
        LLMTurn("", [FunctionCall("serpapi_shopping", {"query": "AirPods Pro 2"}, "c2")], 200, 10),
        LLMTurn("AirPods Pro 2: you paid $249.00 at Target; Amazon lists them at $189.99 "
                "(potential saving $59.01). You will probably save $15.00 a month.", [], 300, 40),
    )


@pytest.fixture()
def client():
    with TestClient(app) as c:  # runs lifespan: schema, cache backend, seed
        yield c
    app.dependency_overrides.clear()


def use_llm(llm):
    app.dependency_overrides[get_llm] = lambda: llm


def test_health_tools_templates(client):
    h = client.get("/api/health").json()
    assert h["ok"] and h["db"] and h["serpapi"] == "fixture" and h["nessie"] == "fixture"
    assert len(client.get("/api/tools").json()) == 7
    assert {t["template"] for t in client.get("/api/templates").json()} >= {"smart_spend", "news_monitor", "blank"}


def test_seeded_agents_deployed(client):
    ids = {a["id"]: a for a in client.get("/api/agents").json()}
    assert ids["agent-smart-spend"]["status"] == "deployed"
    assert ids["agent-news-monitor"]["status"] == "deployed"


def test_validation_and_errors(client):
    base = {"name": "x", "template": "blank", "instructions": "i"}
    assert client.post("/api/agents", json={**base, "tools": [{"name": "nope", "settings": {}}]}).status_code == 400
    assert client.post("/api/agents", json={**base, "tools": [{"name": "serpapi_news", "settings": {"bogus": 1}}]}).status_code == 400
    assert client.post("/api/agents", json={"name": "x"}).status_code == 400
    assert client.get("/api/agents/missing").status_code == 404
    assert client.get("/api/runs/missing").status_code == 404


def test_lifecycle_and_analytics_counts(client):
    before = client.get("/api/analytics/summary").json()

    created = client.post("/api/agents", json={
        "name": "Spender", "template": "smart_spend", "instructions": "Find savings.",
        "tools": [{"name": "nessie_purchases", "settings": {}}, {"name": "serpapi_shopping", "settings": {}}],
    })
    assert created.status_code == 200
    agent = created.json()
    assert agent["status"] == "draft" and agent["version"] == 1 and agent["deployed_at"] is None
    aid = agent["id"]

    # chat before deploy -> 409
    assert client.post(f"/api/agents/{aid}/chat", json={"message": "hi"}).status_code == 409

    patched = client.patch(f"/api/agents/{aid}", json={"name": "Spender 2"}).json()
    assert patched["version"] == 2 and patched["name"] == "Spender 2"

    deployed = client.post(f"/api/agents/{aid}/deploy").json()
    assert deployed["status"] == "deployed" and deployed["deployed_at"]

    use_llm(smart_spend_script())
    res = client.post(f"/api/agents/{aid}/chat", json={"message": "Find savings", "session_id": "s1"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "completed"
    run_id = body["run_id"]

    run = client.get(f"/api/runs/{run_id}").json()
    assert run["agent_id"] == aid and run["status"] == "completed"
    assert run["assistant_message"] == body["assistant_message"]
    assert run["input_tokens"] == 600 and run["output_tokens"] == 60
    assert run["estimated_cost_usd"] is None  # no pricing configured
    assert [s["step"] for s in run["steps"]] == list(range(1, len(body["steps"]) + 1))
    assert len(run["steps"]) == len(body["steps"])
    assert {s["toolName"] for s in run["steps"] if s["type"] == "tool"} == {"nessie_purchases", "serpapi_shopping"}
    assert run["claims_total"] == len(body["claims"]) >= 3
    assert run["claims_verified"] == sum(c["verified"] for c in body["claims"])
    assert run["claims_verified"] < run["claims_total"]  # the invented $15.00 is unverified

    assert [r["id"] for r in client.get(f"/api/runs?agent_id={aid}").json()] == [run_id]
    assert client.get(f"/api/runs?agent_id={aid}").json()[0]["steps"] is None

    s = client.get(f"/api/analytics/summary?agent_id={aid}").json()
    assert s["total_runs"] == 1 and s["completed_runs"] == 1 and s["failed_runs"] == 0
    assert s["error_rate"] == 0 and s["input_tokens"] == 600 and s["output_tokens"] == 60
    assert s["estimated_cost_usd"] is None
    assert s["serpapi_calls"] == 0  # fixture mode: not a live SerpApi request
    assert s["claims_total"] == run["claims_total"] and s["claims_verified"] == run["claims_verified"]
    assert len(s["runs_over_time"]) == 1 and s["runs_over_time"][0]["runs"] == 1
    assert s["runs_over_time"][0]["bucket"].endswith(("Z", "+00:00"))

    tools = {t["tool_name"]: t for t in client.get(f"/api/analytics/tools?agent_id={aid}").json()}
    assert tools["nessie_purchases"]["calls"] == 1 and tools["nessie_purchases"]["fixture_calls"] == 1
    assert tools["serpapi_shopping"]["calls"] == 1 and tools["serpapi_shopping"]["errors"] == 0

    after = client.get("/api/analytics/summary").json()
    assert after["total_runs"] == before["total_runs"] + 1


def test_failed_run_counts_in_error_rate(client):
    class Boom:
        def generate(self, *a, **k):
            from server.runtime.llm import LLMError
            raise LLMError("down")

    use_llm(Boom())
    res = client.post("/api/agents/agent-news-monitor/chat", json={"message": "news"})
    assert res.status_code == 200 and res.json()["status"] == "failed"
    run = client.get(f"/api/runs/{res.json()['run_id']}").json()
    assert run["status"] == "failed" and run["error"]
    s = client.get("/api/analytics/summary?agent_id=agent-news-monitor").json()
    assert s["failed_runs"] >= 1 and 0 < s["error_rate"] <= 1


def test_db_tool_cache_respects_expiry(client):
    from server.hooks import db_cache_get, db_cache_set

    db_cache_set("k1", "serpapi_news", {"a": 1}, 3600)
    assert db_cache_get("k1") == {"a": 1}
    db_cache_set("k2", "serpapi_news", {"a": 2}, -5)
    assert db_cache_get("k2") is None
    db_cache_set("k1", "serpapi_news", {"a": 3}, 3600)  # upsert
    assert db_cache_get("k1") == {"a": 3}


def test_delete_agent_removes_runs_and_protects_demo_agents(client):
    aid = client.post("/api/agents", json={
        "name": "Temp", "template": "news_monitor", "instructions": "i",
        "tools": [{"name": "serpapi_news", "settings": {}}],
    }).json()["id"]
    client.post(f"/api/agents/{aid}/deploy")
    use_llm(ScriptedLLM(LLMTurn("", [FunctionCall("serpapi_news", {"query": "nvidia"}, "c1")], 10, 1), LLMTurn("Done.", [], 10, 1)))
    run_id = client.post(f"/api/agents/{aid}/chat", json={"message": "news"}).json()["run_id"]
    assert client.get(f"/api/runs/{run_id}").status_code == 200

    res = client.delete(f"/api/agents/{aid}")
    assert res.status_code == 200 and res.json()["deleted"] == aid and res.json()["runs_deleted"] == 1
    assert client.get(f"/api/agents/{aid}").status_code == 404
    assert client.get(f"/api/runs/{run_id}").status_code == 404
    assert client.delete(f"/api/agents/{aid}").status_code == 404
    assert client.delete("/api/agents/agent-smart-spend").status_code == 409
    assert client.get("/api/agents/agent-smart-spend").status_code == 200
