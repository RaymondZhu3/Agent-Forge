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


def test_unhashable_tool_data_skips_the_receipt_but_not_the_answer(monkeypatch):
    """Receipts are best-effort: a NaN in tool data must not fail the run."""
    import server.runtime.engine as E

    monkeypatch.setattr(E, "data_hash", lambda d: (_ for _ in ()).throw(ValueError("nan")))
    monkeypatch.setattr(E, "receipt_chain", lambda *a: (_ for _ in ()).throw(ValueError("nan")))
    r, _ = run_once()
    assert r.status == "completed" and r.assistant_message
    assert "receipt" not in r.steps[-1].output


def test_signed_receipt_catches_a_rewritten_chain(monkeypatch):
    """With RECEIPT_SECRET, someone who edits the answer AND recomputes the whole chain still fails the signature."""
    from server.runtime.receipt import chain

    monkeypatch.setenv("RECEIPT_SECRET", "test-secret")
    r, hooks = run_once()
    rc = r.steps[-1].output["receipt"]
    assert rc["sig"] and len(rc["key_id"]) == 8
    run = stored_run(r, hooks)
    ok = verify_run(run)
    assert ok["ok"] and ok["signature"] == "valid"

    # the attacker edits the answer and recomputes every hash, but can't sign without the key
    forged = copy.deepcopy(run)
    forged["assistant_message"] = forged["assistant_message"].replace("$189.99", "$149.99")
    redo = chain(forged["id"], forged["agent_id"], forged["user_message"], forged["steps"], forged["assistant_message"])
    forged["steps"][-1]["output"]["receipt"] = {**forged["steps"][-1]["output"]["receipt"], "hash": redo["hash"], "steps": redo["steps"]}
    res = verify_run(forged)
    assert not res["ok"] and res["signature"] == "invalid" and "signature" in res["reason"]

    # without the key, a signed receipt is reported as unchecked rather than valid
    monkeypatch.delenv("RECEIPT_SECRET")
    assert verify_run(run)["signature"] == "unchecked"


def test_unsigned_without_a_secret(monkeypatch):
    monkeypatch.delenv("RECEIPT_SECRET", raising=False)
    r, hooks = run_once()
    assert "sig" not in r.steps[-1].output["receipt"]
    assert verify_run(stored_run(r, hooks))["signature"] == "unsigned"
