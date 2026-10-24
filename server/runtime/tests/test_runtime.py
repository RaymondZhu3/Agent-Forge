"""Runtime tests with a scripted model (no network, no keys). Run: pytest server/runtime/tests"""

from __future__ import annotations

import pytest

from server.runtime.engine import InMemoryHooks, run_agent
from server.runtime.llm import FunctionCall, LLMError, LLMTurn
from server.runtime.templates import NEWS_MONITOR, SMART_SPEND
from server.runtime.verify import verify_answer
from server.schemas import AgentConfig


@pytest.fixture(autouse=True)
def fixtures_only(monkeypatch):
    monkeypatch.setenv("SERPAPI_MOCK", "1")
    monkeypatch.setenv("NESSIE_MOCK", "1")


def agent(tpl=SMART_SPEND, **guard) -> AgentConfig:
    a = AgentConfig(id=f"agent-{tpl.template}", status="deployed", **tpl.model_dump())
    for k, v in guard.items():
        setattr(a.guardrails, k, v)
    return a


class ScriptedLLM:
    """Returns pre-scripted turns; records what it was offered."""

    def __init__(self, *turns: LLMTurn):
        self.turns = list(turns)
        self.offered: list[list[str]] = []
        self.histories: list[list] = []

    def generate(self, model, system, history, tools):
        self.offered.append([t.name for t in tools])
        self.histories.append(list(history))
        return self.turns.pop(0)


def call(name, **args):
    return FunctionCall(name=name, args=args, id=f"c_{name}")


def test_smart_spend_multi_tool_run_and_fact_check():
    llm = ScriptedLLM(
        LLMTurn("", [call("nessie_purchases")], 100, 10),
        LLMTurn("", [call("serpapi_shopping", query="AirPods Pro 2")], 200, 10),
        LLMTurn(
            "1. AirPods Pro 2: you paid $249.00 at Target. Amazon lists them at $189.99, "
            "a potential saving of $59.01.\n2. You could save about $15.00 a month on coffee.",
            [], 300, 50,
        ),
    )
    hooks = InMemoryHooks()
    r = run_agent(agent(), "Find savings", "s1", hooks=hooks, llm=llm)

    assert r.status == "completed"
    assert [s.type for s in r.steps] == ["llm", "tool", "llm", "tool", "llm", "verify"]
    assert r.steps[1].output["summary"].startswith("11 purchases")
    assert r.steps[1].fixture is True and r.data_modes == ["fixture"]
    assert r.usage.input_tokens == 600 and r.usage.output_tokens == 70

    claims = {c.text: c for c in r.claims}
    assert claims["$249.00"].verified and claims["$249.00"].source_tool == "nessie_purchases"
    assert claims["$189.99"].verified and claims["$189.99"].source_tool == "serpapi_shopping"
    assert claims["$59.01"].verified and claims["$59.01"].how == "difference"
    assert not claims["$15.00"].verified
    assert "AirPods Pro 2: you paid $249.00 at Target" in claims["$249.00"].context

    # hooks saw every step and the finished run
    assert len(hooks.steps) == len(r.steps)
    assert hooks.runs[r.run_id]["status"] == "completed"
    # the model received the real tool result
    tool_msg = llm.histories[1][-1]
    assert tool_msg["role"] == "tool" and tool_msg["results"][0][1]["data"]["total_spent"] == 611.51


def test_block_mode_redacts_unverified_figures():
    llm = ScriptedLLM(
        LLMTurn("", [call("serpapi_shopping", query="AirPods Pro 2")]),
        LLMTurn("Lowest price is $189.99; on Black Friday it will be $149.00.", []),
    )
    r = run_agent(agent(fact_check="block"), "price?", llm=llm)
    assert r.blocked
    assert "$189.99" in r.assistant_message
    assert "$149.00" not in r.assistant_message
    assert "[unverified figure removed]" in r.assistant_message


def test_disabled_and_unknown_tools_are_rejected():
    llm = ScriptedLLM(
        LLMTurn("", [call("serpapi_news", query="x"), call("rm_rf", path="/")]),
        LLMTurn("I couldn't use those tools.", []),
    )
    r = run_agent(agent(), "news?", llm=llm)
    rejected = [s for s in r.steps if s.type == "tool"]
    assert all(not s.success for s in rejected)
    assert "not enabled" in rejected[0].error and "not enabled" in rejected[1].error
    assert r.status == "completed"


