"""Run an agent from the terminal, no server or DB needed.

    python -m server.runtime.cli smart_spend "Find three ways I could reduce my spending."
    python -m server.runtime.cli news_monitor "Brief me on NVIDIA and semiconductor supply chains."
    python -m server.runtime.cli --tools          # list registered tools

Needs GEMINI_API_KEY. Missing SERPAPI_KEY / NESSIE_API_KEY → labeled demo fixtures.
"""

from __future__ import annotations

import argparse
import json
import sys

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from server.schemas import AgentConfig
from tools.registry import registry

from .engine import run_agent
from .templates import TEMPLATES


def main() -> int:
    # Windows consoles default to cp1252; model answers can contain characters it can't encode.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser()
    p.add_argument("template", nargs="?", choices=[t.template for t in TEMPLATES])
    p.add_argument("message", nargs="?")
    p.add_argument("--tools", action="store_true", help="list registered tools and exit")
    p.add_argument("--fact-check", choices=["flag", "block", "off"])
    p.add_argument("--json", action="store_true", help="print the full ChatResponse JSON")
    p.add_argument("--no-file-cache", action="store_true", help="don't persist tool results to tools/.cache/")
    a = p.parse_args()

    if not a.no_file_cache:
        # Share cached SerpApi results across CLI runs so repeated debugging doesn't spend searches.
        from pathlib import Path

        from tools.cache import use_file_cache

        use_file_cache(str(Path(__file__).resolve().parents[2] / "tools" / ".cache" / "cli_cache.json"))

    if a.tools:
        for t in registry.list_metadata():
            print(f"{t['name']:24} {t['source']:26} {t['label']}")
        return 0
    if not a.template or not a.message:
        p.error("template and message are required")

    tpl = next(t for t in TEMPLATES if t.template == a.template)
    agent = AgentConfig(id=f"agent-{tpl.template}", status="deployed", **tpl.model_dump())
    if a.fact_check:
        agent.guardrails.fact_check = a.fact_check

    resp = run_agent(agent, a.message, session_id="cli")
    if a.json:
        print(resp.model_dump_json(indent=2))
        return 0 if resp.status == "completed" else 1

    print(f"\n== {agent.name} | {resp.status} | {resp.total_latency_ms} ms | data: {', '.join(resp.data_modes) or 'none'}")
    for s in resp.steps:
        label = s.tool_name or s.type
        extra = json.dumps(s.output, default=str)[:140] if s.output else ""
        flag = "" if s.success else f"  ERROR: {s.error}"
        print(f"  {s.step:>2}. [{s.type:6}] {label:22} {s.ms:>6} ms  {extra}{flag}")
    print(f"\n{resp.assistant_message or resp.error}\n")
    if resp.claims:
        ok = sum(c.verified for c in resp.claims)
        print(f"Fact-check: {ok}/{len(resp.claims)} figures verified" + (" (blocked)" if resp.blocked else ""))
        for c in resp.claims:
            mark = "ok" if c.verified else " X"
            src = f"step {c.source_step} {c.source_tool} ({c.how})" if c.verified else "no matching tool data"
            print(f"  {mark} {c.text:>12}  {src}")
    if resp.usage.input_tokens is not None:
        print(f"Tokens: {resp.usage.input_tokens} in / {resp.usage.output_tokens} out")
    return 0 if resp.status == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
