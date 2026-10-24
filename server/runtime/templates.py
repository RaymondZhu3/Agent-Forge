"""Starting configurations for the builder (GET /api/templates)."""

from __future__ import annotations

from server.schemas import AgentCreate, Guardrails, ToolConfig

from .llm import DEFAULT_MODEL

SMART_SPEND = AgentCreate(
    name="Smart Spend",
    template="smart_spend",
    model=DEFAULT_MODEL,
    instructions=(
        "You help the customer understand their spending and find realistic ways to save.\n"
        "1. Read their purchases and bills. Use the totals the tools calculate; never recompute or invent totals.\n"
        "2. Identify the biggest savings opportunities: repeated merchants, recurring bills, and specific products "
        "they bought that may be cheaper elsewhere.\n"
        "3. For specific products, search current prices and compare: state what they paid, where, the lowest price "
        "found and the merchant, and the difference.\n"
        "4. Present at most three opportunities, biggest first, each with the evidence. Call price differences "
        "'potential savings', not guaranteed savings.\n"
        "Never suggest moving money, paying bills or changing accounts."
    ),
    tools=[
        ToolConfig(name="nessie_accounts", settings={}),
        ToolConfig(name="nessie_purchases", settings={}),
        ToolConfig(name="nessie_bills", settings={}),
        ToolConfig(name="serpapi_shopping", settings={"location": "Austin, Texas"}),
    ],
    guardrails=Guardrails(read_only_financial_data=True, max_tool_calls=8, fact_check="flag"),
)

NEWS_MONITOR = AgentCreate(
    name="News Monitor",
    template="news_monitor",
    model=DEFAULT_MODEL,
    instructions=(
        "You produce a concise, source-backed briefing on the topics the user asks about.\n"
        "1. Search news for each topic (one search per topic). Use web search only to check a specific detail.\n"
        "2. Pick the most important stories, removing duplicates of the same event.\n"
        "3. For each: headline, source, publication date if the tool returned one (otherwise say 'date unknown'), "
        "one or two sentences on why it matters, and the original URL.\n"
        "Only report what the retrieved articles say. Never invent stories, dates or quotes."
    ),
    tools=[
        ToolConfig(name="serpapi_news", settings={"when": "7d"}),
        ToolConfig(name="serpapi_web_search", settings={}),
    ],
    guardrails=Guardrails(read_only_financial_data=True, max_tool_calls=6, fact_check="flag"),
)

BLANK = AgentCreate(
    name="New Agent",
    template="blank",
    model=DEFAULT_MODEL,
    instructions="Describe what this agent should do, which tools to use, and how to format its answer.",
    tools=[],
    guardrails=Guardrails(),
)

TEMPLATES: list[AgentCreate] = [SMART_SPEND, NEWS_MONITOR, BLANK]
