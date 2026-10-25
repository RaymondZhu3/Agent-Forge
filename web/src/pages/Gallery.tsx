import { ArrowRight, Eye, MessageSquare, PenTool, Plus, Settings2, ShieldCheck, Trash2, X } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import AgentAvatar from "../components/AgentAvatar";
import ConfirmDialog from "../components/ConfirmDialog";
import ToolIcon from "../components/ToolIcon";
import { EmptyState, ErrorBanner, Skeleton, StatusPill } from "../components/ui";
import { api } from "../lib/api";
import { PROTECTED_AGENT_IDS, relTime, templateLabel } from "../lib/format";
import { useAsync, useDocumentTitle } from "../lib/hooks";
import type { AgentConfig, AgentCreate, ToolMetadata } from "../types";

const TEMPLATE_BLURB: Record<string, { use: string; tag: string }> = {
  smart_spend: { tag: "Banking + shopping", use: "Reads purchases and bills from a Capital One account, finds savings, and checks prices across stores." },
  news_monitor: { tag: "Research", use: "Searches current news on any topic and returns a source-backed briefing with original links." },
  blank: { tag: "Custom", use: "Start from scratch: write instructions and pick the tools your agent can use." },
};

function TemplatePreview({ tpl, tools, onClose }: { tpl: AgentCreate; tools: ToolMetadata[]; onClose: () => void }) {
  const nav = useNavigate();
  const meta = (n: string) => tools.find((t) => t.name === n);
  return (
    <div className="modal-scrim" onClick={onClose} role="presentation">
      <div className="modal" role="dialog" aria-modal="true" aria-label={`${tpl.name} template`} onClick={(e) => e.stopPropagation()}>
        <header>
          <AgentAvatar seed={tpl.template} size={40} />
          <div>
            <h2>{tpl.name}</h2>
            <span className="muted">{templateLabel(tpl.template)} template</span>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close preview"><X size={16} /></button>
        </header>
        <h5>Instructions</h5>
        <pre className="instr">{tpl.instructions}</pre>
        <h5>Tools</h5>
        <ul className="tool-list">
          {tpl.tools.map((t) => (
            <li key={t.name}>
              <ToolIcon name={t.name} size={13} />
              <div>
                <span className="mono">{t.name}</span>
                <span className="muted">{meta(t.name)?.description ?? ""}</span>
              </div>
            </li>
          ))}
        </ul>
        <h5>Guardrails</h5>
        <p className="muted mono">fact_check: {tpl.guardrails?.fact_check} · max_tool_calls: {tpl.guardrails?.max_tool_calls} · read_only_financial_data: {String(tpl.guardrails?.read_only_financial_data)}</p>
        <footer>
          <button className="btn ghost" onClick={onClose}>Close</button>
          <button className="btn primary" onClick={() => nav(`/builder?template=${tpl.template}`)}>
            Configure this template <ArrowRight size={14} />
          </button>
        </footer>
      </div>
    </div>
  );
}

/** "Audited · 312 figures checked in 40 runs", from the stored runs. */
function TrustBadge({ agentId }: { agentId: string }) {
  const runs = useAsync(() => api.runs({ agent_id: agentId, limit: 500 }), [agentId]);
  if (!runs.data) return null;
  const done = runs.data.filter((r) => r.status === "completed");
  const figures = done.reduce((n, r) => n + (r.claims_total ?? 0), 0);
  if (!done.length) return <div className="trust sm muted"><ShieldCheck size={12} /> No runs yet</div>;
  return (
    <div className="trust sm"><ShieldCheck size={12} /> Audited · {figures.toLocaleString()} figures checked in {done.length.toLocaleString()} {done.length === 1 ? "run" : "runs"}</div>
  );
}

function AgentRow({ a, onDelete }: { a: AgentConfig; onDelete: (a: AgentConfig) => void }) {
  return (
    <li className="agent-card">
      <AgentAvatar seed={a.id} size={44} />
      <div className="agent-card-main">
        <div className="agent-card-title">
          <Link to={`/builder/${a.id}`}>{a.name}</Link>
          <StatusPill status={a.status} />
        </div>
        <div className="muted sm">
          {templateLabel(a.template)} · <span className="mono">{a.model}</span> · v{a.version} · updated {relTime(a.updated_at)}
        </div>
        <TrustBadge agentId={a.id} />
        <div className="chips">
          {a.tools.map((t) => (
            <span key={t.name} className="chip mono"><ToolIcon name={t.name} size={10} />{t.name.replace(/^(serpapi|nessie)_/, "")}</span>
          ))}
          {a.tools.length === 0 && <span className="muted sm">No tools</span>}
        </div>
      </div>
      <div className="agent-card-actions">
        {!PROTECTED_AGENT_IDS.has(a.id) && <button className="btn ghost sm danger" onClick={() => onDelete(a)} aria-label={`Delete ${a.name}`}><Trash2 size={13} /></button>}
        <Link to={`/builder/${a.id}`} className="btn ghost sm"><Settings2 size={13} /> Configure</Link>
        {a.status === "deployed" ? (
          <Link to={`/chat/${a.id}`} className="btn primary sm"><MessageSquare size={13} /> Open chat</Link>
        ) : (
          <Link to={`/builder/${a.id}`} className="btn sm">Deploy</Link>
        )}
      </div>
    </li>
  );
}

