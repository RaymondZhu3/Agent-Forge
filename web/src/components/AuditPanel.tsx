import { Loader2, ShieldCheck, ShieldAlert } from "lucide-react";
import { Fragment, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { receiptOf, verifyRun } from "../lib/receipt";

type VOut = { invented?: string[]; fixed?: string[]; user_supplied?: string[]; used_correction?: boolean; draft?: string; claims?: number; verified?: number };
type Tally = { runs: number; figures: number; backed: number; user: number; madeUp: number; corrected: number; receipts: number; intact: number; changed: string[] };

/** Re-audit recent runs from the stored records: re-check every receipt and count what the fact-check caught. */
export default function AuditPanel({ agentId, limit = 25 }: { agentId?: string; limit?: number }) {
  const [t, setT] = useState<Tally | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const audit = async () => {
    setBusy(true);
    setErr(null);
    try {
      const list = (await api.runs({ agent_id: agentId, limit })).filter((r) => r.status === "completed");
      const runs = await Promise.all(list.map((r) => api.run(r.id).catch(() => null)));
      const tally: Tally = { runs: 0, figures: 0, backed: 0, user: 0, madeUp: 0, corrected: 0, receipts: 0, intact: 0, changed: [] };
      for (const run of runs) {
        if (!run) continue;
        tally.runs++;
        const v = (run.steps ?? []).filter((s) => s.type === "verify").map((s) => (s.output ?? {}) as VOut);
        const draft = v.find((o) => o.draft !== undefined);
        const final = v[v.length - 1] ?? {};
        tally.figures += final.claims ?? run.claims_total ?? 0;
        tally.backed += final.verified ?? run.claims_verified ?? 0;
        tally.user += new Set(final.user_supplied ?? []).size;
        tally.madeUp += draft?.invented?.length ?? 0;
        tally.corrected += final.used_correction ? final.fixed?.length ?? 0 : 0;
        if (receiptOf(run.steps)) {
          tally.receipts++;
          const c = await verifyRun(run);
          if (c.ok) tally.intact++;
          else tally.changed.push(run.id);
        }
      }
      setT(tally);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className={`card audit${t && t.changed.length ? " bad" : ""}`}>
      <div className="card-head">
        <h2>Audit recent runs</h2>
        <button className="btn sm" onClick={audit} disabled={busy}>
          {busy ? <Loader2 size={13} className="spin" /> : <ShieldCheck size={13} />} {t ? "Audit again" : `Audit the last ${limit} runs`}
        </button>
      </div>
      {!t && !busy && !err && <p className="muted sm">Re-checks every stored run: recomputes each audit receipt from the database and counts what the fact-check caught.</p>}
      {err && <p className="err-t sm">{err}</p>}
      {t && (
        <>
          <div className="audit-big">
            {t.changed.length ? <ShieldAlert size={20} /> : <ShieldCheck size={20} />}
            <strong>{t.receipts ? `${t.intact} of ${t.receipts} receipts intact` : "No receipts yet"}</strong>
            <span className="muted sm">{t.runs} runs audited{t.receipts < t.runs ? ` · ${t.runs - t.receipts} from before receipts existed` : ""}</span>
          </div>
          <dl className="audit-stats">
            <div><dt>Figures checked</dt><dd className="mono">{t.figures}</dd></div>
            <div><dt>Backed by tool data</dt><dd className="mono ok-t">{t.backed}</dd></div>
            <div><dt>User's numbers flagged</dt><dd className="mono">{t.user}</dd></div>
            <div><dt>Made up by the model</dt><dd className="mono err-t">{t.madeUp}</dd></div>
            <div><dt>Corrected before shown</dt><dd className="mono ok-t">{t.corrected}</dd></div>
          </dl>
          {t.changed.length > 0 && (
            <p className="err-t sm">Changed after the run: {t.changed.map((id, i) => <Fragment key={id}>{i ? ", " : ""}<Link className="mono" to={`/runs/${id}`}>{id}</Link></Fragment>)}</p>
          )}
        </>
      )}
    </section>
  );
}
