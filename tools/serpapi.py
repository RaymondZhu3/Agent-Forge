"""SerpApi tools: Shopping, News, Web Search, Local Places (Person 1).

Docs:
  Google Shopping  https://serpapi.com/google-shopping-api
  Google News      https://serpapi.com/google-news-api
  Google Search    https://serpapi.com/search-api
  Google Local     https://serpapi.com/google-local-api

Each tool normalizes the raw response into one small shape here, so no other
code parses SerpApi JSON. Results are cached (tools.cache) per tool + normalized
query/settings with a per-tool TTL. Cached results stay labeled cached.

Env:
  SERPAPI_KEY         missing -> labeled fixtures
  SERPAPI_MOCK=1      force fixtures
  SERPAPI_CACHE_ONLY=1  never call SerpApi; serve cache or fail (demo backup)
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from .base import Tool, ToolError
from .cache import cache_get, cache_key, cache_set
from .fixtures import serp_fixture

ENDPOINT = "https://serpapi.com/search.json"
TIMEOUT_S = 20

TTL = {
    "serpapi_shopping": 6 * 3600,
    "serpapi_news": 30 * 60,
    "serpapi_web_search": 24 * 3600,
    "serpapi_local_places": 24 * 3600,
}

LOCATION_SETTING = {
    "location": {"type": "string", "description": "Search location, e.g. 'Austin, Texas'", "default": "Austin, Texas"},
}


def _use_fixtures() -> bool:
    return not os.getenv("SERPAPI_KEY") or os.getenv("SERPAPI_MOCK") == "1"


def serp_request(tool_name: str, params: dict[str, Any]) -> tuple[dict[str, Any], bool, bool]:
    """Returns (raw_json, cached, fixture). Never logs or returns the API key."""
    params = {k: v for k, v in params.items() if v not in (None, "")}
    if _use_fixtures():
        return serp_fixture(params["engine"], str(params.get("q", ""))), False, True

    key = cache_key(tool_name, params)
    hit = cache_get(key)
    if hit is not None:
        return hit, True, False
    if os.getenv("SERPAPI_CACHE_ONLY") == "1":
        raise ToolError("No cached result for this search (cache-only mode is on)")

    try:
        res = httpx.get(ENDPOINT, params={**params, "api_key": os.environ["SERPAPI_KEY"]}, timeout=TIMEOUT_S)
    except httpx.TimeoutException:
        raise ToolError("SerpApi timed out")
    except httpx.HTTPError:
        raise ToolError("Could not reach SerpApi")
    if res.status_code == 401:
        raise ToolError("SerpApi rejected the API key")
    if res.status_code == 429:
        raise ToolError("SerpApi search limit reached")
    if res.status_code >= 400:
        raise ToolError(f"SerpApi returned HTTP {res.status_code}")
    data = res.json()
    if data.get("error"):
        # SerpApi returns e.g. "Google hasn't returned any results for this query." — treat as empty, not failure
        if "hasn't returned any results" in data["error"]:
            data = {}
        else:
            raise ToolError(f"SerpApi: {data['error']}")
    cache_set(key, tool_name, data, TTL[tool_name])
    return data, False, False


def _num(v: Any) -> float | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return None


# ---------------- Shopping ----------------

def _shopping(input: dict[str, Any], settings: dict[str, Any]):
    raw, cached, fixture = serp_request(
        "serpapi_shopping",
        {"engine": "google_shopping", "q": input["query"].strip(), "location": settings.get("location", "Austin, Texas"),
         "gl": "us", "hl": "en"},
    )
    products = []
    for r in (raw.get("shopping_results") or [])[: int(input.get("max_results") or 8)]:
        products.append({
            "title": r.get("title"),
            "price": _num(r.get("extracted_price")),
            "price_text": r.get("price"),
            "merchant": r.get("source"),
            "rating": r.get("rating"),
            "url": r.get("product_link") or r.get("link"),
        })
    prices = [p["price"] for p in products if p["price"] is not None]
    data = {
        "query": input["query"],
        "products": products,
        "lowest_price": min(prices) if prices else None,
        "highest_price": max(prices) if prices else None,
    }
    return data, cached, fixture


def _sum_shopping(d: dict[str, Any]) -> str:
    if not d["products"]:
        return f"no products for '{d['query']}'"
    if d["lowest_price"] is None:
        return f"{len(d['products'])} products"
    return f"{len(d['products'])} products, ${d['lowest_price']:.2f}–${d['highest_price']:.2f}"


serpapi_shopping = Tool(
    name="serpapi_shopping",
    label="Shopping Prices",
    source="serpapi:google_shopping",
    category="search",
    description=(
        "Look up current prices for a specific product across online stores (Google Shopping). "
        "Returns product titles, prices, merchants and links. Use a specific product name, not a category."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Specific product name, e.g. 'AirPods Pro 2'"},
            "max_results": {"type": "integer", "description": "Max products to return (default 8)"},
        },
        "required": ["query"],
    },
    settings_schema={"type": "object", "properties": dict(LOCATION_SETTING)},
    run_fn=_shopping,
    summarize_fn=_sum_shopping,
)


# ---------------- News ----------------

def _news(input: dict[str, Any], settings: dict[str, Any]):
    params = {"engine": "google_news", "q": input["query"].strip(), "gl": "us", "hl": "en"}
    if settings.get("when"):
        params["q"] = f"{params['q']} when:{settings['when']}"
    raw, cached, fixture = serp_request("serpapi_news", params)
    stories = []
    for r in raw.get("news_results") or []:
        # Some results are clusters with nested "stories"; take the lead story.
        item = r if r.get("link") else (r.get("highlight") or (r.get("stories") or [{}])[0])
        if not item.get("link"):
            continue
        stories.append({
            "title": item.get("title"),
            "source": (item.get("source") or {}).get("name"),
            "published": item.get("iso_date") or item.get("date"),  # None when unknown — never guessed
            "url": item.get("link"),
            "snippet": item.get("snippet"),
        })
        if len(stories) >= int(input.get("max_results") or 8):
            break
    return {"query": input["query"], "stories": stories}, cached, fixture


serpapi_news = Tool(
    name="serpapi_news",
    label="News",
    source="serpapi:google_news",
    category="search",
    description=(
        "Find recent news stories about a company, product or topic (Google News). "
        "Returns headlines, source, publication date when known, and the original URL."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Topic or company, e.g. 'NVIDIA supply chain'"},
            "max_results": {"type": "integer", "description": "Max stories (default 8)"},
        },
        "required": ["query"],
    },
    settings_schema={"type": "object", "properties": {
        "when": {"type": "string", "description": "Recency filter: 1d, 7d, 1m", "enum": ["1d", "7d", "1m"]},
    }},
    run_fn=_news,
    summarize_fn=lambda d: f"{len(d['stories'])} stories for '{d['query']}'",
)


# ---------------- Web search ----------------

def _web(input: dict[str, Any], settings: dict[str, Any]):
    raw, cached, fixture = serp_request(
        "serpapi_web_search",
        {"engine": "google", "q": input["query"].strip(), "location": settings.get("location"), "gl": "us", "hl": "en"},
    )
    results = [
        {"title": r.get("title"), "url": r.get("link"), "snippet": r.get("snippet"), "source": r.get("source")}
        for r in (raw.get("organic_results") or [])[: int(input.get("max_results") or 6)]
    ]
    ab = raw.get("answer_box") or {}
    answer = ab.get("answer") or ab.get("snippet")
    return {"query": input["query"], "answer_box": answer, "results": results}, cached, fixture


serpapi_web_search = Tool(
    name="serpapi_web_search",
    label="Web Search",
    source="serpapi:google",
    category="search",
    description="General Google web search. Use to verify a detail or find facts other tools don't cover. Returns titles, snippets and URLs.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "description": "Max results (default 6)"},
        },
        "required": ["query"],
    },
    settings_schema={"type": "object", "properties": dict(LOCATION_SETTING)},
    run_fn=_web,
    summarize_fn=lambda d: f"{len(d['results'])} results for '{d['query']}'",
)


# ---------------- Local places ----------------

def _local(input: dict[str, Any], settings: dict[str, Any]):
    location = input.get("location") or settings.get("location") or "Austin, Texas"
    raw, cached, fixture = serp_request(
        "serpapi_local_places",
        {"engine": "google_local", "q": input["query"].strip(), "location": location, "gl": "us", "hl": "en"},
    )
    places = [
        {
            "name": r.get("title"),
            "address": r.get("address"),
            "rating": r.get("rating"),
            "reviews": r.get("reviews"),
            "type": r.get("type"),
            "hours": r.get("hours"),
            "phone": r.get("phone"),
        }
        for r in (raw.get("local_results") or [])[: int(input.get("max_results") or 5)]
    ]
    return {"query": input["query"], "location": location, "places": places}, cached, fixture


serpapi_local_places = Tool(
    name="serpapi_local_places",
    label="Local Places",
    source="serpapi:google_local",
    category="search",
    description="Find nearby stores or places (Google Local) with address, rating, hours and phone.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to find, e.g. 'Best Buy'"},
            "location": {"type": "string", "description": "City or area; defaults to the agent's configured location"},
            "max_results": {"type": "integer", "description": "Max places (default 5)"},
        },
        "required": ["query"],
    },
    settings_schema={"type": "object", "properties": dict(LOCATION_SETTING)},
    run_fn=_local,
    summarize_fn=lambda d: f"{len(d['places'])} places for '{d['query']}' near {d['location']}",
)

SERPAPI_TOOLS = [serpapi_shopping, serpapi_news, serpapi_web_search, serpapi_local_places]
