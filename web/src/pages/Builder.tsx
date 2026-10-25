import { AlertTriangle, ArrowRight, Check, ChevronDown, Cpu, Loader2, Rocket, Search, ShieldCheck, Trash2, X, Zap } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import AgentAvatar from "../components/AgentAvatar";
import ConfirmDialog from "../components/ConfirmDialog";
import ToolIcon from "../components/ToolIcon";
import { EmptyState, ErrorBanner, ModeBadge, Skeleton, StatusPill } from "../components/ui";
import { api } from "../lib/api";
import { PROTECTED_AGENT_IDS, templateLabel } from "../lib/format";
import { useAsync, useDocumentTitle, useMediaQuery } from "../lib/hooks";
import type { AgentConfig, AgentCreate, Guardrails, ToolConfig, ToolMetadata } from "../types";

type Draft = { name: string; template: string; model: string; instructions: string; tools: ToolConfig[]; guardrails: Guardrails };
type Phase = "idle" | "saving" | "deploying" | "deployed" | "error";

const DEFAULT_GUARDRAILS: Guardrails = { read_only_financial_data: true, max_tool_calls: 8, require_confirmation_for_external_actions: true, fact_check: "flag" };
const MODEL_SUGGESTIONS = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-flash-latest", "gemini-3.1-flash-lite"];

const toDraft = (a: AgentConfig | AgentCreate): Draft => ({
  name: a.name, template: a.template, model: a.model ?? "", instructions: a.instructions,
  tools: a.tools.map((t) => ({ name: t.name, settings: { ...t.settings } })),
  guardrails: { ...DEFAULT_GUARDRAILS, ...(a.guardrails ?? {}) },
});
const same = (a: Draft, b: Draft) => JSON.stringify(a) === JSON.stringify(b);

function schemaDefaults(meta: ToolMetadata | undefined): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, p] of Object.entries(meta?.settingsSchema.properties ?? {})) if (p.default !== undefined) out[k] = p.default;
  return out;
}

/* ---------- small controls ---------- */

function Switch({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} disabled={disabled} className={`switch${checked ? " on" : ""}`} onClick={() => onChange(!checked)}>
      <span />
    </button>
  );
}

function Segmented<T extends string>({ value, options, onChange, label }: { value: T; options: { v: T; label: string }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div className="seg" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button key={o.v} type="button" role="radio" aria-checked={value === o.v} className={value === o.v ? "on" : ""} onClick={() => onChange(o.v)}>{o.label}</button>
      ))}
    </div>
  );
}

function Section({ title, hint, children, defaultOpen = true }: { title: string; hint?: string; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="cfg-section">
      <button className="cfg-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span>{title}</span>
        {hint && <span className="muted sm">{hint}</span>}
        <ChevronDown size={14} className={`chev${open ? " open" : ""}`} />
      </button>
      {open && <div className="cfg-body">{children}</div>}
    </section>
  );
}

/* ---------- tool settings ---------- */

