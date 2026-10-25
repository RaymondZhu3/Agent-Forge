import { ArrowLeft, ShieldAlert, ShieldCheck } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import Markdown, { FigureMarks } from "../components/Markdown";
import Receipt from "../components/Receipt";
import Trace from "../components/Trace";
import { ErrorBanner, ModeBadge, Skeleton, StatusPill, modeOf } from "../components/ui";
import { api } from "../lib/api";
import { fmtDateTime, fmtInt, fmtMs, fmtUsd } from "../lib/format";
import { useAsync, useDocumentTitle } from "../lib/hooks";
import type { DataMode, RunStep } from "../types";

/** Per-figure fact-check results stored in the final verify step: [text, verified, source_tool, source_step, how]. */
function figureMarks(steps: RunStep[]): Map<string, boolean> {
  const m = new Map<string, boolean>();
  for (let i = steps.length - 1; i >= 0; i--) {
    const figs = (steps[i].output as { figures?: [string, boolean][] } | null)?.figures;
    if (Array.isArray(figs)) {
      for (const [text, ok] of figs) m.set(text, (m.get(text) ?? false) || ok);
      break;
    }
  }
  return m;
}

export default function RunDetail() {
  const { id = "" } = useParams();
  const run = useAsync(() => api.run(id), [id]);
  const agent = useAsync(() => (run.data ? api.agent(run.data.agent_id) : Promise.resolve(null)), [run.data?.agent_id]);
  useDocumentTitle(`Run ${id.slice(0, 12)}`);

  if (run.error) return <div className="page narrow"><Link to="/dashboard" className="back"><ArrowLeft size={14} /> Observability</Link><ErrorBanner title="Couldn't load this run" message={run.error} onRetry={run.reload} /></div>;
  if (!run.data) return <div className="page"><Skeleton h={30} w="40%" /><Skeleton h={140} style={{ marginTop: 16 }} /><Skeleton h={260} style={{ marginTop: 16 }} /></div>;
  const r = run.data;
  const steps = r.steps ?? [];
  const toolSteps = steps.filter((s) => s.type === "tool");
  const modes = [...new Set(toolSteps.map(modeOf))] as DataMode[];
  const llmMs = steps.filter((s) => s.type === "llm").reduce((a, s) => a + s.ms, 0);
  const toolMs = toolSteps.reduce((a, s) => a + s.ms, 0);

  return (
    <div className="page wide">
      <Link to={r.agent_id ? `/dashboard?agent=${r.agent_id}` : "/dashboard"} className="back"><ArrowLeft size={14} /> Observability</Link>
      <header className="page-head">
        <div>
          <div className="eyebrow mono">RUN</div>
          <h1 className="mono run-id">{r.id}</h1>
          <div className="muted sm">{agent.data ? <Link to={`/builder/${agent.data.id}`}>{agent.data.name}</Link> : r.agent_id} · started {fmtDateTime(r.started_at)}{r.session_id ? <> · session <span className="mono">{r.session_id}</span></> : null}</div>
        </div>
        <div className="head-actions"><StatusPill status={r.status} />{modes.map((m) => <ModeBadge key={m} mode={m} />)}</div>
      </header>

      <div className="kpis small">
        <div className="kpi"><div className="kpi-label">Total latency</div><div className="kpi-value mono">{fmtMs(r.total_latency_ms)}</div><div className="kpi-sub">model {fmtMs(llmMs)} · tools {fmtMs(toolMs)}</div></div>
        <div className="kpi"><div className="kpi-label">Tokens</div><div className="kpi-value mono">{r.input_tokens === null ? "—" : fmtInt((r.input_tokens ?? 0) + (r.output_tokens ?? 0))}</div><div className="kpi-sub">{fmtInt(r.input_tokens)} in · {fmtInt(r.output_tokens)} out</div></div>
        <div className="kpi"><div className="kpi-label">Est. cost</div><div className="kpi-value mono">{r.estimated_cost_usd === null ? <span className="na">Not available</span> : fmtUsd(r.estimated_cost_usd)}</div><div className="kpi-sub">{r.estimated_cost_usd === null ? "no pricing configured" : "estimate"}</div></div>
        <div className="kpi"><div className="kpi-label">Steps</div><div className="kpi-value mono">{steps.length}</div><div className="kpi-sub">{toolSteps.length} tool calls</div></div>
        <div className="kpi"><div className="kpi-label">Figures verified</div><div className={`kpi-value mono ${r.claims_total && r.claims_verified < r.claims_total ? "warn-t" : r.claims_total ? "ok-t" : ""}`}>{r.claims_total ? `${r.claims_verified}/${r.claims_total}` : "—"}</div><div className="kpi-sub">{r.blocked ? <><ShieldAlert size={11} /> some redacted</> : <><ShieldCheck size={11} /> fact-check</>}</div></div>
      </div>

      {r.error && <ErrorBanner title="Run failed" message={r.error} />}

      <div className="grid-detail">
        <section className="card">
          <div className="card-head"><h2>Execution trace</h2><span className="muted sm">click a step to inspect its input and output</span></div>
          {steps.length === 0 ? <p className="muted sm">No steps were recorded for this run.</p> : <Trace steps={steps} running={r.status === "running"} />}
        </section>
        <div className="stack">
          <section className="card">
            <div className="card-head"><h2>Request</h2></div>
            <p className="request">{r.user_message}</p>
          </section>
          {steps.some((s) => (s.output as { receipt?: unknown } | null)?.receipt) && (
            <section className="card"><Receipt runId={r.id} steps={steps} run={r} /></section>
          )}
          <section className="card">
            <div className="card-head"><h2>Answer</h2></div>
            {r.assistant_message ? (
              <FigureMarks.Provider value={figureMarks(steps)}>
                <Markdown text={r.assistant_message} cards={agent.data?.template === "smart_spend"} stories={agent.data?.template === "news_monitor"} />
              </FigureMarks.Provider>
            ) : <p className="muted sm">{r.status === "running" ? "Still running…" : "No answer was produced."}</p>}
          </section>
        </div>
      </div>
    </div>
  );
}
