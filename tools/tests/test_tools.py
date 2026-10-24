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
                                      "merchant": "Best Buy", "rating": None, "url": "https://bb"}
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
