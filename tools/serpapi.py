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


def _get(params: dict[str, Any]) -> httpx.Response:
    try:
        return httpx.get(ENDPOINT, params={**params, "api_key": os.environ["SERPAPI_KEY"]}, timeout=TIMEOUT_S)
    except httpx.TimeoutException:
        raise ToolError("SerpApi timed out")
    except httpx.HTTPError:
        raise ToolError("Could not reach SerpApi")


def _reason(res: httpx.Response) -> str:
    """SerpApi's own short error message (never contains the key)."""
    try:
        return str(res.json().get("error") or "")[:160]
    except ValueError:
        return ""


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

    res = _get(params)
    # Live 7:30 PM (web, Court Scout): the model passed location "UT Austin" -> HTTP 400 "Unsupported location".
    # SerpApi only accepts its canonical locations; retry once without it rather than failing the tool.
    if res.status_code == 400 and params.get("location"):
        params = {k: v for k, v in params.items() if k != "location"}
        res = _get(params)
    if res.status_code == 401:
        raise ToolError("SerpApi rejected the API key")
    if res.status_code == 429:
        raise ToolError("SerpApi search limit reached")
    if res.status_code >= 400:
        raise ToolError(f"SerpApi returned HTTP {res.status_code}" + (f": {_reason(res)}" if _reason(res) else ""))
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
# Live Google Shopping results mixed in refurbished units, eBay/Whatnot resale, single replacement earbuds,
# an "EMPTY RETAIL BOX ONLY" listing and different models; those made fake "savings". Keep comparable items only.

RESALE_SOURCES = ("ebay", "whatnot", "poshmark", "mercari", "facebook", "offerup", "depop", "swappa", "craigslist")
NOT_THE_ITEM = (
    "refurbished", "renewed", "pre-owned", "preowned", "used", "open box", "for parts", "box only", "empty",
    "replacement", "case only", "charging case only", "left ", "right ", "single ", "cover", "skin", "sticker",
    "compatible with", "for airpods", "dummy", "replica", "3d model", "download", "receiver -", "dongle only",
    "no mouse", "mouse only",
)
# Lowest price comes from these when any are present (marketplace sellers like "Walmart - X" count as Walmart).
TRUSTED_RETAILERS = (
    "amazon", "walmart", "target", "best buy", "costco", "apple", "b&h", "adorama", "newegg", "sam's club",
    "micro center", "staples", "office depot", "kohl's", "macy's", "home depot", "lowe's", "verizon", "at&t",
)


def _trusted(source: str | None, query: str = "") -> bool:
    """Major retailer, or the brand's own store (query "Logitech MX Master 3S" -> source "Logitech" / "logitech.com").
    Marketplace sellers ("Walmart - 6AVE Electronics") count as the retailer they list on."""
    s = (source or "").lower()
    brand = (query.split() or [""])[0].lower()
    return any(s.startswith(r) for r in TRUSTED_RETAILERS) or (len(brand) >= 3 and s.startswith(brand))


def _not_comparable(query: str, r: dict[str, Any]) -> str | None:
    title = f" {(r.get('title') or '').lower()} "
    source = (r.get("source") or "").lower()
    if r.get("second_hand_condition") or not source or any(m in source for m in RESALE_SOURCES):
        return "used_or_resale"
    if any(w in title for w in NOT_THE_ITEM):
        return "part_or_accessory"
    tokens = [t for t in "".join(c if c.isalnum() else " " for c in query.lower()).split() if t]
    if not all(t in title for t in tokens):
        return "different_product"
    if _num(r.get("extracted_price")) is None:
        return "different_product"
    return None


def _shopping(input: dict[str, Any], settings: dict[str, Any]):
    raw, cached, fixture = serp_request(
        "serpapi_shopping",
        {"engine": "google_shopping", "q": input["query"].strip(), "location": settings.get("location", "Austin, Texas"),
         "gl": "us", "hl": "en"},
    )
    limit = int(input.get("max_results") or 8)
    products, excluded = [], {"used_or_resale": 0, "part_or_accessory": 0, "different_product": 0}
    for r in raw.get("shopping_results") or []:
        why = _not_comparable(input["query"], r)
        if why:
            excluded[why] += 1
            continue
        if len(products) < limit:
            products.append({
                "title": r.get("title"),
                "price": _num(r.get("extracted_price")),
                "price_text": r.get("price"),
                "merchant": r.get("source"),
                "trusted_retailer": _trusted(r.get("source"), input["query"]),
                "rating": r.get("rating"),
                "url": r.get("product_link") or r.get("link"),
            })
    trusted = [p["price"] for p in products if p["price"] is not None and p["trusted_retailer"]]
    prices = trusted or [p["price"] for p in products if p["price"] is not None]
    data = {
        "query": input["query"],
        "products": products,  # new items from named retailers matching the query only
        "lowest_price_from": "trusted retailers" if trusted else "all listed sellers",
        "lowest_price": min(prices) if prices else None,
        "highest_price": max(prices) if prices else None,
        "excluded_listings": excluded,
    }
    if not products:
        # Live 8:37 PM: 'AirPods Pro 2' returned 40 listings, all AirPods Max / resale / refurbished; the agent gave up.
        data["hint"] = (
            f"All {sum(excluded.values())} listings were excluded (used/resale, parts, or a different model). "
            "Try once more with the full product name, e.g. brand + model + generation + variant."
        )
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
        "Returns NEW items from named retailers that match the product name (used, resale, parts and "
        "other models are excluded and only counted). lowest_price prefers major retailers (trusted_retailer). "
        "Quote prices from trusted retailers when available. Use a specific product name, not a category. "
        "If no products come back, retry once with the full product name (see hint)."
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
    # The model's free-text place ("UT Austin") goes into the query; SerpApi's `location` must be a canonical
    # location, so it stays the agent's configured city.
    city = settings.get("location") or "Austin, Texas"
    near = (input.get("location") or "").strip()
    query = input["query"].strip()
    if near and near.lower() not in query.lower() and near.lower() != city.lower():
        query = f"{query} near {near}"
    location = near or city
    raw, cached, fixture = serp_request(
        "serpapi_local_places",
        {"engine": "google_local", "q": query, "location": city, "gl": "us", "hl": "en"},
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
