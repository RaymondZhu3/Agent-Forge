"""Fact-check step: every money amount / percentage in the final answer must be
backed by data a tool actually returned during this run.

A figure is verified if it equals (±1 cent) a number in the tool outputs, or a
difference or sum of two such numbers (e.g. a saving = paid − found price), or a
monthly figure or monthly difference ×12 (annualized). Anything else is unverified.

Deterministic and cheap: no model call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from server.schemas import Claim

MONEY_RE = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)")
PCT_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s?%")
TOL = 0.0051  # half a cent: with whole-dollar Nessie data, 0.011 let $109.01 "exactly" match $109
MAX_VALUES = 400


@dataclass
class Evidence:
    value: float
    step: int
    tool: str
    item: Any = None  # the record the number sits in (a listing, purchase, bill, search result)
    field: str = ""


# What an evidence card may show from a tool record: descriptive fields only, no ids or account numbers.
ITEM_FIELDS = ("title", "name", "description", "merchant", "payee", "source", "seller", "price", "price_text", "amount",
               "payment_amount", "lowest_price", "total_spent", "recurring_monthly_total", "purchase_date", "date",
               "published", "snippet", "url", "link", "query")


def trim_item(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    out = {}
    for k in ITEM_FIELDS:
        v = item.get(k)
        if isinstance(v, (str, int, float)) and not isinstance(v, bool):
            out[k] = v[:220] if isinstance(v, str) else v
    return out or None


# Only numbers under money-like keys count as evidence, so counts, days of month,
# ratings etc. can't accidentally "verify" a figure.
MONEY_KEY_RE = re.compile(r"price|amount|total|balance|cost|spent|saving|fee|payment|lowest|highest", re.I)


def collect_numbers(data: Any, step: int, tool: str, out: list[Evidence], key: str = "", parent: Any = None) -> None:
    if isinstance(data, bool) or data is None:
        return
    if isinstance(data, (int, float)):
        if MONEY_KEY_RE.search(key):
            out.append(Evidence(float(data), step, tool, parent, key))
    elif isinstance(data, str):
        if "$" in data:
            for m in MONEY_RE.finditer(data):
                try:
                    out.append(Evidence(float(m.group(1).replace(",", "")), step, tool, parent, key))
                except ValueError:
                    pass
    elif isinstance(data, dict):
        for k, v in data.items():
            collect_numbers(v, step, tool, out, str(k), data)
    elif isinstance(data, (list, tuple)):
        for v in data:
            collect_numbers(v, step, tool, out, key, parent)


SAVING_RE = re.compile(r"sav|=|differen|less|cheaper|lower", re.I)
# "Amazon.com" and "$1.50" are not sentence ends: a dot followed by a letter or digit isn't a boundary.
BOUNDARY_RE = re.compile(r"[!?\n]|\.(?![\w])")


def _sentence(text: str, start: int, end: int) -> str:
    """The sentence/line containing [start, end); decimal points don't count as boundaries."""
    left = 0
    for m in BOUNDARY_RE.finditer(text, 0, start):
        left = m.end()
    m = BOUNDARY_RE.search(text, end)
    right = m.start() + (1 if m and m.group(0) != "\n" else 0) if m else len(text)
    return text[left:right].strip(" *-•\t")[:240]


WORD_RE = re.compile(r"[a-z][a-z0-9&']{2,}")
STOP = {"the", "and", "for", "you", "your", "with", "this", "that", "from", "are", "per", "month", "plan", "price", "plans"}


def _words(x: Any) -> set[str]:
    text = " ".join(str(v) for v in x.values() if isinstance(v, str)) if isinstance(x, dict) else str(x or "")
    return {w for w in WORD_RE.findall(text.lower()) if w not in STOP}


def _best_exact(value: float, evidence: list[Evidence], context: str = "") -> Evidence | None:
    """Exact match. When several records hold the same number: prefer the one that talks about the same thing as
    the sentence (live: Spotify's "$10.99" was credited to the AT&T search because that came first), then a specific
    item (listing, purchase, bill) over a summary total ("spent at Amazon: $109.99")."""
    hits = [e for e in evidence if abs(e.value - value) <= TOL]
    if len(hits) <= 1:
        return hits[0] if hits else None
    ctx = _words(context)
    def score(e: Evidence) -> tuple[int, int]:
        specific = int(isinstance(e.item, dict) and any(e.item.get(k) for k in ("title", "name", "description", "payee")))
        return (len(ctx & _words(e.item)) if ctx else 0, specific)
    return max(hits, key=score)  # max() keeps the first of equal scores


def _match(value: float, evidence: list[Evidence], percent: bool) -> tuple[Evidence | None, str | None, Evidence | None]:
    e = _best_exact(value, evidence)
    if e is not None:
        return e, "exact", None
    if percent:
        for a in evidence:
            if a.value <= 0:
                continue
            for b in evidence:
                if a is b:
                    continue
                if abs((a.value - b.value) / a.value * 100 - value) <= 0.6:
                    return a, "difference", b
        return None, None, None
    for e in evidence:
        if abs(e.value * 12 - value) <= TOL * 12:
            return e, "annualized", None
    vals = evidence[:MAX_VALUES]
    for i, a in enumerate(vals):
        for b in vals[i + 1:]:
            if abs(abs(a.value - b.value) - value) <= TOL:
                return a, "difference", b
            if abs(a.value + b.value - value) <= TOL:
                return a, "sum", b
    # Yearly saving from a plan switch: ($24.99 - $7.99) x 12 = $204.00. Only between stated, verified figures.
    for i, a in enumerate(vals):
        for b in vals[i + 1:]:
            if abs(abs(a.value - b.value) * 12 - value) <= TOL * 12:
                return a, "annualized", b
    return None, None, None


