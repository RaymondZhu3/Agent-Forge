import { ArrowLeft, ArrowUp, Loader2, ShieldCheck, ShieldOff } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import Markdown, { FigureMarks } from "../components/Markdown";
import { ErrorBanner, Skeleton } from "../components/ui";
import { api } from "../lib/api";
import { figureMap, figureMapFromSteps } from "../lib/figures";
import { fmtMs, uid } from "../lib/format";
import { useAsync, useDocumentTitle } from "../lib/hooks";
import type { AgentConfig, ChatResponse } from "../types";
import { FactCheck, SelfCorrection, SUGGESTIONS } from "./Chat";

const COPY_SUFFIX = " (no fact-check)";
const PROMPTS: Record<string, string[]> = {
  smart_spend: [
    "Someone told me my Logitech MX Master 3S mouse is $59 on Amazon. Is that true?",
    "Netflix just raised prices by 40%. How much more will I pay per year?",
    "What will the MX Master 3S cost on Black Friday?",
  ],
  quick_quote: ["What do AirPods Pro 2 usually cost, and what's a good Black Friday price to wait for?"],
};

/** The same agent with the fact-check off, created once (clearly named) and reused. */
async function unauditedCopy(a: AgentConfig): Promise<AgentConfig> {
  const all = await api.agents();
  const name = a.name + COPY_SUFFIX;
  let copy = all.find((x) => x.name === name && x.template === a.template);
  if (!copy) {
    copy = await api.createAgent({
      name, template: a.template, model: a.model, instructions: a.instructions, tools: a.tools,
      guardrails: { ...a.guardrails, fact_check: "off" },
    });
  }
  if (copy.status !== "deployed") copy = await api.deploy(copy.id);
  return copy;
}

type Side = { res?: ChatResponse; error?: string; busy: boolean };

function countFigures(text: string) {
  return (text.match(/\$\s?\d[\d,]*(?:\.\d+)?|\d+(?:\.\d+)?\s?%/g) ?? []).length;
}

export default function Compare() {
  const { id = "" } = useParams();
  const agent = useAsync(() => api.agent(id), [id]);
  useDocumentTitle("Compare");
  const [input, setInput] = useState("");
  const [question, setQuestion] = useState("");
  const [left, setLeft] = useState<Side>({ busy: false });
  const [right, setRight] = useState<Side>({ busy: false });

  if (agent.error) return <div className="page narrow"><ErrorBanner title="Couldn't load this agent" message={agent.error} onRetry={agent.reload} /></div>;
  if (!agent.data) return <div className="page"><Skeleton h={48} /><Skeleton h={300} style={{ marginTop: 16 }} /></div>;
  const a = agent.data;
  const prompts = PROMPTS[a.template] ?? (SUGGESTIONS[a.template] ?? []).map((s) => s.text);

  const ask = async (text: string) => {
    const q = text.trim();
    if (!q || left.busy || right.busy) return;
    setQuestion(q);
    setInput("");
    setLeft({ busy: true });
    setRight({ busy: true });
    const session = uid("compare");
    const audited = api.chat(a.id, { message: q, session_id: session })
      .then((res) => setRight({ res, busy: false }), (e) => setRight({ error: (e as Error).message, busy: false }));
    const raw = unauditedCopy(a)
      .then((copy) => api.chat(copy.id, { message: q, session_id: session }))
      .then((res) => setLeft({ res, busy: false }), (e) => setLeft({ error: (e as Error).message, busy: false }));
    await Promise.all([audited, raw]);
  };

  return (
    <div className="page wide">
      <Link to={`/chat/${a.id}`} className="back"><ArrowLeft size={14} /> Back to chat</Link>
      <header className="page-head">
        <div>
          <h1>Same question, with and without Agent Forge</h1>
          <p className="muted">Left: {a.name} with the fact-check off. Right: the same agent, audited. Same model, tools and instructions.</p>
        </div>
      </header>

      <form className="cmp-ask" onSubmit={(e) => { e.preventDefault(); ask(input); }}>
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder={`Ask ${a.name} something…`} aria-label="Question" />
        <button className="btn primary" type="submit" disabled={!input.trim() || left.busy || right.busy}><ArrowUp size={15} /> Ask both</button>
      </form>
      {prompts.length > 0 && (
        <div className="chips">
          {prompts.map((p) => <button key={p} className="chip cmp-chip" onClick={() => ask(p)} disabled={left.busy || right.busy}>{p}</button>)}
        </div>
      )}
      {question && <p className="cmp-q"><span className="dim">Question:</span> {question}</p>}

      {question && (
        <div className="cmp-grid">
          <section className="cmp-col raw">
            <header><ShieldOff size={15} /> <strong>No fact-check</strong><span className="muted sm">every number is presented as fact</span></header>
            {left.busy && <p className="cmp-wait"><Loader2 size={14} className="spin" /> Answering…</p>}
            {left.error && <ErrorBanner title="The unaudited copy couldn't answer" message={left.error} />}
            {left.res && (
              <>
                <div className="answer"><Markdown text={left.res.assistant_message || left.res.error || ""} /></div>
                <p className="cmp-foot sm">{countFigures(left.res.assistant_message)} figures, <strong>none checked</strong> · {fmtMs(left.res.total_latency_ms)}</p>
              </>
            )}
          </section>
          <section className="cmp-col audited">
            <header><ShieldCheck size={15} /> <strong>Audited by Agent Forge</strong><span className="muted sm">checked against this run's tool data</span></header>
            {right.busy && <p className="cmp-wait"><Loader2 size={14} className="spin" /> Answering and checking…</p>}
            {right.error && <ErrorBanner title="The agent couldn't answer" message={right.error} />}
            {right.res && (
              <>
                <SelfCorrection res={right.res} />
                <div className="answer">
                  <FigureMarks.Provider value={figureMapFromSteps(right.res.steps) ?? figureMap(right.res.claims)}>
                    <Markdown text={right.res.assistant_message || right.res.error || ""} />
                  </FigureMarks.Provider>
                </div>
                <FactCheck claims={right.res.claims} blocked={right.res.blocked} mode={a.guardrails.fact_check} />
                <p className="cmp-foot sm"><Link to={`/runs/${right.res.run_id}`}>Open the audited run</Link> · {fmtMs(right.res.total_latency_ms)}</p>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