def test_invalid_tool_arguments_fail_safely():
    llm = ScriptedLLM(
        LLMTurn("", [call("serpapi_shopping", query="AirPods", evil="x")]),
        LLMTurn("Search failed.", []),
    )
    r = run_agent(agent(), "x", llm=llm)
    step = r.steps[1]
    assert not step.success and "unknown input 'evil'" in step.error


def test_tool_call_limit_forces_final_answer():
    llm = ScriptedLLM(
        LLMTurn("", [call("nessie_purchases"), call("nessie_bills")]),
        LLMTurn("Done with what I have.", []),
    )
    r = run_agent(agent(max_tool_calls=1), "x", llm=llm)
    tool_steps = [s for s in r.steps if s.type == "tool"]
    assert tool_steps[0].success and not tool_steps[1].success
    assert llm.offered[1] == []  # no tools offered after the limit
    assert r.status == "completed"


def test_model_failure_is_a_failed_run_not_an_exception():
    class Broken:
        def generate(self, *a):
            raise LLMError("boom")

    hooks = InMemoryHooks()
    r = run_agent(agent(), "x", hooks=hooks, llm=Broken())
    assert r.status == "failed" and r.error and "boom" not in r.error
    assert hooks.runs[r.run_id]["status"] == "failed"
    assert r.steps[0].success is False


def test_undeployed_agent_fails():
    a = agent()
    a.status = "draft"
    r = run_agent(a, "x", llm=ScriptedLLM())
    assert r.status == "failed"


def test_news_monitor_runs_on_same_runtime():
    llm = ScriptedLLM(
        LLMTurn("", [call("serpapi_news", query="NVIDIA")]),
        LLMTurn("1. Chipmakers race to expand packaging (Demo Wire) https://example.com/news/packaging", []),
    )
    r = run_agent(agent(NEWS_MONITOR), "brief me", llm=llm)
    assert r.status == "completed"
    assert r.steps[1].output["preview"][0]["url"].startswith("https://example.com")
    assert r.claims == []


def test_verify_percent_and_annualized():
    outputs = [(2, "nessie_bills", {"amount": 24.99}), (3, "serpapi_shopping", {"products": [{"price": 249.0}, {"price": 189.99}]})]
    _, claims, _ = verify_answer("Netflix is $24.99 a month, that's $299.88 a year, and 24% cheaper.", outputs, "flag")
    by = {c.text: c for c in claims}
    assert by["$299.88"].verified and by["$299.88"].how == "annualized"
    assert by["24%"].verified


def test_verify_does_not_call_a_cent_off_figure_exact():
    """Live bug: Nessie stored a $109.99 purchase as $109, and the $109.01 saving ($249.00 - $139.99)
    was reported as an exact match of $109 instead of a difference."""
    from server.runtime.verify import verify_answer

    outputs = [
        (2, "nessie_purchases", {"purchases": [{"amount": 249}, {"amount": 109}]}),
        (5, "serpapi_shopping", {"lowest_price": 139.99}),
    ]
    _, claims, _ = verify_answer("Potential savings: $109.01 ($249.00 - $139.99).", outputs, "flag")
    saving = next(c for c in claims if c.text == "$109.01")
    assert saving.verified and saving.how == "difference"
    _, claims, _ = verify_answer("You could save $108.50.", outputs, "flag")
    assert not claims[0].verified


def test_model_is_told_cached_results_are_real_data():
    """Live bug: the agent described cached SerpApi prices as "cached demo data"."""
    from server.runtime.engine import build_system_prompt

    llm = ScriptedLLM(LLMTurn("", [call("nessie_bills")], 1, 1), LLMTurn("done", [], 1, 1))
    run_agent(agent(), "bills?", "s1", llm=llm)
    assert llm.histories[1][-1]["results"][0][1]["real_data"] is False  # fixtures in tests
    prompt = build_system_prompt(agent(), [])
    assert "cached is just a recent copy" in prompt and "both are real data" in prompt


def test_user_supplied_figures_can_be_used_but_are_flagged():
    """Live rehearsal: told only to state tool figures, Gemini refused to use the user's "$199 on Amazon",
    so the fact-check demo had nothing to flag. The model may use user figures; verify still flags them."""
    from server.runtime.engine import build_system_prompt

    assert "the $X you mentioned" in build_system_prompt(agent(), [])
    outputs = [(2, "nessie_purchases", {"purchases": [{"amount": 249}, {"amount": 22}, {"amount": 28}]})]
    text = "You paid $249 at Target. At the $199 you mentioned, you'd have saved $50."
    _, claims, _ = verify_answer(text, outputs, "flag")
    by = {c.text: c.verified for c in claims}
    assert by == {"$249": True, "$199": False, "$50": False}


