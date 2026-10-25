import { AlertTriangle, ArrowUp, ChevronDown, ExternalLink, FileSearch, Loader2, RotateCcw, ShieldAlert, ShieldCheck, Square } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import AgentAvatar from "../components/AgentAvatar";
import Markdown, { FigureMarks } from "../components/Markdown";
import ToolIcon from "../components/ToolIcon";
import Trace, { stepLabel } from "../components/Trace";
import { EmptyState, ErrorBanner, ModeBadge, Skeleton, StatusPill, modeOf } from "../components/ui";
import { api } from "../lib/api";
import { extractUrls, fmtInt, fmtMs, hostOf, templateLabel, uid } from "../lib/format";
import { useAsync, useDocumentTitle } from "../lib/hooks";
import type { AgentConfig, ChatResponse, Claim, RunStep } from "../types";

type Turn =
  | { kind: "user"; id: string; text: string }
  | { kind: "agent"; id: string; res: ChatResponse }
  | { kind: "error"; id: string; message: string; retryText: string };

const SUGGESTIONS: Record<string, { label: string; text: string }[]> = {
  smart_spend: [
    { label: "Find three ways to save", text: "Find three ways I could reduce my spending." },
    { label: "Review my subscriptions", text: "Which recurring bills and subscriptions am I paying for, and could any be cheaper?" },
    { label: "Check my recent purchases", text: "Am I overpaying for anything I bought recently? Compare prices." },
  ],
  news_monitor: [
    { label: "NVIDIA & chips", text: "Brief me on NVIDIA and semiconductor supply chains." },
    { label: "AI regulation", text: "What are the most important recent stories on AI regulation?" },
    { label: "Cloud & data centers", text: "Brief me on new cloud and AI data center announcements." },
  ],
};

/* ---------- pieces of an agent turn ---------- */