export default function Gallery() {
  useDocumentTitle("Agents");
  const agents = useAsync(() => api.agents(), []);
  const templates = useAsync(() => api.templates(), []);
  const tools = useAsync(() => api.tools(), []);
  const [preview, setPreview] = useState<AgentCreate | null>(null);
  const [toDelete, setToDelete] = useState<AgentConfig | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [delError, setDelError] = useState<string | null>(null);
  const confirmDelete = async () => {
    if (!toDelete) return;
    setDeleting(true); setDelError(null);
    try { await api.deleteAgent(toDelete.id); setToDelete(null); agents.reload(); }
    catch (e) { setDelError((e as Error).message); }
    finally { setDeleting(false); }
  };

  return (
    <div className="page">
      <header className="hero">
        <div>
          <div className="eyebrow mono">AGENT FORGE</div>
          <h1>Build agents on real data.<br /><span className="grad">Trust every answer.</span></h1>
          <p>Compose an agent from live tools, deploy it, and watch every step it takes — each figure it states is checked against the tool results behind it.</p>
        </div>
        <div className="hero-actions">
          <Link to="/builder" className="btn primary"><Plus size={15} /> New agent</Link>
          <Link to="/dashboard" className="btn ghost">Open observability</Link>
        </div>
      </header>

      <section>
        <div className="section-head">
          <h2>Your agents</h2>
          {agents.data && <span className="muted mono">{agents.data.length}</span>}
        </div>
        {agents.error && <ErrorBanner message={agents.error} onRetry={agents.reload} title="Couldn't load agents" />}
        {agents.loading && !agents.data && (
          <ul className="agent-list">{[0, 1].map((i) => <li key={i} className="agent-card"><Skeleton h={44} w={44} /><div style={{ flex: 1, display: "grid", gap: 8 }}><Skeleton h={14} w="40%" /><Skeleton h={12} w="65%" /></div></li>)}</ul>
        )}
        {agents.data && agents.data.length === 0 && (
          <EmptyState icon={<PenTool size={20} />} title="No agents yet" action={<Link to="/builder" className="btn primary">Create your first agent</Link>}>
            Start from a template below or build one from scratch.
          </EmptyState>
        )}
        {agents.data && agents.data.length > 0 && <ul className="agent-list">{agents.data.map((a) => <AgentRow key={a.id} a={a} onDelete={(x) => { setDelError(null); setToDelete(x); }} />)}</ul>}
      </section>

      <section>
        <div className="section-head">
          <h2>Templates</h2>
          <span className="muted sm">Prefilled configurations you can customize</span>
        </div>
        {templates.error && <ErrorBanner message={templates.error} onRetry={templates.reload} title="Couldn't load templates" />}
        <div className="tpl-grid">
          {templates.loading && !templates.data && [0, 1].map((i) => <div key={i} className="tpl-card"><Skeleton h={120} /></div>)}
          {templates.data?.map((t) => {
            const b = TEMPLATE_BLURB[t.template] ?? TEMPLATE_BLURB.blank;
            return (
              <article key={t.template} className="tpl-card">
                <div className="tpl-top">
                  <AgentAvatar seed={t.template} size={40} />
                  <span className="chip mono">{b.tag}</span>
                </div>
                <h3>{t.name}</h3>
                <p>{b.use}</p>
                <div className="chips">
                  {t.tools.map((x) => <span key={x.name} className="chip mono"><ToolIcon name={x.name} size={10} />{x.name.replace(/^(serpapi|nessie)_/, "")}</span>)}
                </div>
                <div className="tpl-actions">
                  <button className="btn ghost sm" onClick={() => setPreview(t)}><Eye size={13} /> Preview</button>
                  <Link to={`/builder?template=${t.template}`} className="btn primary sm">Configure &amp; deploy <ArrowRight size={13} /></Link>
                </div>
              </article>
            );
          })}
        </div>
      </section>
      {toDelete && (
        <ConfirmDialog title={`Delete ${toDelete.name}?`} confirmLabel="Delete agent" busy={deleting} error={delError} onCancel={() => setToDelete(null)} onConfirm={confirmDelete}
          body="This permanently removes the agent and all of its runs and traces. Observability numbers will change. This can't be undone." />
      )}
      {preview && <TemplatePreview tpl={preview} tools={tools.data ?? []} onClose={() => setPreview(null)} />}
    </div>
  );
}
