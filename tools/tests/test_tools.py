"""Tool tests (no network). Run: pytest tools/tests"""

from __future__ import annotations

import httpx
import pytest

from tools import cache as cache_mod
from tools.base import validate, ToolError
from tools.registry import registry


def test_registry_lists_all_tools():
    names = registry.names()
    assert set(names) == {
        "serpapi_shopping", "serpapi_news", "serpapi_web_search", "serpapi_local_places",
        "nessie_accounts", "nessie_purchases", "nessie_bills",
    }
    meta = registry.list_metadata()[0]
    assert set(meta) == {"name", "label", "source", "category", "description", "parameters", "settingsSchema"}


def test_fixtures_are_labeled(monkeypatch):
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    monkeypatch.delenv("NESSIE_API_KEY", raising=False)
    r = registry.get("serpapi_shopping").run({"query": "AirPods Pro 2"})
    assert r.ok and r.fixture and r.mode == "fixture"
    assert r.data["lowest_price"] == 189.99
    b = registry.get("nessie_bills").run({})
    assert b.ok and b.fixture and b.data["recurring_monthly_total"] == 121.98


def test_purchases_totals_are_deterministic(monkeypatch):
    monkeypatch.setenv("NESSIE_MOCK", "1")
    d = registry.get("nessie_purchases").run({}).data
    assert d["purchase_count"] == 11
    assert d["total_spent"] == 611.51
    top = d["by_merchant"][0]
    assert top["merchant"] == "Target" and top["total"] == 294.0
    assert set(d["repeat_merchants"]) == {"Uber Eats", "Starbucks"}
    # no raw account ids reach the model
    assert "demo_acct" not in str(d)


def test_validation():
    schema = registry.get("serpapi_shopping").parameters
    validate({"query": "x"}, schema)
    with pytest.raises(ToolError):
        validate({}, schema)
    with pytest.raises(ToolError):
        validate({"query": 5}, schema)
    with pytest.raises(ToolError):
        validate({"query": "x", "extra": 1}, schema)


class FakeResp:
    def __init__(self, status, payload):
        self.status_code, self._p = status, payload

    def json(self):
        return self._p


def test_serpapi_live_call_is_cached_and_normalized(monkeypatch):
    cache_mod.clear_memory_cache()
    monkeypatch.setenv("SERPAPI_KEY", "test-key")
    monkeypatch.delenv("SERPAPI_MOCK", raising=False)
    calls = []

    def fake_get(url, params, timeout):
        calls.append(params)
        return FakeResp(200, {"shopping_results": [
            {"title": "AirPods Pro 2", "source": "Best Buy", "extracted_price": 199.99, "price": "$199.99", "product_link": "https://bb"},
        ]})

    monkeypatch.setattr(httpx, "get", fake_get)
    tool = registry.get("serpapi_shopping")
    r1 = tool.run({"query": "AirPods Pro 2"}, {"location": "Austin, Texas"})
    r2 = tool.run({"query": "  airpods   PRO 2 "}, {"location": "Austin, Texas"})  # equivalent query
    r3 = tool.run({"query": "AirPods Max"}, {"location": "Austin, Texas"})  # different query
    assert r1.ok and not r1.cached and r1.mode == "live"
    assert r2.ok and r2.cached and r2.mode == "cached"
    assert not r3.cached
    assert len(calls) == 2
    assert r1.data["products"][0] == {"title": "AirPods Pro 2", "price": 199.99, "price_text": "$199.99",
                                      "merchant": "Best Buy", "trusted_retailer": True, "rating": None,
                                      "url": "https://bb"}
    assert "test-key" not in str(r1.to_dict())


def test_serpapi_errors_are_safe(monkeypatch):
    cache_mod.clear_memory_cache()
    monkeypatch.setenv("SERPAPI_KEY", "secret-key")
    monkeypatch.delenv("SERPAPI_MOCK", raising=False)
    monkeypatch.setattr(httpx, "get", lambda *a, **k: FakeResp(429, {}))
    r = registry.get("serpapi_news").run({"query": "x"})
    assert not r.ok and "limit" in r.error and "secret" not in r.error


