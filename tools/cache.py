"""Tool cache hooks (Person 1 calls, Person 2 implements with the tool_cache table).

Default is an in-memory TTL cache so tools work before the DB exists.
Person 2 wires the DB version at startup:

    from tools.cache import set_cache_backend
    set_cache_backend(get=db_cache_get, set=db_cache_set)

where
    db_cache_get(key: str) -> dict | None            # None if missing or expired
    db_cache_set(key: str, tool_name: str, result: dict, ttl_seconds: int) -> None
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Callable

CacheGet = Callable[[str], "dict[str, Any] | None"]
CacheSet = Callable[[str, str, "dict[str, Any]", int], None]

_mem: dict[str, tuple[float, dict[str, Any]]] = {}


def _mem_get(key: str) -> dict[str, Any] | None:
    hit = _mem.get(key)
    if not hit:
        return None
    expires, value = hit
    if expires < time.time():
        _mem.pop(key, None)
        return None
    return value


def _mem_set(key: str, tool_name: str, result: dict[str, Any], ttl_seconds: int) -> None:
    _mem[key] = (time.time() + ttl_seconds, result)


_get: CacheGet = _mem_get
_set: CacheSet = _mem_set


def set_cache_backend(get: CacheGet, set: CacheSet) -> None:  # noqa: A002
    global _get, _set
    _get, _set = get, set


def clear_memory_cache() -> None:
    _mem.clear()


def use_file_cache(path: str) -> None:
    """Persist the cache to a JSON file so separate CLI runs share it (CLI only; the server uses the DB).

    With SERPAPI_CACHE_ONLY=1, expired entries are still served, so a demo can replay old results.
    """
    import os
    from pathlib import Path

    p = Path(path)

    def _load() -> dict[str, Any]:
        try:
            return json.loads(p.read_text())
        except (OSError, ValueError):
            return {}

    def _fget(key: str) -> dict[str, Any] | None:
        hit = _load().get(key)
        if not hit:
            return None
        if hit["expires"] < time.time() and os.getenv("SERPAPI_CACHE_ONLY") != "1":
            return None
        return hit["result"]

    def _fset(key: str, tool_name: str, result: dict[str, Any], ttl_seconds: int) -> None:
        data = _load()
        data[key] = {"expires": time.time() + ttl_seconds, "tool": tool_name, "result": result}
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        tmp.replace(p)

    set_cache_backend(get=_fget, set=_fset)


def cache_key(tool_name: str, params: dict[str, Any]) -> str:
    """Canonical key: tool name + normalized params (case/whitespace-insensitive strings)."""
    norm = {
        k: (" ".join(v.lower().split()) if isinstance(v, str) else v)
        for k, v in sorted(params.items())
        if v not in (None, "")
    }
    digest = hashlib.sha256(json.dumps(norm, sort_keys=True).encode()).hexdigest()[:32]
    return f"{tool_name}:{digest}"


def cache_get(key: str) -> dict[str, Any] | None:
    return _get(key)


def cache_set(key: str, tool_name: str, result: dict[str, Any], ttl_seconds: int) -> None:
    _set(key, tool_name, result, ttl_seconds)