def find_claims_detailed(answer: str, evidence: list[Evidence]) -> tuple[list[tuple[Claim, tuple[int, int]]], list[dict | None]]:
    """Two passes. 1) exact matches against tool data. 2) derived money figures (difference, sum, x12) only from
    figures the answer itself states AND that passed pass 1. Live bug: "$249 - $199 = $50" (with $199 made up)
    was "verified" because two unrelated purchases happened to sum to $50."""
    hits: list[tuple[re.Match, bool, float]] = []
    seen: set[tuple[str, int]] = set()
    for regex, percent in ((MONEY_RE, False), (PCT_RE, True)):
        for m in regex.finditer(answer):
            key = (m.group(0), m.start())
            if key in seen:
                continue
            seen.add(key)
            hits.append((m, percent, float(m.group(1).replace(",", ""))))

    exact: dict[int, Evidence] = {}
    for i, (m, percent, value) in enumerate(hits):
        ev = _best_exact(value, evidence, _sentence(answer, m.start(), m.end()))
        if ev is not None:
            exact[i] = ev
    how_of = {i: "exact" for i in exact}
    partner: dict[int, Evidence | None] = {}

    # A saving that also equals some unrelated tool number (a $5 purchase) should cite the prices it came from:
    # "$11.99/mo vs $6.99/mo = $5.00" is a difference, not "the $5 coffee". Live 5:42 PM bill-savings run.
    money = [i for i in exact if not hits[i][1]]
    for i in money:
        m, _, value = hits[i]
        if not SAVING_RE.search(_sentence(answer, m.start(), m.end())):
            continue
        best: tuple[int, int] | None = None
        for x in money:
            for y in money:
                a, b = hits[x][2], hits[y][2]
                if x >= y or i in (x, y) or hits[x][0].start() > m.start() or hits[y][0].start() > m.start():
                    continue  # operands must be other figures stated before this one
                if min(a, b) <= TOL or abs(a - value) <= TOL or abs(b - value) <= TOL:
                    continue
                if abs(abs(a - b) - value) <= TOL:
                    dist = 2 * m.start() - hits[x][0].start() - hits[y][0].start()
                    if best is None or dist < best[0]:
                        best = (dist, x if a >= b else y)
        if best is not None:
            src = exact[best[1]]
            other = next((x for x in money if x not in (best[1], i) and hits[x][0].start() < m.start()
                          and abs(abs(hits[best[1]][2] - hits[x][2]) - value) <= TOL), None)
            partner[i] = exact[other] if other is not None else None
            exact[i] = Evidence(value, src.step, src.tool, src.item, src.field)
            how_of[i] = "difference"

    stated: list[Evidence] = []
    for i, ev in exact.items():
        if not hits[i][1] and all(abs(x.value - ev.value) > TOL for x in stated):
            stated.append(Evidence(hits[i][2], ev.step, ev.tool, ev.item, ev.field))

    found: list[tuple[Claim, tuple[int, int]]] = []
    details: list[dict | None] = []
    for i, (m, percent, value) in enumerate(hits):
        if i in exact:
            ev, how, other = exact[i], how_of[i], partner.get(i)
        elif percent:
            ev, how, other = _match(value, evidence, True)
        else:
            ev, how, other = _match(value, stated, False)
        details.append(_detail(ev, how, other))
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
    order = sorted(range(len(found)), key=lambda k: found[k][1][0])
    return [found[k] for k in order], [details[k] for k in order]


def find_claims(answer: str, evidence: list[Evidence]) -> list[tuple[Claim, tuple[int, int]]]:
    return find_claims_detailed(answer, evidence)[0]


def _ref(e: Evidence) -> dict[str, Any]:
    return {"value": e.value, "step": e.step, "tool": e.tool, "item": trim_item(e.item)}


def _detail(ev: Evidence | None, how: str | None, other: Evidence | None) -> dict | None:
    """Why a figure verified: the record it matched, or the two figures it was computed from."""
    if ev is None:
        return None
    if how == "exact" or other is None:
        d = {"kind": how or "exact", **_ref(ev)}
        if how == "annualized":
            d["op"] = "x12"
        return d
    return {"kind": how, "op": "+" if how == "sum" else ("-x12" if how == "annualized" else "-"), "operands": [_ref(ev), _ref(other)]}


def explain_figures(answer: str, tool_outputs: Iterable[tuple[int, str, Any]]) -> list[dict | None]:
    """Evidence per figure, in the same order as verify_answer's claims."""
    evidence: list[Evidence] = []
    for step, tool, data in tool_outputs:
        collect_numbers(data, step, tool, evidence)
    return find_claims_detailed(answer, evidence)[1]


USER_SOURCE = "user_message"


def mark_user_figures(claims: list[Claim], message: str) -> None:
    """Unverified figures the user typed themselves stay unverified, but are labeled as the user's (source_tool =
    "user_message"), so the platform doesn't try to "correct" the user and the UI can say where they came from."""
    user = [float(m.group(1).replace(",", "")) for r in (MONEY_RE, PCT_RE) for m in r.finditer(message or "")]
    if not user:
        return

    def val(c: Claim) -> float | None:
        try:
            return float(re.sub(r"[^\d.]", "", c.text.replace(",", "")))
        except ValueError:
            return None

    # Figures derived from the user's number count as the user's too: "$249 paid - the $199 you mentioned = $50".
    checked = [x for c in claims if c.verified and (x := val(c)) is not None]
    values = list(user)
    for u in user:
        for a in checked:
            values += [abs(a - u), a + u, abs(a - u) * 12]
    for c in claims:
        if c.verified:
            continue
        v = val(c)
        if v is not None and any(abs(v - u) <= TOL * 12 for u in values):
            c.source_tool = USER_SOURCE


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
