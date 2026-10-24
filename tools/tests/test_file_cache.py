"""File-backed CLI cache (no network)."""

from __future__ import annotations

import time

from tools import cache as cache_mod


def test_file_cache_persists_and_replays_expired_in_cache_only(tmp_path, monkeypatch):
    path = tmp_path / "c.json"
    try:
        cache_mod.use_file_cache(str(path))
        cache_mod.cache_set("serpapi_news:abc", "serpapi_news", {"stories": [1]}, ttl_seconds=60)
        # A fresh backend on the same file (= a new CLI process) sees the entry.
        cache_mod.use_file_cache(str(path))
        assert cache_mod.cache_get("serpapi_news:abc") == {"stories": [1]}

        # Expire it: normal mode misses, cache-only mode still replays it.
        monkeypatch.setattr(time, "time", lambda: 10**12)
        monkeypatch.delenv("SERPAPI_CACHE_ONLY", raising=False)
        assert cache_mod.cache_get("serpapi_news:abc") is None
        monkeypatch.setenv("SERPAPI_CACHE_ONLY", "1")
        assert cache_mod.cache_get("serpapi_news:abc") == {"stories": [1]}
    finally:
        cache_mod.set_cache_backend(get=cache_mod._mem_get, set=cache_mod._mem_set)
