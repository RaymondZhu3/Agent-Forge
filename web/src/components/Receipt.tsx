import { ChevronDown, Fingerprint, Loader2, ShieldAlert, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { api } from "../lib/api";
import { receiptOf, verifyRun, type ReceiptCheck } from "../lib/receipt";
import type { Run, RunStep } from "../types";

const short = (h: string) => `${h.slice(0, 10)}…${h.slice(-6)}`;

/** Audit receipt for a run: the stored fingerprint chain, and a check of the stored record against it. */
export default function Receipt({ runId, steps, run }: { runId: string; steps: RunStep[]; run?: Run }) {
  const receipt = receiptOf(steps);
  const [check, setCheck] = useState<ReceiptCheck | { error: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  if (!receipt) return null;

  const verify = async () => {
    setBusy(true);
    try {
      // Always check the record as stored on the server, not the copy this page received.
      const stored = run ?? (await api.run(runId));
      setCheck(await verifyRun(stored));
    } catch (e) {
      setCheck({ error: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };
  const result = check && "ok" in check ? check : null;

  return (
    <div className={`receipt${result ? (result.ok ? " intact" : " broken") : ""}`}>
      <div className="rc-row">
        <Fingerprint size={15} className="rc-icon" />
        <div className="rc-main">
          <strong>Audit receipt</strong>
          <span className="mono rc-hash" title={receipt.hash}>{short(receipt.hash)}</span>
        </div>
        {result ? (
          <span className={`rc-result ${result.ok ? "ok" : "bad"}`} role="status">
            {result.ok ? <ShieldCheck size={14} /> : <ShieldAlert size={14} />} {result.ok ? "Record intact" : "Record changed"}
          </span>
        ) : check && "error" in check ? (
          <span className="rc-result bad" role="status"><ShieldAlert size={14} /> Couldn't load the stored run</span>
        ) : null}
        <button className="btn sm" onClick={verify} disabled={busy}>
          {busy ? <Loader2 size={13} className="spin" /> : null} {result ? "Verify again" : "Verify record"}
        </button>
      </div>
      {result && <p className="rc-reason sm muted">{result.reason}</p>}
      <button className="link-btn rc-toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
        <ChevronDown size={12} className={`chev${open ? " open" : ""}`} /> {open ? "Hide" : "Show"} the fingerprint chain
      </button>
      {open && (
        <ol className="rc-chain">
          {receipt.steps.map((h, i) => (
            <li key={h} className={result && !result.ok && result.badIndex === i ? "bad" : ""}>
              <span className="dim">step {steps[i]?.step ?? i + 1}</span>
              <span>{steps[i]?.toolName ?? steps[i]?.type ?? ""}</span>
              <span className="mono">{short(h)}</span>
            </li>
          ))}
          <li className={`rc-final${result && !result.ok && result.badIndex === receipt.steps.length ? " bad" : ""}`}><span className="dim">answer</span><span>final receipt</span><span className="mono">{short(receipt.hash)}</span></li>
        </ol>
      )}
      <p className="rc-note sm dim">SHA-256 chain over the question, every step and the answer. Changing anything in the stored record breaks it.</p>
    </div>
  );
}