def test_cache_only_mode(monkeypatch):
    cache_mod.clear_memory_cache()
    monkeypatch.setenv("SERPAPI_KEY", "k")
    monkeypatch.setenv("SERPAPI_CACHE_ONLY", "1")
    monkeypatch.delenv("SERPAPI_MOCK", raising=False)
    monkeypatch.setattr(httpx, "get", lambda *a, **k: pytest.fail("network called in cache-only mode"))
    r = registry.get("serpapi_web_search").run({"query": "x"})
    assert not r.ok and "cache-only" in r.error


def test_custom_cache_backend(monkeypatch):
    store = {}
    cache_mod.set_cache_backend(get=lambda k: store.get(k), set=lambda k, t, r, ttl: store.__setitem__(k, r))
    try:
        monkeypatch.setenv("SERPAPI_KEY", "k")
        monkeypatch.delenv("SERPAPI_MOCK", raising=False)
        monkeypatch.delenv("SERPAPI_CACHE_ONLY", raising=False)
        monkeypatch.setattr(httpx, "get", lambda *a, **k: FakeResp(200, {"local_results": [{"title": "Best Buy"}]}))
        registry.get("serpapi_local_places").run({"query": "Best Buy"})
        assert len(store) == 1 and next(iter(store)).startswith("serpapi_local_places:")
    finally:
        cache_mod.set_cache_backend(cache_mod._mem_get, cache_mod._mem_set)


def test_nessie_unreachable_falls_back_to_labeled_fixtures(monkeypatch):
    """Real-data bug: hackathon network couldn't reach Nessie, so every Smart Spend tool failed."""
    from tools import nessie

    calls = []

    def down(*a, **k):
        calls.append(a)
        raise httpx.ConnectError("no route")

    monkeypatch.setenv("NESSIE_API_KEY", "k")
    monkeypatch.delenv("NESSIE_MOCK", raising=False)
    monkeypatch.delenv("NESSIE_FALLBACK", raising=False)
    monkeypatch.setattr(nessie, "_offline_until", 0.0)
    monkeypatch.setattr(httpx, "get", down)
    r = registry.get("nessie_purchases").run({})
    assert r.ok and r.fixture and r.mode == "fixture"
    n = len(calls)
    assert registry.get("nessie_bills").run({}).mode == "fixture"
    assert len(calls) == n  # stays offline for a minute instead of retrying every call

    monkeypatch.setattr(nessie, "_offline_until", 0.0)
    monkeypatch.setattr(httpx, "get", lambda *a, **k: FakeResp(502, {}))
    assert registry.get("nessie_accounts").run({}).mode == "fixture"  # 5xx counts as unreachable

    monkeypatch.setattr(httpx, "get", down)
    monkeypatch.setattr(nessie, "_offline_until", 0.0)
    monkeypatch.setenv("NESSIE_FALLBACK", "0")
    r = registry.get("nessie_purchases").run({})
    assert not r.ok and "reach Nessie" in (r.error or "")
    monkeypatch.setattr(nessie, "_offline_until", 0.0)


def test_shopping_keeps_only_comparable_new_listings_from_real_results(monkeypatch):
    """Real-data bug: live results made a "$209 saving" from a $40 Whatnot listing (and offered an
    empty box, a single earbud, refurbs and a different mouse as prices)."""
    import json
    from pathlib import Path

    from tools import serpapi

    live = json.loads((Path(__file__).parent / "data" / "serp_shopping_live_2026-10-24.json").read_text())
    monkeypatch.setattr(serpapi, "serp_request", lambda tool, params: ({"shopping_results": live[params["q"]]}, False, False))
    tool = registry.get("serpapi_shopping")

    air = tool.run({"query": "AirPods Pro 2"}).data
    assert {p["merchant"] for p in air["products"]} == {"Walmart - Cellfeee", "Les Appartements de Juju", "VXB.com Bearings"}
    assert air["lowest_price"] == 139.99 and air["lowest_price_from"] == "trusted retailers"
    assert air["excluded_listings"] == {"used_or_resale": 7, "part_or_accessory": 0, "different_product": 1}

    mouse = tool.run({"query": "Logitech MX Master 3S"}).data
    assert mouse["products"] == [] and mouse["lowest_price"] is None