def test_derived_figures_need_verified_operands_in_the_answer():
    """Live bug (tool removed, block mode): "$249 - $199 = $50" with a made-up $199 kept "$50" as verified,
    because two unrelated purchases summed to $50; "$60" was "verified" as some $5 purchase x 12."""
    outputs = [(2, "nessie_purchases", {"purchases": [{"amount": 249}, {"amount": 28}, {"amount": 22}, {"amount": 5}]})]
    text = "You paid $249. Elsewhere about $199: $249 - $199 = $50 saved, or $60 a year."
    out, claims, blocked = verify_answer(text, outputs, "block")
    by = {c.text: c for c in claims}
    assert by["$249"].verified and not by["$199"].verified
    assert not by["$50"].verified and not by["$60"].verified
    assert "$50" not in out and blocked

    # a real saving between two stated, verified figures still verifies
    outputs.append((4, "serpapi_shopping", {"lowest_price": 139.99}))
    _, claims, _ = verify_answer("Paid $249.00, now $139.99: save $109.01.", outputs, "flag")
    assert {c.text: c.how for c in claims}["$109.01"] == "difference"


def test_bill_plan_switch_saving_verifies_monthly_and_yearly():
    """Smart Spend said "save up to $121.98" on bills; now it names a cheaper plan from a web search."""
    outputs = [
        (3, "nessie_bills", {"recurring_monthly_total": 121.98, "bills": [{"payee": "Netflix", "amount": 24.99},
                                                                         {"payee": "Spotify", "amount": 11.99}]}),
        (5, "serpapi_web_search", {"results": [{"snippet": "Standard with ads: $7.99/month. Standard: $17.99/month."}]}),
    ]
    text = "Netflix: $24.99/mo vs Standard with ads $7.99/mo = $17.00/mo, $204.00 per year."
    _, claims, _ = verify_answer(text, outputs, "flag")
    by = {c.text: (c.verified, c.how) for c in claims}
    assert by["$7.99"] == (True, "exact") and by["$17.00"] == (True, "difference")
    assert by["$204.00"] == (True, "annualized")
    # a yearly figure from an unstated or made-up plan price is not verified
    _, claims, _ = verify_answer("Switch to a $5.99 plan: save $19.00/mo, $228.00 per year.", outputs, "flag")
    assert not any(c.verified for c in claims)


def test_smart_spend_searches_bill_plans():
    from server.runtime.templates import SMART_SPEND

    assert "serpapi_web_search" in {t.name for t in SMART_SPEND.tools}
    assert "web search for that provider's current plans" in SMART_SPEND.instructions
    assert SMART_SPEND.guardrails.max_tool_calls >= 8


def test_saving_cites_the_prices_it_came_from_not_a_coincidental_purchase():
    """Live 5:42 PM: "$11.99/mo vs $6.99/mo = $5.00/mo" was sourced to a $5 coffee in nessie_purchases."""
    outputs = [
        (2, "nessie_bills", {"bills": [{"payee": "Netflix", "amount": 24.99}, {"payee": "Spotify", "amount": 11.99}]}),
        (3, "nessie_purchases", {"purchases": [{"amount": 5}, {"amount": 249}]}),
        (8, "serpapi_web_search", {"results": [{"snippet": "Student $6.99/month. Free $0. Standard $19.99/month."}]}),
    ]
    text = ("Netflix $24.99/mo. Standard is $19.99/month, saving $5.00/month.\n"
            "Spotify: Current $11.99/mo vs $0.00/mo = $11.99/mo saved.\n"
            "Student: Current $11.99/mo vs $6.99/mo = $5.00/mo ($5.00 x 12 = $60.00 per year).\n"
            "You also bought a $5.00 coffee.")
    _, claims, _ = verify_answer(text, outputs, "flag")
    fives = [c for c in claims if c.text == "$5.00"]
    assert [(c.how, c.source_tool) for c in fives[:2]] == [("difference", "nessie_bills")] * 2
    assert fives[-1].how == "exact" and fives[-1].source_tool == "nessie_purchases"  # not a saving sentence
    sixty = next(c for c in claims if c.text == "$60.00")
    assert sixty.verified and sixty.how == "annualized" and sixty.source_tool == "nessie_bills"
    elevens = [c for c in claims if c.text == "$11.99"]
    assert all(c.how == "exact" and c.source_tool == "nessie_bills" for c in elevens)