function DataUsed({ steps }: { steps: RunStep[] }) {
  const tools = steps.filter((s) => s.type === "tool");
  if (!tools.length) return null;
  return (
    <div className="data-used">
      <h5>Data used</h5>
      <div className="du-grid">
        {tools.map((s) => {
          const { detail } = stepLabel(s);
          return (
            <div key={s.step} className={`du-card${s.success ? "" : " failed"}`}>
              <div className="du-top">
                <ToolIcon name={s.toolName ?? ""} size={12} />
                <span className="mono">{s.toolName}</span>
              </div>
              <div className="du-sum">{s.success ? detail || "No summary returned" : s.error ?? "Failed"}</div>
              <div className="du-foot">
                {s.success ? <ModeBadge mode={modeOf(s)} /> : <span className="pill err"><AlertTriangle size={10} /> Failed</span>}
                <span className="mono dim">{fmtMs(s.ms)}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const HOW: Record<string, string> = { difference: "difference", sum: "sum", annualized: "× 12" };
/** The sentence a figure came from, without Markdown syntax. */
const plain = (t: string) => t.replace(/\[([^\]]+)\]\([^)]*\)?/g, "$1").replace(/[*_`#]+/g, "").replace(/\s+/g, " ").trim();

/** One row per figure as written; a figure counts as backed if any mention of it is. */
function ledger(claims: Claim[]) {
  const rows = new Map<string, { claim: Claim; times: number; verified: boolean }>();
  for (const c of claims) {
    const r = rows.get(c.text);
    if (!r) rows.set(c.text, { claim: c, times: 1, verified: c.verified });
    else { r.times++; if (c.verified && !r.verified) { r.claim = c; r.verified = true; } }
  }
  return [...rows.values()];
}

function FactCheck({ claims, blocked, mode }: { claims: Claim[]; blocked: boolean; mode?: string }) {
  const rows = useMemo(() => ledger(claims), [claims]);
  const bad = rows.filter((r) => !r.verified);
  const [open, setOpen] = useState(bad.length > 0);
  if (mode === "off" && !claims.length) return null;
  if (!claims.length) return <div className="fact muted sm"><ShieldCheck size={13} /> No figures to verify in this answer.</div>;
  return (
    <div className={`fact${bad.length ? " warn" : " ok"}`}>
      <button className="fact-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        {bad.length ? <ShieldAlert size={14} /> : <ShieldCheck size={14} />}
        <strong>{rows.length - bad.length} of {rows.length} figures verified</strong>
        <span className="muted sm">{bad.length ? `${bad.length} not backed by tool data` : "every figure traced to a tool result"}</span>
        <ChevronDown size={13} className={`chev${open ? " open" : ""}`} />
      </button>
      {blocked && <p className="note warn"><ShieldAlert size={12} /> Unverified figures were redacted from this answer.</p>}
      {open && (
        <ul className="claims">
          {[...bad, ...rows.filter((r) => r.verified)].map(({ claim: c, times, verified }) => (
            <li key={c.text} className={verified ? "v" : "u"}>
              <span className="mono claim-t">{c.text}</span>
              <span className="claim-c">{plain(c.context)}</span>
              <span className="claim-s">
                {verified
                  ? `${TOOL_NAMES[c.source_tool ?? ""] ?? c.source_tool ?? "Tool"}, step ${c.source_step}${c.how && HOW[c.how] ? ` (${HOW[c.how]})` : ""}`
                  : c.source_tool === "user_message" ? "From your message, no tool confirms it" : "No tool returned this"}
                {times > 1 && <span className="dim"> ×{times}</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const TOOL_NAMES: Record<string, string> = {
  nessie_purchases: "Nessie purchases", nessie_bills: "Nessie bills", nessie_accounts: "Nessie accounts",
  serpapi_shopping: "Google Shopping", serpapi_web_search: "Google search", serpapi_news: "Google News", serpapi_local_places: "Google Local",
};

type VerifyOut = { draft?: string; invented?: string[]; fixed?: string[]; used_correction?: boolean };

/** Shown only when the platform sent made-up figures back to the agent (verify steps: stage draft -> corrected). */
function SelfCorrection({ res }: { res: ChatResponse }) {
  const [open, setOpen] = useState(false);
  const verifies = res.steps.filter((s) => s.type === "verify");
  const draftStep = verifies.find((s) => (s.output as VerifyOut | null)?.draft);
  const fixStep = verifies.find((s) => (s.input as { stage?: string } | null)?.stage === "corrected");
  const marks = useMemo(() => new Map(((draftStep?.output as VerifyOut)?.invented ?? []).map((t) => [t, false])), [draftStep]);
  if (!draftStep) return null;
  const d = draftStep.output as VerifyOut;
  const f = (fixStep?.output ?? null) as VerifyOut | null;
  const used = !!f?.used_correction;
  const invented = d.invented ?? [];
  const fixed = new Set(f?.fixed ?? []);
  const nowVerified = new Map(res.claims.filter((c) => c.verified).map((c) => [c.text, c]));
  const nFixed = invented.filter((t) => fixed.has(t)).length;
  const summary = !f
    ? "The correction didn't finish, so the original answer is shown"
    : !used
      ? "The correction wasn't better, so the original answer is shown"
      : `${nFixed} ${nFixed === 1 ? "figure" : "figures"} had no tool data and ${nFixed === 1 ? "was" : "were"} fixed before you saw this answer`;

  return (
    <div className={`selfcorr${used ? "" : " kept"}`}>
      <button className="sc-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <RotateCcw size={14} />
        <strong>{used ? "Self-corrected" : "Correction attempted"}</strong>
        <span className="muted sm">{summary}</span>
        <span className="sc-toggle sm">{open ? "Hide draft" : "Show draft"}<ChevronDown size={13} className={`chev${open ? " open" : ""}`} /></span>
      </button>
      {open && (
        <div className="sc-body">
          <div className="sc-label sm">First draft (not shown to the user)</div>
          <div className="sc-draft">
            <FigureMarks.Provider value={marks}>
              <Markdown text={d.draft ?? ""} />
            </FigureMarks.Provider>
          </div>
          <ul className="sc-list">
            {invented.map((t) => {
              const v = nowVerified.get(t);
              return (
                <li key={t}>
                  <span className="mono sc-fig">{t}</span>
                  <span className="muted">no tool returned this</span>
                  <span className={`sc-out${fixed.has(t) ? " ok" : ""}`}>
                    {!fixed.has(t) ? "still unverified" : v ? `now verified from ${TOOL_NAMES[v.source_tool ?? ""] ?? v.source_tool}` : "removed"}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

function AgentTurn({ res, agent }: { res: ChatResponse; agent: AgentConfig }) {
  const [showTrace, setShowTrace] = useState(false);
  const sources = useMemo(() => extractUrls(res.assistant_message), [res.assistant_message]);
  // A figure counts as backed if any mention of it is.
  const answerMarks = useMemo(() => {
    const m = new Map<string, boolean>();
    for (const c of res.claims) m.set(c.text, (m.get(c.text) ?? false) || c.verified);
    return m;
  }, [res.claims]);
  const fixtureOnly = res.data_modes.length > 0 && res.data_modes.every((m) => m === "fixture");
  const failed = res.status === "failed";

  return (
    <div className="turn agent">
      <AgentAvatar seed={agent.id} size={30} />
      <div className="turn-body">
        <div className="turn-meta">
          <strong>{agent.name}</strong>
          <StatusPill status={res.status} />
          <span className="mono dim">{fmtMs(res.total_latency_ms)}</span>
          {res.usage.input_tokens !== null && <span className="mono dim">{fmtInt((res.usage.input_tokens ?? 0) + (res.usage.output_tokens ?? 0))} tokens</span>}
          {res.data_modes.map((m) => <ModeBadge key={m} mode={m} />)}
        </div>
        {fixtureOnly && <p className="note warn"><AlertTriangle size={12} /> This answer used demo data, not live API results.</p>}
        {failed && <ErrorBanner title="The agent couldn't finish" message={res.error ?? "Unknown error"} />}
        {!failed && <DataUsed steps={res.steps} />}
        {!failed && <SelfCorrection res={res} />}
        {res.assistant_message && (
          <div className="answer">
            <FigureMarks.Provider value={answerMarks}>
              <Markdown text={res.assistant_message} cards={agent.template === "smart_spend"} stories={agent.template === "news_monitor"} />
            </FigureMarks.Provider>
          </div>
        )}
        {sources.length > 0 && (
          <div className="sources">
            <h5>Sources</h5>
            <div className="chips">
              {sources.map((u) => <a key={u} className="chip link" href={u} target="_blank" rel="noopener noreferrer">{hostOf(u)}<ExternalLink size={10} /></a>)}
            </div>
          </div>
        )}
        {!failed && <FactCheck claims={res.claims} blocked={res.blocked} mode={agent.guardrails.fact_check} />}
        <div className="turn-foot">
          <button className="link-btn" onClick={() => setShowTrace(!showTrace)} aria-expanded={showTrace}>
            <FileSearch size={13} /> Execution · {res.steps.length} steps
          </button>
          <Link to={`/runs/${res.run_id}`} className="link-btn mono">{res.run_id}</Link>
        </div>
        {showTrace && <Trace steps={res.steps} compact />}
      </div>
    </div>
  );
}

function LiveTurn({ agent, steps, startedAt, onCancel }: { agent: AgentConfig; steps: RunStep[]; startedAt: number; onCancel: () => void }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, []);
  const last = steps[steps.length - 1];
  const phase = !last ? "Understanding the request" : last.type === "llm" && Array.isArray((last.output as { function_calls?: string[] } | null)?.function_calls)
    ? "Executing tools" : last.type === "tool" ? "Processing tool results" : last.type === "verify" ? "Finishing up" : "Producing the answer";
  return (
    <div className="turn agent live" aria-live="polite">
      <AgentAvatar seed={agent.id} size={30} />
      <div className="turn-body">
        <div className="turn-meta">
          <strong>{agent.name}</strong>
          <StatusPill status="running" />
          <span className="mono dim">{((now - startedAt) / 1000).toFixed(1)} s</span>
          <button className="link-btn" onClick={onCancel}><Square size={11} /> Stop waiting</button>
        </div>
        <div className="live-phase"><Loader2 size={14} className="spin" /> {phase}…</div>
        {steps.length > 0 ? <Trace steps={steps} compact running /> : <p className="muted sm">Waiting for the first step to be recorded…</p>}
      </div>
    </div>
  );
}

/* ---------- page ---------- */

export default function Chat() {
  const { id = "" } = useParams();
  const agent = useAsync(() => api.agent(id), [id]);
  useDocumentTitle(agent.data?.name ?? "Chat");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState<{ startedAt: number } | null>(null);
  const [liveSteps, setLiveSteps] = useState<RunStep[]>([]);
  const session = useRef(uid("session"));
  const abort = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "end" }); }, [turns, liveSteps, pending]);

  // Poll the real run record so the timeline reflects steps the backend has actually written.
  useEffect(() => {
    if (!pending) { setLiveSteps([]); return; }
    let alive = true;
    const tick = async () => {
      try {
        const runs = await api.runs({ agent_id: id, limit: 5 });
        const mine = runs.find((r) => r.session_id === session.current && r.status === "running");
        if (!mine) return;
        const detail = await api.run(mine.id);
        if (alive && detail.steps) setLiveSteps(detail.steps);
      } catch { /* polling is best-effort */ }
    };
    const t = setInterval(tick, 1200);
    return () => { alive = false; clearInterval(t); };
  }, [pending, id]);

  const send = useCallback(async (text: string) => {
    const msg = text.trim();
    if (!msg || pending) return;
    setInput("");
    setTurns((t) => [...t, { kind: "user", id: uid("u"), text: msg }]);
    const ctl = new AbortController();
    abort.current = ctl;
    setPending({ startedAt: Date.now() });
    try {
      const res = await api.chat(id, { message: msg, session_id: session.current, demo_user_id: "demo_user_01" }, ctl.signal);
      setTurns((t) => [...t, { kind: "agent", id: res.run_id, res }]);
    } catch (e) {
      if ((e as Error).name === "AbortError") setTurns((t) => [...t, { kind: "error", id: uid("e"), message: "You stopped waiting. The server may still finish this run; it will appear in the run history.", retryText: msg }]);
      else setTurns((t) => [...t, { kind: "error", id: uid("e"), message: (e as Error).message, retryText: msg }]);
    } finally {
      setPending(null);
      abort.current = null;
    }
  }, [id, pending]);

  if (agent.error) return <div className="page narrow"><ErrorBanner title="Couldn't load this agent" message={agent.error} onRetry={agent.reload} /></div>;
  if (!agent.data) return <div className="page narrow"><Skeleton h={48} /><Skeleton h={200} style={{ marginTop: 16 }} /></div>;
  const a = agent.data;

  if (a.status !== "deployed") {
    return (
      <div className="page narrow">
        <EmptyState icon={<AlertTriangle size={20} />} title={`${a.name} isn't deployed yet`} action={<Link to={`/builder/${a.id}`} className="btn primary">Open in builder</Link>}>
          Deploy the agent before chatting with it.
        </EmptyState>
      </div>
    );
  }
  const suggestions = SUGGESTIONS[a.template] ?? [];

  return (
    <div className="chat">
      <header className="chat-head">
        <AgentAvatar seed={a.id} size={38} />
        <div className="ch-main">
          <h1>{a.name}</h1>
          <div className="muted sm">{templateLabel(a.template)} · <span className="mono">{a.model}</span> · v{a.version}</div>
        </div>
        <div className="chips ch-tools">{a.tools.map((t) => <span key={t.name} className="chip mono"><ToolIcon name={t.name} size={10} />{t.name.replace(/^(serpapi|nessie)_/, "")}</span>)}</div>
        <StatusPill status="deployed" />
        <Link to={`/builder/${a.id}`} className="btn ghost sm">Configure</Link>
        <Link to={`/dashboard?agent=${a.id}`} className="btn ghost sm">Runs</Link>
      </header>

      <div className="thread" role="log" aria-label="Conversation">
        {turns.length === 0 && !pending && (
          <div className="chat-empty">
            <AgentAvatar seed={a.id} size={56} />
            <h2>Ask {a.name} anything</h2>
            <p className="muted">It will call its tools, show every step it takes, and check the figures in its answer against the data it retrieved.</p>
            {suggestions.length > 0 && (
              <div className="suggest">
                {suggestions.map((s) => (
                  <button key={s.label} className="suggest-card" onClick={() => send(s.text)}>
                    <strong>{s.label}</strong>
                    <span>{s.text}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        {turns.map((t) =>
          t.kind === "user" ? (
            <div key={t.id} className="turn user"><div className="bubble">{t.text}</div></div>
          ) : t.kind === "agent" ? (
            <AgentTurn key={t.id} res={t.res} agent={a} />
          ) : (
            <div key={t.id} className="turn error-turn">
              <ErrorBanner title="Message failed" message={t.message} />
              <button className="btn ghost sm" onClick={() => send(t.retryText)} disabled={!!pending}><RotateCcw size={13} /> Try again</button>
            </div>
          ),
        )}
        {pending && <LiveTurn agent={a} steps={liveSteps} startedAt={pending.startedAt} onCancel={() => abort.current?.abort()} />}
        <div ref={endRef} />
      </div>

      <form className="composer" onSubmit={(e) => { e.preventDefault(); send(input); }}>
        <textarea
          ref={taRef}
          value={input}
          rows={1}
          placeholder={`Message ${a.name}…`}
          aria-label="Message"
          onChange={(e) => { setInput(e.target.value); e.target.style.height = "auto"; e.target.style.height = Math.min(e.target.scrollHeight, 160) + "px"; }}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(input); } }}
        />
        <div className="composer-foot">
          <span className="muted sm"><kbd>Enter</kbd> to send · <kbd>Shift</kbd>+<kbd>Enter</kbd> for a new line</span>
          <button className="btn primary icon" type="submit" disabled={!input.trim() || !!pending} aria-label="Send message">{pending ? <Loader2 size={16} className="spin" /> : <ArrowUp size={16} />}</button>
        </div>
      </form>
    </div>
  );
}
