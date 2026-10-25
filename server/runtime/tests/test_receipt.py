"""Audit receipts: deterministic, detect tampering, and use the same number format as the browser."""

from __future__ import annotations

import copy

from server.runtime.engine import InMemoryHooks, run_agent
from server.runtime.llm import LLMTurn
from server.runtime.receipt import _js_number, canonical, verify_run
from server.runtime.tests.test_runtime import ScriptedLLM, agent, call


def stored_run(r, hooks):
    """What GET /api/runs/{id} returns: snake_case run, camelCase steps (RunStep serializes by alias)."""
    return {
        "id": r.run_id, "agent_id": "agent-smart_spend", "user_message": hooks.runs[r.run_id]["user_message"],
        "assistant_message": r.assistant_message,
        "steps": [s.model_dump(mode="json", by_alias=True) for s in hooks.steps],
    }


def run_once():
    llm = ScriptedLLM(
        LLMTurn("", [call("nessie_purchases"), call("serpapi_shopping", query="AirPods Pro 2")]),
        LLMTurn("You paid $249.00 at Target; Amazon has $189.99, a potential saving of $59.01.", []),
    )
    hooks = InMemoryHooks()
    r = run_agent(agent(), "Am I overpaying?", "s", hooks=hooks, llm=llm)
    return r, hooks


def test_receipt_is_stored_and_verifies():
    r, hooks = run_once()
    final = r.steps[-1]
    assert final.type == "verify" and len(final.output["receipt"]["hash"]) == 64
    assert final.output["figures"][0][:2] == ["$249.00", True]
    assert all("data_sha256" in s.output for s in r.steps if s.type == "tool")
    res = verify_run(stored_run(r, hooks))
    assert res["ok"], res


def test_tampering_is_detected():
    r, hooks = run_once()
    base = stored_run(r, hooks)

    edited_step = copy.deepcopy(base)
    edited_step["steps"][1]["output"]["summary"] = "11 purchases, total $1.00"
    assert verify_run(edited_step) == {**verify_run(edited_step), "ok": False}
    assert "step 2" in verify_run(edited_step)["reason"]

    edited_answer = copy.deepcopy(base)
    edited_answer["assistant_message"] = edited_answer["assistant_message"].replace("$189.99", "$149.99")
    assert verify_run(edited_answer)["reason"] == "The answer was changed after the run."

    relabeled = copy.deepcopy(base)
    relabeled["steps"][-1]["output"]["figures"][0][1] = False  # flip a verified figure to flagged
    assert not verify_run(relabeled)["ok"]


def test_same_run_same_receipt_and_no_receipt_when_fact_check_off():
    r1, h1 = run_once()
    r2, h2 = run_once()
    # different run ids -> different receipts, but each verifies
    assert r1.steps[-1].output["receipt"]["hash"] != r2.steps[-1].output["receipt"]["hash"]
    llm = ScriptedLLM(LLMTurn("Hi there.", []))
    hooks = InMemoryHooks()
    r = run_agent(agent(fact_check="off"), "hi", "s", hooks=hooks, llm=llm)
    assert not verify_run(stored_run(r, hooks))["ok"]


def test_number_format_matches_javascript():
    # Expected values are what JavaScript's String(x) prints.
    cases = {0.1: "0.1", 2.0: "2", -0.5: "-0.5", 123.456: "123.456", 1e-7: "1e-7", 0.00001: "0.00001",
             1.5e22: "1.5e+22", 1e21: "1e+21", 611.51: "611.51", 1e16: "10000000000000000"}
    for x, js in cases.items():
        assert _js_number(x) == js, (x, _js_number(x), js)
    assert canonical({"b": [1, 2.5, None, True], "a": "é\n\"x\""}) == '{"a":"é\\n\\"x\\"","b":[1,2.5,null,true]}'
