import httpx
import pytest

from tools import serpapi
from tools.base import ToolError


class R:
    def __init__(self, code, data):
        self.status_code, self._d = code, data

    def json(self):
        return self._d


@pytest.fixture(autouse=True)
def live(monkeypatch):
    monkeypatch.setenv("SERPAPI_KEY", "k")
    monkeypatch.delenv("SERPAPI_MOCK", raising=False)
    monkeypatch.delenv("SERPAPI_CACHE_ONLY", raising=False)
    monkeypatch.setattr(serpapi, "cache_get", lambda k: None)
    monkeypatch.setattr(serpapi, "cache_set", lambda *a: None)
    serpapi._last_good.clear()


def test_retries_once_after_timeout(monkeypatch):
    calls = []

    def fake(url, params, timeout):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("slow")
        return R(200, {"ok": 1})

    monkeypatch.setattr(serpapi.httpx, "get", fake)
    assert serpapi.serp_request("serpapi_news", {"engine": "google_news", "q": "x"}) == ({"ok": 1}, False, False)
    assert len(calls) == 2


def test_serves_last_good_when_live_fails(monkeypatch):
    monkeypatch.setattr(serpapi.httpx, "get", lambda *a, **k: R(200, {"ok": 1}))
    serpapi.serp_request("serpapi_news", {"engine": "google_news", "q": "x"})

    def down(*a, **k):
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(serpapi.httpx, "get", down)
    assert serpapi.serp_request("serpapi_news", {"engine": "google_news", "q": "x"}) == ({"ok": 1}, True, False)
    with pytest.raises(ToolError):
        serpapi.serp_request("serpapi_news", {"engine": "google_news", "q": "other"})
