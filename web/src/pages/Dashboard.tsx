import { Activity, Gauge, RefreshCw, ShieldCheck, Timer, Coins, Cpu, Database, Search } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { RunsChart, ToolBars } from "../components/Charts";
import { EmptyState, ErrorBanner, Skeleton, StatusPill } from "../components/ui";
import { api } from "../lib/api";
import { fmtCompact, fmtDateTime, fmtInt, fmtMs, fmtPct, fmtUsd, relTime, shortId } from "../lib/format";
import { useAsync, useDocumentTitle } from "../lib/hooks";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

function Kpi({ icon, label, value, sub, tone }: { icon: ReactNode; label: string; value: ReactNode; sub?: ReactNode; tone?: "err" | "ok" }) {
  return (
    <div className="kpi">
      <div className="kpi-label">{icon}{label}</div>
      <div className={`kpi-value mono${tone ? " " + tone + "-t" : ""}`}>{value}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </div>
  );
}

export default function Dashboard() {
  useDocumentTitle("Observability");
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const agentId = params.get("agent") ?? "";
  const [status, setStatus] = useState<"" | "completed" | "failed" | "running">("");
  const [auto, setAuto] = useState(true);

  const agents = useAsync(() => api.agents(), []);
  const summary = useAsync(() => api.summary(agentId || undefined), [agentId]);
  const tools = useAsync(() => api.toolStats(agentId || undefined), [agentId]);
  const runs = useAsync(() => api.runs({ agent_id: agentId || undefined, limit: 50 }), [agentId]);

  const refresh = () => { summary.reload(); tools.reload(); runs.reload(); };
  useEffect(() => {
    if (!auto) return;
    const t = setInterval(refresh, 15000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auto, agentId]);

  const names = useMemo(() => new Map((agents.data ?? []).map((a) => [a.id, a.name])), [agents.data]);
  const s = summary.data;
  const shown = (runs.data ?? []).filter((r) => !status || r.status === status);
  const loading = summary.loading && !s;
  const err = summary.error ?? runs.error ?? tools.error;

  return (
    <div className="page wide">
      <header className="page-head">
        <div>
          <div className="eyebrow mono">OBSERVABILITY</div>
          <h1>Runs &amp; performance</h1>
        </div>
        <div className="head-actions">
          <label className="select-inline">
            <span className="sr">Agent</span>
            <select value={agentId} onChange={(e) => setParams(e.target.value ? { agent: e.target.value } : {})} aria-label="Filter by agent">
              <option value="">All agents</option>
              {agents.data?.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </label>
          <label className="check"><input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} /> Auto-refresh</label>
          <button className="btn ghost sm" onClick={refresh}><RefreshCw size={13} className={summary.loading || runs.loading ? "spin" : ""} /> Refresh</button>
        </div>
      </header>

      {err && <ErrorBanner message={err} onRetry={refresh} title="Couldn't load analytics" />}

      <div className="kpis">
        {loading ? [0, 1, 2, 3, 4, 5].map((i) => <div key={i} className="kpi"><Skeleton h={12} w="50%" /><Skeleton h={26} w="70%" style={{ marginTop: 10 }} /></div>) : s && (
          <>
            <Kpi icon={<Activity size={13} />} label="Total runs" value={fmtInt(s.total_runs)} sub={`${s.completed_runs} completed · ${s.failed_runs} failed`} />
            <Kpi icon={<Timer size={13} />} label="Avg latency" value={s.avg_latency_ms === null ? "—" : fmtMs(s.avg_latency_ms)} sub="from stored run times" />
            <Kpi icon={<Gauge size={13} />} label="Error rate" value={fmtPct(s.error_rate)} tone={s.error_rate > 0 ? "err" : undefined} sub="failed ÷ (completed + failed)" />
            <Kpi icon={<Cpu size={13} />} label="Tokens" value={fmtCompact(s.input_tokens + s.output_tokens)} sub={`${fmtInt(s.input_tokens)} in · ${fmtInt(s.output_tokens)} out`} />
            <Kpi icon={<Coins size={13} />} label="Est. cost" value={s.estimated_cost_usd === null ? <span className="na">Not available</span> : fmtUsd(s.estimated_cost_usd)} sub={s.estimated_cost_usd === null ? "no pricing configured" : "estimate from configured pricing"} />
            <Kpi icon={<Search size={13} />} label="SerpApi calls" value={fmtInt(s.serpapi_calls)} sub="live requests only" />
            <Kpi icon={<Database size={13} />} label="Cache hits" value={fmtInt(s.cache_hits)} sub="served without a new request" />
            <Kpi icon={<ShieldCheck size={13} />} label="Verified figures" value={s.claims_total ? `${s.claims_verified}/${s.claims_total}` : "—"} tone={s.claims_total && s.claims_verified === s.claims_total ? "ok" : undefined} sub={s.claims_total ? fmtPct(s.claims_verified / s.claims_total) + " backed by tools" : "no figures checked yet"} />
          </>
        )}
      </div>

      <div className="grid2">
        <section className="card">
          <div className="card-head"><h2>Runs over time</h2><span className="muted sm">per hour · <span className="swatch ok" /> ok <span className="swatch err" /> failed</span></div>
          {summary.loading && !s ? <Skeleton h={200} /> : s && s.runs_over_time.length ? <RunsChart points={s.runs_over_time} /> : <EmptyState icon={<Activity size={18} />} title="No runs yet">Runs appear here as soon as an agent is used.</EmptyState>}
        </section>
        <section className="card">
          <div className="card-head"><h2>Tool calls</h2><span className="muted sm">distribution &amp; latency</span></div>
          {tools.loading && !tools.data ? <Skeleton h={200} /> : tools.data && tools.data.length ? <ToolBars stats={tools.data} /> : <EmptyState icon={<Search size={18} />} title="No tool calls yet">Tool usage shows up after an agent calls a tool.</EmptyState>}
        </section>
      </div>

      <section className="card">
        <div className="card-head">
          <h2>Recent runs</h2>
          <div className="seg" role="radiogroup" aria-label="Filter by status">
            {([["", "All"], ["completed", "Completed"], ["failed", "Failed"], ["running", "Running"]] as const).map(([v, l]) => (
              <button key={v} role="radio" aria-checked={status === v} className={status === v ? "on" : ""} onClick={() => setStatus(v)}>{l}</button>
            ))}
          </div>
        </div>
        {runs.loading && !runs.data ? <Skeleton h={160} /> : shown.length === 0 ? (
          <EmptyState icon={<Activity size={18} />} title={status ? `No ${status} runs` : "No runs yet"} action={status ? <button className="btn ghost sm" onClick={() => setStatus("")}>Show all runs</button> : undefined}>
            {status ? "Try a different filter." : "Chat with a deployed agent to create the first run."}
          </EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Run</th><th>Agent</th><th>Request</th><th>Status</th><th className="num">Latency</th><th className="num">Tokens</th><th className="num">Figures</th><th>Started</th></tr></thead>
              <tbody>
                {shown.map((r) => (
                  <tr key={r.id} tabIndex={0} onClick={() => nav(`/runs/${r.id}`)} onKeyDown={(e) => e.key === "Enter" && nav(`/runs/${r.id}`)} className="click">
                    <td className="mono">{shortId(r.id)}</td>
                    <td>{names.get(r.agent_id) ?? r.agent_id}</td>
                    <td className="trunc">{r.user_message}</td>
                    <td><StatusPill status={r.status} /></td>
                    <td className="num mono">{fmtMs(r.total_latency_ms)}</td>
                    <td className="num mono">{r.input_tokens === null ? "—" : fmtInt((r.input_tokens ?? 0) + (r.output_tokens ?? 0))}</td>
                    <td className="num mono">{r.claims_total ? `${r.claims_verified}/${r.claims_total}` : "—"}</td>
                    <td className="dim" title={fmtDateTime(r.started_at)}>{relTime(r.started_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
