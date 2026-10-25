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


# Live 5:34 PM: "$249.00 − $199.00" printed as "$249.00 ? $199.00" on a cp1252 console (bad for the demo video).
_ASCII = str.maketrans({"\u2212": "-", "\u2013": "-", "\u2014": "-", "\u2018": "'", "\u2019": "'",
                        "\u201c": '"', "\u201d": '"', "\u2026": "...", "\u00d7": "x", "\u2192": "->"})


def _console_text(text: str, stream=None) -> str:
    """Swap typographic characters for ASCII unless the console is UTF-8. Live 5:48 PM: piped through
    Tee-Object, a cp1252 en dash (0x96) was read back by PowerShell's OEM codepage as "u-circumflex"."""
    enc = (getattr(stream or sys.stdout, "encoding", None) or "utf-8").lower().replace("-", "")
    return text if enc in ("utf8", "utf8sig") else text.translate(_ASCII)


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
    p.add_argument("--without", action="append", default=[], metavar="TOOL",
                   help="remove a tool from the agent (repeatable), e.g. --without serpapi_shopping")
    p.add_argument("--instructions", help="replace the template's instructions (rehearse a custom-built agent)")
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
    unknown = set(a.without) - {t.name for t in agent.tools}
    if unknown:
        p.error(f"{agent.name} has no tool(s): {', '.join(sorted(unknown))}")
    agent.tools = [t for t in agent.tools if t.name not in a.without]
    if a.instructions:
        agent.instructions = a.instructions

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
    drafts = [s for s in resp.steps if s.type == "verify" and isinstance(s.output, dict) and s.output.get("draft")]
    fixes = [s for s in resp.steps if s.type == "verify" and isinstance(s.input, dict) and s.input.get("stage") == "corrected"]
    if drafts:
        print(f"\n-- Draft (before self-correction; not shown to the user) --\n{_console_text(drafts[0].output['draft'])}")
        if fixes:
            o = fixes[0].output
            print(f"\n-- Self-correction: fixed {', '.join(o['fixed']) or 'nothing'}"
                  f"{'' if o['used_correction'] else ' (correction was worse; kept the draft)'} --")
        else:
            print("\n-- Self-correction failed; kept the draft --")
    print(f"\n{_console_text(resp.assistant_message or resp.error or '')}\n")
    if resp.claims:
        ok = sum(c.verified for c in resp.claims)
        print(f"Fact-check: {ok}/{len(resp.claims)} figures verified" + (" (blocked)" if resp.blocked else ""))
        shown = set()
        for c in resp.claims:
            if (c.text, c.verified) in shown:  # a figure repeated in the answer is one line here
                continue
            shown.add((c.text, c.verified))
            mark = "ok" if c.verified else " X"
            src = (f"step {c.source_step} {c.source_tool} ({c.how})" if c.verified
                   else "from the user's message; no tool confirms it" if c.source_tool == "user_message"
                   else "no matching tool data")
            print(f"  {mark} {c.text:>12}  {src}")
    if resp.usage.input_tokens is not None:
        print(f"Tokens: {resp.usage.input_tokens} in / {resp.usage.output_tokens} out")
    return 0 if resp.status == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
