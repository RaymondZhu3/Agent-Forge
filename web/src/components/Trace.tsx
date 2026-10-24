import { AlertTriangle, BrainCircuit, ChevronRight, Loader2, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { fmtInt, fmtMs } from "../lib/format";
import type { RunStep } from "../types";
import ToolIcon from "./ToolIcon";
import { ModeBadge, modeOf } from "./ui";

type Out = Record<string, unknown> | null;
const asObj = (v: unknown): Out => (v && typeof v === "object" ? (v as Record<string, unknown>) : null);

/** Human label derived strictly from what the backend recorded for the step. */
export function stepLabel(s: RunStep): { title: string; detail: string } {
  const out = asObj(s.output);
  if (s.type === "tool") {
    const summary = typeof out?.summary === "string" ? out.summary : s.error ?? "";
    return { title: s.toolName ?? "tool", detail: summary };
  }
  if (s.type === "verify") {
    const claims = out?.claims, verified = out?.verified;
    return { title: "Fact-check", detail: claims !== undefined ? `${verified ?? 0} of ${claims} figures verified against tool data` : "Checked figures against tool results" };
  }
  const calls = out?.function_calls;
  if (Array.isArray(calls) && calls.length) return { title: "Selecting tools", detail: calls.join(", ") };
  if (out && "final_answer_chars" in out) return { title: "Writing the answer", detail: `${fmtInt(Number(out.final_answer_chars))} characters` };
  return { title: s.success ? "Model call" : "Model call failed", detail: s.error ?? "" };
}

function StepIcon({ s }: { s: RunStep }) {
  if (s.type === "tool" && s.toolName) return <ToolIcon name={s.toolName} size={14} />;
  if (s.type === "verify") return <span className="tool-icon verify" style={{ width: 28, height: 28 }}><ShieldCheck size={14} /></span>;
  return <span className="tool-icon model" style={{ width: 28, height: 28 }}><BrainCircuit size={14} /></span>;
}

function Json({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className="dim">—</span>;
  return <pre className="json">{JSON.stringify(value, null, 2)}</pre>;
}

export default function Trace({ steps, running = false, compact = false }: { steps: RunStep[]; running?: boolean; compact?: boolean }) {
  const [open, setOpen] = useState<Set<number>>(new Set());
  const total = steps.reduce((a, s) => a + s.ms, 0) || 1;
  const toggle = (n: number) =>
    setOpen((p) => {
      const q = new Set(p);
      q.has(n) ? q.delete(n) : q.add(n);
      return q;
    });

  return (
    <ol className={`trace${compact ? " compact" : ""}`}>
      {steps.map((s, idx) => {
        const { title, detail } = stepLabel(s);
        const isOpen = open.has(s.step);
        return (
          <li key={s.step} className={`trace-step ${s.success ? "" : "failed"}`} style={{ animationDelay: `${Math.min(idx, 8) * 40}ms` }}>
            <span className="rail" aria-hidden />
            <button className="trace-row" onClick={() => toggle(s.step)} aria-expanded={isOpen}>
              <StepIcon s={s} />
              <span className="trace-main">
                <span className="trace-title">
                  <span className={s.type === "tool" ? "mono" : ""}>{title}</span>
                  {s.type === "tool" && <ModeBadge mode={modeOf(s)} />}
                  {!s.success && (
                    <span className="pill err">
                      <AlertTriangle size={10} /> Failed
                    </span>
                  )}
                </span>
                {detail && <span className="trace-detail">{detail}</span>}
                {!compact && (
                  <span className="bar" aria-hidden>
                    <span style={{ width: `${Math.max(2, (s.ms / total) * 100)}%` }} className={s.type} />
                  </span>
                )}
              </span>
              <span className="trace-meta">
                <span className="mono">{fmtMs(s.ms)}</span>
                {s.tokens !== null && !compact && <span className="mono dim">{fmtInt(s.tokens)} tok</span>}
              </span>
              <ChevronRight size={14} className={`chev${isOpen ? " open" : ""}`} />
            </button>
            {isOpen && (
              <div className="trace-body">
                <div>
                  <h5>Input</h5>
                  <Json value={s.input} />
                </div>
                <div>
                  <h5>Output</h5>
                  <Json value={s.output} />
                </div>
                {s.error && (
                  <div className="full">
                    <h5>Error</h5>
                    <pre className="json err">{s.error}</pre>
                  </div>
                )}
              </div>
            )}
          </li>
        );
      })}
      {running && (
        <li className="trace-step pending">
          <span className="rail" aria-hidden />
          <div className="trace-row static">
            <span className="tool-icon model" style={{ width: 28, height: 28 }}>
              <Loader2 size={14} className="spin" />
            </span>
            <span className="trace-main">
              <span className="trace-title dim">Waiting for the next step…</span>
            </span>
          </div>
        </li>
      )}
    </ol>
  );
}
