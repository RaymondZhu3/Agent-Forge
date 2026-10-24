"""Analytics computed from stored rows only (docs/PLAN.md §4). No invented numbers."""

from __future__ import annotations

from collections import defaultdict
from datetime import timezone

from sqlalchemy.orm import Session

from server.db import RunRow, RunStepRow, aware
from server.schemas import AnalyticsSummary, RunsOverTimePoint, ToolAnalytics


def summary(s: Session, agent_id: str | None = None) -> AnalyticsSummary:
    rq = s.query(RunRow)
    sq = s.query(RunStepRow)
    if agent_id:
        rq, sq = rq.filter(RunRow.agent_id == agent_id), sq.filter(RunStepRow.agent_id == agent_id)
    runs = rq.all()

    completed = sum(1 for r in runs if r.status == "completed")
    failed = sum(1 for r in runs if r.status == "failed")
    lat = [r.total_latency_ms for r in runs if r.total_latency_ms is not None]
    costs = [r.estimated_cost_usd for r in runs if r.estimated_cost_usd is not None]

    buckets: dict = defaultdict(lambda: [0, 0])
    for r in runs:
        b = aware(r.started_at).astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
        buckets[b][0] += 1
        buckets[b][1] += 1 if r.status == "failed" else 0

    steps = sq.filter(RunStepRow.type == "tool").all()
    serp = sum(1 for st in steps
               if (st.tool_name or "").startswith("serpapi_") and not st.cached and not st.fixture)
    cache_hits = sq.filter(RunStepRow.cached.is_(True)).count()

    return AnalyticsSummary(
        total_runs=len(runs),
        completed_runs=completed,
        failed_runs=failed,
        error_rate=(failed / (completed + failed)) if (completed + failed) else 0.0,
        avg_latency_ms=(sum(lat) / len(lat)) if lat else None,
        input_tokens=sum(r.input_tokens or 0 for r in runs),
        output_tokens=sum(r.output_tokens or 0 for r in runs),
        estimated_cost_usd=round(sum(costs), 6) if costs else None,
        serpapi_calls=serp,
        cache_hits=cache_hits,
        claims_total=sum(r.claims_total or 0 for r in runs),
        claims_verified=sum(r.claims_verified or 0 for r in runs),
        runs_over_time=[RunsOverTimePoint(bucket=b, runs=v[0], failed=v[1]) for b, v in sorted(buckets.items())],
    )


def by_tool(s: Session, agent_id: str | None = None) -> list[ToolAnalytics]:
    q = s.query(RunStepRow).filter(RunStepRow.type == "tool", RunStepRow.tool_name.isnot(None))
    if agent_id:
        q = q.filter(RunStepRow.agent_id == agent_id)
    agg: dict[str, dict] = defaultdict(lambda: {"calls": 0, "errors": 0, "ms": [], "cache": 0, "fix": 0})
    for st in q.all():
        a = agg[st.tool_name]
        a["calls"] += 1
        a["errors"] += 0 if st.success else 1
        a["ms"].append(st.duration_ms)
        a["cache"] += 1 if st.cached else 0
        a["fix"] += 1 if st.fixture else 0
    return [
        ToolAnalytics(tool_name=n, calls=a["calls"], errors=a["errors"],
                      avg_ms=(sum(a["ms"]) / len(a["ms"])) if a["ms"] else None,
                      cache_hits=a["cache"], fixture_calls=a["fix"])
        for n, a in sorted(agg.items(), key=lambda kv: -kv[1]["calls"])
    ]