def test_nessie_4xx_error_includes_reason_without_key(monkeypatch):
    """Live: GET purchases returned HTTP 400 and the reason was hidden."""
    from tools import nessie

    monkeypatch.setenv("NESSIE_API_KEY", "secret-key")
    monkeypatch.delenv("NESSIE_MOCK", raising=False)
    monkeypatch.setattr(nessie, "_offline_until", 0.0)

    class R:
        status_code = 400
        text = '{"detail": "bad merchant_id for key secret-key"}'

    monkeypatch.setattr(httpx, "get", lambda *a, **k: R())
    r = registry.get("nessie_accounts").run({}, {"customer_id": "c1"})
    assert not r.ok and "bad merchant_id" in r.error and "secret-key" not in r.error


def test_nessie_defaults_to_the_live_host(monkeypatch):
    """The old default http://api.nessieisreality.com no longer serves the API (BUILD_STATUS gotcha)."""
    from tools import nessie

    monkeypatch.delenv("NESSIE_BASE_URL", raising=False)
    assert nessie._base() == "https://api.nessieisreal.com"



def test_serpapi_bad_location_retries_without_it_and_local_puts_place_in_query(monkeypatch):
    """Live 7:30 PM: model passed location "UT Austin" -> SerpApi HTTP 400, both local searches failed."""
    import httpx

    from tools import serpapi
    monkeypatch.setenv("SERPAPI_KEY", "test")
    monkeypatch.delenv("SERPAPI_MOCK", raising=False)
    monkeypatch.delenv("SERPAPI_CACHE_ONLY", raising=False)
    monkeypatch.setattr(serpapi, "cache_get", lambda k: None)
    monkeypatch.setattr(serpapi, "cache_set", lambda *a, **k: None)
    seen = []

    def fake_get(url, params, timeout):
        seen.append(dict(params))
        req = httpx.Request("GET", url)
        if params.get("location") == "Nowhere, Mars":
            return httpx.Response(400, json={"error": "Unsupported `Nowhere, Mars` location - location parameter."}, request=req)
        return httpx.Response(200, json={"local_results": [{"title": "Caswell Tennis Center", "address": "2312 Shoal Creek Blvd"}]}, request=req)

    monkeypatch.setattr(serpapi.httpx, "get", fake_get)
    data, _, _ = serpapi.serp_request("serpapi_local_places", {"engine": "google_local", "q": "tennis", "location": "Nowhere, Mars"})
    assert data["local_results"] and "location" not in seen[-1] and len(seen) == 2

    seen.clear()
    out, _, _ = serpapi._local({"query": "tennis courts", "location": "UT Austin"}, {"location": "Austin, Texas"})
    assert seen[0]["q"] == "tennis courts near UT Austin" and seen[0]["location"] == "Austin, Texas"
    assert out["places"][0]["name"] == "Caswell Tennis Center"



def test_shopping_with_everything_excluded_tells_the_model_to_refine(monkeypatch):
    """Live 8:37 PM: 40 listings for 'AirPods Pro 2', all AirPods Max / Mercari / refurbished -> 'no products'."""
    from tools import serpapi

    raw = {"shopping_results": [
        {"title": "Apple AirPod Pro Max - New", "source": "Mercari", "extracted_price": 360.0},
        {"title": "Apple AirPods Pro 2nd Gen", "source": "eBay", "extracted_price": 125.0, "second_hand_condition": "pre-owned"},
    ]}
    monkeypatch.setattr(serpapi, "serp_request", lambda *a, **k: (raw, False, False))
    data, _, _ = serpapi._shopping({"query": "AirPods Pro 2"}, {})
    assert data["products"] == [] and "full product name" in data["hint"]