function SettingsFields({ meta, cfg, onChange }: { meta: ToolMetadata | undefined; cfg: ToolConfig; onChange: (s: Record<string, unknown>) => void }) {
  const props = Object.entries(meta?.settingsSchema.properties ?? {});
  if (!props.length) return <p className="muted sm">This tool has no settings.</p>;
  const set = (k: string, v: string) => {
    const next = { ...cfg.settings };
    if (v === "") delete next[k]; else next[k] = v;
    onChange(next);
  };
  return (
    <div className="fields">
      {props.map(([k, p]) => (
        <label key={k} className="field">
          <span className="mono">{k}</span>
          {p.enum ? (
            <select value={String(cfg.settings[k] ?? p.default ?? "")} onChange={(e) => set(k, e.target.value)}>
              {!p.default && <option value="">(default)</option>}
              {p.enum.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          ) : (
            <input value={String(cfg.settings[k] ?? "")} placeholder={p.default !== undefined ? String(p.default) : k === "customer_id" ? "Nessie customer id" : ""} onChange={(e) => set(k, e.target.value)} spellCheck={false} />
          )}
          {p.description && <small className="muted">{p.description}</small>}
        </label>
      ))}
    </div>
  );
}

/* ---------- describe an agent (experimental) ---------- */

function DescribeBox({ onDraft }: { onDraft: (c: AgentCreate) => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const go = async () => {
    setBusy(true); setErr(null);
    try { onDraft(await api.draftAgent(text)); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <div className="describe">
      <label className="field">
        <span>Describe your agent in one sentence <span className="pill info">Experimental</span></span>
        <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. Finds tennis courts near UT and compares racquet prices" />
      </label>
      <button className="btn sm" onClick={go} disabled={busy || text.trim().length < 8}>{busy ? "Drafting…" : "Draft it"}</button>
      {err && <p className="err-t sm">{err}</p>}
      <p className="muted sm">Gemini fills in the name, instructions, tools and fact-check mode below. Review before you deploy.</p>
    </div>
  );
}

/* ---------- page ---------- */

export default function Builder() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const nav = useNavigate();
  const wide = useMediaQuery("(min-width: 1180px)");
  const [tab, setTab] = useState<"config" | "canvas" | "tools">("canvas");

  const tools = useAsync(() => api.tools(), []);
  const templates = useAsync(() => api.templates(), []);
  const agents = useAsync(() => api.agents(), []);
  const health = useAsync(() => api.health(), []);
  const existing = useAsync(() => (id ? api.agent(id) : Promise.resolve(null)), [id]);

  const [draft, setDraft] = useState<Draft | null>(null);
  const [baseline, setBaseline] = useState<Draft | null>(null);
  const [saved, setSaved] = useState<AgentConfig | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [celebrate, setCelebrate] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [delError, setDelError] = useState<string | null>(null);
  const initFor = useRef<string | null>(null);

  const templateParam = params.get("template") ?? "blank";
  const initKey = id ? `id:${id}` : `new:${templateParam}`;

  // Borrow a real Nessie customer_id already configured on another agent so new banking agents work out of the box.
  const borrowCustomer = useCallback((d: Draft): Draft => {
    const known = agents.data?.flatMap((a) => a.tools).find((t) => t.name.startsWith("nessie_") && t.settings.customer_id)?.settings.customer_id;
    if (!known) return d;
    return { ...d, tools: d.tools.map((t) => (t.name.startsWith("nessie_") && !t.settings.customer_id ? { ...t, settings: { ...t.settings, customer_id: known } } : t)) };
  }, [agents.data]);

  useEffect(() => {
    if (initFor.current === initKey) return;
    if (id) {
      if (!existing.data) return;
      const d = toDraft(existing.data);
      setDraft(d); setBaseline(d); setSaved(existing.data);
    } else {
      if (!templates.data || (templateParam !== "blank" && agents.loading && !agents.data)) return;
      const t = templates.data.find((x) => x.template === templateParam) ?? templates.data.find((x) => x.template === "blank");
      if (!t) return;
      const d = borrowCustomer(toDraft(t));
      setDraft(d); setBaseline(d); setSaved(null);
    }
    initFor.current = initKey;
    setPhase("idle"); setError(null); setSelected(null); setCelebrate(false);
  }, [id, initKey, existing.data, templates.data, templateParam, agents.loading, agents.data, borrowCustomer]);

  const dirty = !!draft && !!baseline && !same(draft, baseline);
  useDocumentTitle(draft?.name || "Builder");

  useEffect(() => {
    if (!dirty) return;
    const h = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [dirty]);

  const meta = useCallback((n: string) => tools.data?.find((t) => t.name === n), [tools.data]);
  const update = (patch: Partial<Draft>) => setDraft((d) => (d ? { ...d, ...patch } : d));
  const updateGuard = (patch: Partial<Guardrails>) => setDraft((d) => (d ? { ...d, guardrails: { ...d.guardrails, ...patch } } : d));

  const toggleTool = (name: string) => {
    if (!draft) return;
    if (draft.tools.some((t) => t.name === name)) {
      update({ tools: draft.tools.filter((t) => t.name !== name) });
      if (selected === name) setSelected(null);
    } else {
      update({ tools: [...draft.tools, borrowCustomer({ ...draft, tools: [{ name, settings: schemaDefaults(meta(name)) }] }).tools[0]] });
      setSelected(name);
    }
  };

  const applyTemplate = (key: string) => {
    const t = templates.data?.find((x) => x.template === key);
    if (!t) return;
    if (dirty && !window.confirm("Replace the current configuration with this template? Unsaved changes will be lost.")) return;
    const d = borrowCustomer(toDraft(t));
    setDraft(d); setBaseline(baseline); setSelected(null);
  };

  const problems = useMemo(() => {
    const p: string[] = [];
    if (!draft) return p;
    if (!draft.name.trim()) p.push("Give the agent a name");
    if (!draft.instructions.trim()) p.push("Write instructions");
    if (!draft.model.trim()) p.push("Choose a model");
    if (draft.tools.length === 0) p.push("Enable at least one tool");
    return p;
  }, [draft]);

  const persist = async (): Promise<AgentConfig> => {
    if (!draft) throw new Error("Nothing to save");
    const body = { name: draft.name.trim(), model: draft.model.trim(), instructions: draft.instructions, tools: draft.tools, guardrails: draft.guardrails };
    if (saved) return dirty ? api.updateAgent(saved.id, body) : saved;
    return api.createAgent({ ...body, template: draft.template });
  };

  const run = async (deploy: boolean) => {
    if (!draft) return;
    setError(null);
    try {
      setPhase("saving");
      let rec = await persist();
      if (deploy && rec.status !== "deployed") {
        setPhase("deploying");
        rec = await api.deploy(rec.id);
      }
      setSaved(rec);
      const d = toDraft(rec);
      setDraft(d); setBaseline(d); initFor.current = `id:${rec.id}`;
      if (!id) nav(`/builder/${rec.id}`, { replace: true });
      if (deploy && rec.status === "deployed") { setPhase("deployed"); setCelebrate(true); } else setPhase("idle");
    } catch (e) {
      setError((e as Error).message);
      setPhase("error");
    }
  };

  const doDelete = async () => {
    if (!saved) return;
    setDeleting(true); setDelError(null);
    try { await api.deleteAgent(saved.id); setBaseline(draft); nav("/", { replace: true }); }
    catch (e) { setDelError((e as Error).message); setDeleting(false); }
  };

  const status = phase === "deploying" || phase === "saving" ? "deploying" : phase === "error" ? "error" : saved?.status ?? "draft";
  const busy = phase === "saving" || phase === "deploying";

  if ((id && existing.error) || templates.error || tools.error) {
    return (
      <div className="page narrow">
        <ErrorBanner title="Couldn't load the builder" message={existing.error ?? templates.error ?? tools.error ?? ""} onRetry={() => { existing.reload(); templates.reload(); tools.reload(); }} />
      </div>
    );
  }
  if (!draft || !tools.data) {
    return (
      <div className="builder">
        <div className="panel"><Skeleton h={18} w="50%" /><Skeleton h={80} /><Skeleton h={120} /></div>
        <div className="panel center"><Skeleton h={90} /><Skeleton h={140} /></div>
        <div className="panel"><Skeleton h={18} w="40%" /><Skeleton h={70} /><Skeleton h={70} /></div>
      </div>
    );
  }

  const live = (name: string): "live" | "fixture" | null =>
    !health.data ? null : name.startsWith("serpapi_") ? health.data.serpapi : name.startsWith("nessie_") ? health.data.nessie : null;

  const filtered = tools.data.filter((t) => `${t.name} ${t.label} ${t.description} ${t.source}`.toLowerCase().includes(q.trim().toLowerCase()));
  const groups = [{ k: "search", title: "Search · SerpApi" }, { k: "banking", title: "Banking · Capital One Nessie" }].map((g) => ({ ...g, items: filtered.filter((t) => t.category === g.k) }))
    .concat([{ k: "other", title: "Other", items: filtered.filter((t) => t.category !== "search" && t.category !== "banking") }]).filter((g) => g.items.length);

  const showPanel = (p: typeof tab) => wide || tab === p;
  const deployLabel = saved?.status === "deployed" ? (dirty ? "Save changes" : "Open chat") : "Deploy agent";

  return (
    <div className="builder-wrap">
      {!wide && (
        <div className="tabs" role="tablist">
          {(["config", "canvas", "tools"] as const).map((t) => (
            <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>{t === "config" ? "Configure" : t === "canvas" ? "Workspace" : `Tools (${draft.tools.length})`}</button>
          ))}
        </div>
      )}
      <div className="builder">
        {/* ---------------- left: configuration ---------------- */}
        {showPanel("config") && (
          <aside className="panel cfg" aria-label="Agent configuration">
            <div className="panel-title">Configuration {dirty && <span className="pill warn">Unsaved</span>}</div>
            {!saved && <DescribeBox onDraft={(c) => { setDraft(borrowCustomer(toDraft(c))); setSelected(null); }} />}
            <Section title="Identity">
              <label className="field"><span>Name</span><input value={draft.name} onChange={(e) => update({ name: e.target.value })} maxLength={60} /></label>
              {!saved ? (
                <label className="field">
                  <span>Start from template</span>
                  <select value={draft.template} onChange={(e) => applyTemplate(e.target.value)}>
                    {templates.data?.map((t) => <option key={t.template} value={t.template}>{t.name}</option>)}
                  </select>
                </label>
              ) : (
                <div className="field"><span>Template</span><div className="mono ro">{templateLabel(draft.template)}</div></div>
              )}
              <label className="field">
                <span>Model</span>
                <input list="models" value={draft.model} onChange={(e) => update({ model: e.target.value })} spellCheck={false} className="mono" />
                <datalist id="models">{MODEL_SUGGESTIONS.map((m) => <option key={m} value={m} />)}</datalist>
              </label>
            </Section>
            <Section title="Instructions" hint={`${draft.instructions.length} chars`}>
              <textarea className="instructions" value={draft.instructions} onChange={(e) => update({ instructions: e.target.value })} spellCheck rows={12} aria-label="Agent instructions" />
            </Section>
            <Section title="Guardrails">
              <div className="row"><div><strong>Read-only financial data</strong><small className="muted">Never move money or change accounts</small></div><Switch label="Read-only financial data" checked={draft.guardrails.read_only_financial_data} onChange={(v) => updateGuard({ read_only_financial_data: v })} /></div>
              <div className="row"><div><strong>No external actions</strong><small className="muted">Report findings, don't act on them</small></div><Switch label="Require confirmation for external actions" checked={draft.guardrails.require_confirmation_for_external_actions} onChange={(v) => updateGuard({ require_confirmation_for_external_actions: v })} /></div>
              <div className="field">
                <span>Fact-check figures</span>
                <Segmented label="Fact-check mode" value={draft.guardrails.fact_check} onChange={(v) => updateGuard({ fact_check: v })} options={[{ v: "flag", label: "Flag" }, { v: "block", label: "Block" }, { v: "off", label: "Off" }]} />
                <small className="muted">{draft.guardrails.fact_check === "flag" ? "Mark figures the tools don't back up." : draft.guardrails.fact_check === "block" ? "Redact figures the tools don't back up." : "Skip verification."}</small>
              </div>
              <div className="field">
                <span>Max tool calls</span>
                <div className="stepper">
                  <button type="button" aria-label="Decrease" onClick={() => updateGuard({ max_tool_calls: Math.max(1, draft.guardrails.max_tool_calls - 1) })}>−</button>
                  <input type="number" min={1} max={25} value={draft.guardrails.max_tool_calls} onChange={(e) => updateGuard({ max_tool_calls: Math.min(25, Math.max(1, Number(e.target.value) || 1)) })} className="mono" aria-label="Max tool calls" />
                  <button type="button" aria-label="Increase" onClick={() => updateGuard({ max_tool_calls: Math.min(25, draft.guardrails.max_tool_calls + 1) })}>+</button>
                </div>
              </div>
            </Section>
            {saved && !PROTECTED_AGENT_IDS.has(saved.id) && (
              <button className="btn ghost danger" onClick={() => { setDelError(null); setConfirmDel(true); }}><Trash2 size={14} /> Delete agent</button>
            )}
          </aside>
        )}

        {/* ---------------- center: workspace ---------------- */}
        {showPanel("canvas") && (
          <section className="panel center" aria-label="Agent workspace">
            <div className="deploy-bar">
              <div className="db-left">
                <StatusPill status={status} />
                <span className="mono dim">{saved ? `${saved.id} · v${saved.version}` : "not saved yet"}</span>
              </div>
              <div className="db-right">
                {saved?.status === "deployed" && dirty && <Link to={`/chat/${saved.id}`} className="btn ghost sm">Open chat</Link>}
                {dirty || !saved ? <button className="btn ghost sm" disabled={busy || !draft.name.trim() || !draft.instructions.trim()} onClick={() => run(false)}>Save draft</button> : null}
                <button
                  className="btn primary"
                  disabled={busy || (problems.length > 0 && !(saved?.status === "deployed" && !dirty))}
                  onClick={() => (saved?.status === "deployed" && !dirty ? nav(`/chat/${saved.id}`) : run(saved?.status !== "deployed"))}
                >
                  {busy ? <Loader2 size={15} className="spin" /> : saved?.status === "deployed" && !dirty ? <ArrowRight size={15} /> : <Rocket size={15} />}
                  {phase === "saving" ? "Saving…" : phase === "deploying" ? "Deploying…" : deployLabel}
                </button>
              </div>
            </div>

            {error && <ErrorBanner title={phase === "error" ? "Couldn't complete that" : "Error"} message={error} onRetry={() => run(saved?.status !== "deployed")} />}

            {phase === "deployed" && celebrate && saved && (
              <div className="deployed" role="status">
                <div className="check-ring"><Check size={22} strokeWidth={3} /></div>
                <div>
                  <h3>{saved.name} is live</h3>
                  <p className="muted">Deployed {saved.deployed_at ? new Date(saved.deployed_at).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }) : ""} · {saved.tools.length} tools · <span className="mono">{saved.model}</span></p>
                </div>
                <div className="deployed-actions">
                  <Link to={`/chat/${saved.id}`} className="btn primary">Open chat <ArrowRight size={14} /></Link>
                  <button className="btn ghost" onClick={() => setCelebrate(false)}>Keep editing</button>
                </div>
              </div>
            )}

            <div className="canvas">
              <div className="agent-node">
                <AgentAvatar seed={saved?.id ?? draft.template + draft.name} size={52} />
                <div className="an-main">
                  <h2>{draft.name || "Untitled agent"}</h2>
                  <div className="muted sm">{templateLabel(draft.template)} · <span className="mono">{draft.model || "no model"}</span></div>
                  <div className="chips">
                    <span className="chip"><ShieldCheck size={11} /> fact-check: {draft.guardrails.fact_check}</span>
                    <span className="chip"><Cpu size={11} /> ≤ {draft.guardrails.max_tool_calls} tool calls</span>
                  </div>
                </div>
              </div>

              {draft.tools.length === 0 ? (
                <div className="empty-canvas">
                  <EmptyState icon={<Zap size={20} />} title="No tools connected" action={!wide ? <button className="btn" onClick={() => setTab("tools")}>Browse tools</button> : undefined}>
                    An agent without tools can only chat. Enable tools from the library to let it act on real systems.
                  </EmptyState>
                </div>
              ) : (
                <>
                  {Array.from({ length: Math.ceil(draft.tools.length / 3) }, (_, r) => draft.tools.slice(r * 3, r * 3 + 3)).map((row, r) => (
                    <div key={r} className="tool-tier">
                      <div className="stem" aria-hidden />
                      <div className="tool-row" style={{ ["--n" as string]: row.length }}>
                        {row.map((t) => {
                          const m = meta(t.name);
                          const open = selected === t.name;
                          const mode = live(t.name);
                          return (
                            <div key={t.name} className={`tool-node${open ? " open" : ""}`}>
                              <span className="drop" aria-hidden />
                              <button className="tn-head" onClick={() => setSelected(open ? null : t.name)} aria-expanded={open}>
                                <ToolIcon name={t.name} size={15} />
                                <span className="tn-t"><strong>{m?.label ?? t.name}</strong><span className="mono dim">{t.name}</span></span>
                                {mode && <ModeBadge mode={mode} />}
                                {!m && <span className="pill err"><AlertTriangle size={10} />Unknown</span>}
                              </button>
                              {open && (
                                <div className="tn-body">
                                  <p className="muted sm">{m?.description}</p>
                                  <SettingsFields meta={m} cfg={t} onChange={(s) => update({ tools: draft.tools.map((x) => (x.name === t.name ? { ...x, settings: s } : x)) })} />
                                  {mode === "fixture" && <p className="note warn"><AlertTriangle size={12} /> The server has no live credentials for this source, so results use labeled demo data.</p>}
                                  <button className="btn ghost sm danger" onClick={() => toggleTool(t.name)}><Trash2 size={12} /> Disconnect</button>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </>
              )}
            </div>

            <div className="preview">
              <div className="panel-title">Live preview</div>
              <div className="pv-grid">
                <div><h5>System role</h5><p className="pv-instr">{draft.instructions.trim().split("\n").slice(0, 3).join(" ").slice(0, 220) || "—"}{draft.instructions.length > 220 ? "…" : ""}</p></div>
                <div>
                  <h5>Readiness</h5>
                  {problems.length === 0 ? <p className="ok-t"><Check size={13} /> {saved?.status === "deployed" ? (dirty ? "Deployed · unsaved changes" : "Deployed · up to date") : "Ready to deploy"}</p> : <ul className="todo">{problems.map((p) => <li key={p}><AlertTriangle size={12} />{p}</li>)}</ul>}
                </div>
              </div>
            </div>
          </section>
        )}

        {/* ---------------- right: tool library ---------------- */}
        {showPanel("tools") && (
          <aside className="panel lib" aria-label="Tool library">
            <div className="panel-title">Tool library <span className="muted mono">{draft.tools.length}/{tools.data.length}</span></div>
            <div className="model-card">
              <span className="tool-icon model"><Cpu size={15} /></span>
              <div><strong>Gemini function calling</strong><small className="muted">The model chooses tools; Agent Forge validates and executes them.</small></div>
            </div>
            <label className="search"><Search size={14} /><input placeholder="Search tools" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search tools" />{q && <button onClick={() => setQ("")} aria-label="Clear search"><X size={13} /></button>}</label>
            {groups.length === 0 && <EmptyState icon={<Search size={18} />} title="No tools match" action={<button className="btn ghost sm" onClick={() => setQ("")}>Clear search</button>}>Nothing matches “{q}”.</EmptyState>}
            {groups.map((g) => (
              <div key={g.k} className="lib-group">
                <h5>{g.title}</h5>
                {g.items.map((t) => {
                  const on = draft.tools.some((x) => x.name === t.name);
                  const mode = live(t.name);
                  return (
                    <div key={t.name} className={`lib-tool${on ? " on" : ""}`}>
                      <ToolIcon name={t.name} size={14} />
                      <div className="lt-main">
                        <div className="lt-title"><strong>{t.label}</strong>{mode === "fixture" && <ModeBadge mode="fixture" />}</div>
                        <span className="mono dim">{t.name}</span>
                        <p>{t.description}</p>
                      </div>
                      <Switch label={`${on ? "Disable" : "Enable"} ${t.label}`} checked={on} onChange={() => toggleTool(t.name)} />
                    </div>
                  );
                })}
              </div>
            ))}
          </aside>
        )}
      </div>
      {confirmDel && saved && (
        <ConfirmDialog title={`Delete ${saved.name}?`} confirmLabel="Delete agent" busy={deleting} error={delError} onCancel={() => setConfirmDel(false)} onConfirm={doDelete}
          body="This permanently removes the agent and all of its runs and traces. Observability numbers will change. This can't be undone." />
      )}
    </div>
  );
}
