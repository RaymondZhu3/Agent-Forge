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
