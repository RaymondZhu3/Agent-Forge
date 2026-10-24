"""Check the Gemini, SerpApi and Nessie keys in .env with the cheapest possible calls.

    python -m tools.check_keys            # report only
    python -m tools.check_keys --write    # also set GEMINI_MODEL in .env to the best Flash model found

Gemini: lists models (free). SerpApi: /account.json (does not use a search). Nessie: GET /customers.
Never prints the keys.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import httpx

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

ENV = Path(__file__).resolve().parents[1] / ".env"


def _safe_stdout() -> None:
    """Windows consoles default to cp1252; never crash printing a character they can't show."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def _scrub(text: str) -> str:
    for k in ("GEMINI_API_KEY", "SERPAPI_KEY", "NESSIE_API_KEY"):
        v = os.getenv(k)
        if v:
            text = text.replace(v, "***")
    return text


def _flash_rank(name: str) -> tuple:
    """Prefer stable over preview/exp, full Flash over Lite, then the highest version."""
    m = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
    ver = float(m.group(1)) if m else 0.0
    unstable = any(t in name for t in ("preview", "exp", "-001", "-002", "latest"))
    return (not unstable, "lite" not in name, ver)


def check_gemini() -> list[str]:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        print("Gemini   [x] GEMINI_API_KEY missing")
        return []
    r = httpx.get("https://generativelanguage.googleapis.com/v1beta/models",
                  params={"key": key, "pageSize": 1000}, timeout=20)
    if r.status_code != 200:
        print(f"Gemini   [x] HTTP {r.status_code}: {_scrub(r.text[:200])}")
        return []
    models = [m["name"].removeprefix("models/") for m in r.json().get("models", [])
              if "generateContent" in m.get("supportedGenerationMethods", [])]
    flash = sorted((m for m in models if "flash" in m and "image" not in m and "tts" not in m
                    and "live" not in m and "audio" not in m), key=_flash_rank, reverse=True)
    if not flash:
        print(f"Gemini   [x] key works but no Flash models ({len(models)} models total)")
        return []
    current = os.getenv("GEMINI_MODEL", "")
    print(f"Gemini   [ok] {len(models)} models; Flash: {', '.join(flash[:6])}")
    print(f"         GEMINI_MODEL now {current!r} ({'available' if current in models else 'NOT available'});"
          f" best Flash = {flash[0]!r}")
    return flash


def time_models(models: list[str]) -> str | None:
    """One tiny generate call per model (a few free-tier requests). Returns the fastest that answered."""
    import time

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"], http_options=types.HttpOptions(timeout=30_000))
    best: tuple[float, str] | None = None
    for m in models:
        cfg = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level="low") if m.startswith("gemini-3") else None)
        t0 = time.perf_counter()
        try:
            client.models.generate_content(model=m, contents="Reply with the word ok.", config=cfg)
        except Exception as e:  # noqa: BLE001 - report and move on
            print(f"         {m:24} [x] {type(e).__name__}: {_scrub(str(e))[:90]}")
            continue
        secs = time.perf_counter() - t0
        print(f"         {m:24} {secs:5.1f}s")
        if best is None or secs < best[0]:
            best = (secs, m)
    return best[1] if best else None


def check_serpapi() -> None:
    key = os.getenv("SERPAPI_KEY")
    if not key:
        print("SerpApi  [x] SERPAPI_KEY missing (tools will use demo fixtures)")
        return
    r = httpx.get("https://serpapi.com/account.json", params={"api_key": key}, timeout=20)
    if r.status_code != 200:
        print(f"SerpApi  [x] HTTP {r.status_code}: {_scrub(r.text[:200])}")
        return
    d = r.json()
    print(f"SerpApi  [ok] plan {d.get('plan_name')!r}: {d.get('this_month_usage')} used of "
          f"{d.get('searches_per_month')}/month; searches left: {d.get('total_searches_left')}"
          f" (plan {d.get('plan_searches_left')}, extra credits {d.get('extra_credits', 0)})")


def check_nessie() -> None:
    key = os.getenv("NESSIE_API_KEY")
    if not key:
        print("Nessie   [x] NESSIE_API_KEY missing (tools will use demo fixtures)")
        return
    base = os.getenv("NESSIE_BASE_URL", "http://api.nessieisreality.com").rstrip("/")
    r = httpx.get(f"{base}/customers", params={"key": key}, timeout=20)
    if r.status_code != 200:
        print(f"Nessie   [x] HTTP {r.status_code}: {_scrub(r.text[:200])}")
        return
    customers = r.json()
    if not customers:
        print("Nessie   [ok] key works, but 0 customers: not seeded yet for THIS key "
              "(Nessie data is per key; run `python -m server.seed_nessie` with this key, or share the teammate's key)")
        return
    print(f"Nessie   [ok] {len(customers)} customer(s); the agents use the first one unless customer_id is set:")
    for c in customers[:5]:
        accts = httpx.get(f"{base}/customers/{c['_id']}/accounts", params={"key": key}, timeout=20)
        n = len(accts.json()) if accts.status_code == 200 else "?"
        print(f"         {c['_id']}  {c.get('first_name')} {c.get('last_name')}  ({n} accounts)")


def main() -> int:
    _safe_stdout()
    p = argparse.ArgumentParser()
    p.add_argument("--write", action="store_true", help="set GEMINI_MODEL in .env to the best Flash model")
    p.add_argument("--latency", action="store_true", help="time one tiny call per Flash model; --write picks the fastest")
    a = p.parse_args()
    for fn in (check_serpapi, check_nessie):
        try:
            fn()
        except httpx.HTTPError as e:
            print(f"{fn.__name__[6:].title().replace('Serpapi','SerpApi'):8} [x] cannot reach API: {type(e).__name__}")
    try:
        flash = check_gemini()
    except httpx.HTTPError as e:
        print(f"Gemini   [x] cannot reach API: {type(e).__name__}")
        flash = []
    best = flash[0] if flash else None
    if a.latency and flash:
        print("Gemini latency (tiny prompt):")
        # Live 5:30 PM: every model failed (504/429) and --write still set the untested "best" one.
        best = time_models([m for m in flash if "omni" not in m][:4])
        if best is None:
            print("         no model answered; .env not changed (429 = quota, try another teammate's key)")
    if a.write and best:
        text = ENV.read_text() if ENV.exists() else ""
        line = f"GEMINI_MODEL={best}"
        text = re.sub(r"^GEMINI_MODEL=.*$", line, text, flags=re.M) if "GEMINI_MODEL=" in text else text + f"\n{line}\n"
        ENV.write_text(text)
        print(f"         wrote {line} to .env")
    return 0


if __name__ == "__main__":
    sys.exit(main())
