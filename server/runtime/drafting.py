"""Experimental platform helpers (Person 1):

- draft_agent(description): one sentence -> a validated AgentCreate (name, instructions, tools, fact-check mode),
  drafted by Gemini from the real tool catalog. The builder shows it for review; nothing is deployed automatically.
- demo_account(agent): the demo customer's accounts, purchases and bills, read with the agent's own Nessie settings,
  so the UI can show the same data the agent sees.
"""

from __future__ import annotations

import json
import re
from typing import Any

from server.schemas import AgentConfig, AgentCreate, Guardrails, ToolConfig
from tools.registry import registry

from .llm import DEFAULT_MODEL, LLM, LLMError

DRAFT_SYSTEM = """You design AI agents for Agent Forge, a platform where every dollar figure an agent states is
fact-checked against its tool results. Given a one-sentence description, reply with ONLY a JSON object:
{"name": short title (2-4 words), "instructions": numbered steps for the agent (3-6 lines, specific, telling it to
use its tools for every price, date or figure and to say so when data is missing), "tools": [tool names from the
catalog that the agent needs], "fact_check": "flag" or "block"}
Use only tools from this catalog:
"""


def _catalog() -> str:
    return "\n".join(f"- {t['name']}: {t['label']} ({t['source']})" for t in registry.list_metadata())


def _json_block(text: str) -> dict[str, Any]:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise LLMError("The model didn't return an agent draft. Try rephrasing the description.")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise LLMError("The model returned an unreadable draft. Try again.") from e


def draft_agent(description: str, llm: LLM | None = None) -> AgentCreate:
    desc = (description or "").strip()
    if len(desc) < 8:
        raise ValueError("Describe the agent in a sentence, e.g. 'finds tennis courts and compares racquet prices'.")
    from .engine import _get_llm  # lazy: tests pass a fake

    client = llm or _get_llm()
    turn = client.generate(DEFAULT_MODEL, DRAFT_SYSTEM + _catalog(), [{"role": "user", "text": desc[:500]}], [])
    d = _json_block(turn.text)
    known = {t["name"] for t in registry.list_metadata()}
    tools = [n for n in dict.fromkeys(d.get("tools") or []) if isinstance(n, str) and n in known]
    if not tools:
        tools = ["serpapi_web_search"]  # every agent needs at least one data source to be audited against
    name = str(d.get("name") or "New Agent").strip()[:60]
    instructions = str(d.get("instructions") or "").strip()[:2000] or f"Help the user with: {desc}"
    fact_check = d.get("fact_check") if d.get("fact_check") in ("flag", "block") else "flag"
    settings = {n: ({"location": "Austin, Texas"} if n in ("serpapi_shopping", "serpapi_local_places", "serpapi_web_search") else {})
                for n in tools}
    return AgentCreate(
        name=name, template="blank", model=DEFAULT_MODEL, instructions=instructions,
        tools=[ToolConfig(name=n, settings=settings[n]) for n in tools],
        guardrails=Guardrails(read_only_financial_data=True, max_tool_calls=8, fact_check=fact_check),
    )


BANK_TOOLS = ("nessie_accounts", "nessie_purchases", "nessie_bills")


def demo_account(agent: AgentConfig) -> dict[str, Any]:
    """Run the agent's own Nessie tools (same settings, e.g. customer_id). Read-only."""
    configured = {t.name: t.settings for t in agent.tools if t.name in BANK_TOOLS}
    if not configured:
        raise ValueError("This agent has no banking tools, so there's no demo account to show.")
    settings = next(iter(configured.values()))  # all three share the customer setting
    out: dict[str, Any] = {"modes": {}}
    for name, key in zip(BANK_TOOLS, ("accounts", "purchases", "bills")):
        tool = registry.get(name)
        res = tool.run({}, configured.get(name, settings)) if tool else None
        out[key] = res.data if res and res.ok else None
        out["modes"][key] = (res.mode if res and res.ok else None)
        if res and not res.ok:
            out.setdefault("errors", {})[key] = res.error
    return out
