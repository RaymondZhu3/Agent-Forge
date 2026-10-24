"""Fact-check step: every money amount / percentage in the final answer must be
backed by data a tool actually returned during this run.

A figure is verified if it equals (±1 cent) a number in the tool outputs, or a
difference or sum of two such numbers (e.g. a saving = paid − found price), or a
monthly figure ×12 (annualized). Anything else is unverified.

Deterministic and cheap: no model call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from server.schemas import Claim

MONEY_RE = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)")
PCT_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s?%")
TOL = 0.011
MAX_VALUES = 400


@dataclass
class Evidence:
    value: float
    step: int
    tool: str


# Only numbers under money-like keys count as evidence, so counts, days of month,
# ratings etc. can't accidentally "verify" a figure.
MONEY_KEY_RE = re.compile(r"price|amount|total|balance|cost|spent|saving|fee|payment|lowest|highest", re.I)


def collect_numbers(data: Any, step: int, tool: str, out: list[Evidence], key: str = "") -> None:
    if isinstance(data, bool) or data is None:
        return
    if isinstance(data, (int, float)):
        if MONEY_KEY_RE.search(key):
            out.append(Evidence(float(data), step, tool))
    elif isinstance(data, str):
        if "$" in data:
            for m in MONEY_RE.finditer(data):
                try:
                    out.append(Evidence(float(m.group(1).replace(",", "")), step, tool))
                except ValueError:
                    pass
    elif isinstance(data, dict):
        for k, v in data.items():
            collect_numbers(v, step, tool, out, str(k))
    elif isinstance(data, (list, tuple)):
        for v in data:
            collect_numbers(v, step, tool, out, key)


BOUNDARY_RE = re.compile(r"[!?\n]|\.(?!\d)")


def _sentence(text: str, start: int, end: int) -> str:
    """The sentence/line containing [start, end); decimal points don't count as boundaries."""
    left = 0
    for m in BOUNDARY_RE.finditer(text, 0, start):
        left = m.end()
    m = BOUNDARY_RE.search(text, end)
    right = m.start() + (1 if m and m.group(0) != "\n" else 0) if m else len(text)
    return text[left:right].strip(" *-•\t")[:240]


def _match(value: float, evidence: list[Evidence], percent: bool) -> tuple[Evidence | None, str | None]:
    for e in evidence:
        if abs(e.value - value) <= TOL:
            return e, "exact"
    if percent:
        for a in evidence:
            if a.value <= 0:
                continue
            for b in evidence:
                if a is b:
                    continue
                if abs((a.value - b.value) / a.value * 100 - value) <= 0.6:
                    return a, "difference"
        return None, None
    for e in evidence:
        if abs(e.value * 12 - value) <= TOL * 12:
            return e, "annualized"
    vals = evidence[:MAX_VALUES]
    for i, a in enumerate(vals):
        for b in vals[i + 1:]:
            if abs(abs(a.value - b.value) - value) <= TOL:
                return a, "difference"
            if abs(a.value + b.value - value) <= TOL:
                return a, "sum"
    return None, None


def find_claims(answer: str, evidence: list[Evidence]) -> list[tuple[Claim, tuple[int, int]]]:
    found: list[tuple[Claim, tuple[int, int]]] = []
    seen: set[tuple[str, int]] = set()
    for regex, percent in ((MONEY_RE, False), (PCT_RE, True)):
        for m in regex.finditer(answer):
            key = (m.group(0), m.start())
            if key in seen:
                continue
            seen.add(key)
            value = float(m.group(1).replace(",", ""))
            ev, how = _match(value, evidence, percent)
            found.append((
                Claim(
                    text=m.group(0).strip(),
                    context=_sentence(answer, m.start(), m.end()),
                    verified=ev is not None,
                    source_step=ev.step if ev else None,
                    source_tool=ev.tool if ev else None,
                    how=how,
                ),
                (m.start(), m.end()),
            ))
    found.sort(key=lambda c: c[1][0])
    return found


def verify_answer(answer: str, tool_outputs: Iterable[tuple[int, str, Any]], mode: str) -> tuple[str, list[Claim], bool]:
    """tool_outputs: (step, tool_name, data). Returns (answer, claims, blocked)."""
    if mode == "off":
        return answer, [], False
    evidence: list[Evidence] = []
    for step, tool, data in tool_outputs:
        collect_numbers(data, step, tool, evidence)
    found = find_claims(answer, evidence)
    claims = [c for c, _ in found]
    blocked = False
    if mode == "block":
        for c, (s, e) in sorted(found, key=lambda x: x[1][0], reverse=True):
            if not c.verified:
                answer = answer[:s] + "[unverified figure removed]" + answer[e:]
                blocked = True
    return answer, claims, blocked
