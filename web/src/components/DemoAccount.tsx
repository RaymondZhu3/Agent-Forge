import { Loader2, X } from "lucide-react";
import { useEffect } from "react";
import { api } from "../lib/api";
import { money } from "../lib/figures";
import { useAsync } from "../lib/hooks";
import { ModeBadge } from "./ui";
import type { DataMode } from "../types";

/** Side drawer: the demo customer's purchases and bills, read with the agent's own banking tools. */
export default function DemoAccount({ agentId, onClose }: { agentId: string; onClose: () => void }) {
  const acct = useAsync(() => api.demoAccount(agentId), [agentId]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  const d = acct.data;
  const purchases = [...(d?.purchases?.purchases ?? [])].sort((a, b) => String(b.date ?? "").localeCompare(String(a.date ?? "")));
  const bills = d?.bills?.bills ?? [];
  const mode = (d?.modes?.purchases ?? null) as DataMode | null;

  return (
    <aside className="acct" role="dialog" aria-label="Demo account">
      <header className="acct-head">
        <div>
          <strong>Demo account</strong>
          <div className="muted sm">What this agent's banking tools return (Capital One Nessie sandbox)</div>
        </div>
        {mode && <ModeBadge mode={mode} />}
        <button className="icon-btn" onClick={onClose} aria-label="Close"><X size={16} /></button>
      </header>
      {acct.loading && !d && <p className="muted sm acct-pad"><Loader2 size={13} className="spin" /> Loading the account…</p>}
      {acct.error && <p className="err-t sm acct-pad">{acct.error}</p>}
      {d && (
        <div className="acct-body">
          <section>
            <h3>Purchases <span className="dim mono">{d.purchases?.purchase_count ?? purchases.length}</span>
              {d.purchases?.total_spent !== undefined && <span className="acct-total mono">{money(d.purchases.total_spent)}</span>}</h3>
            <ul className="acct-list">
              {purchases.map((p, i) => (
                <li key={i}>
                  <div><div className="acct-what">{p.description}</div><div className="dim sm">{[p.merchant, p.date].filter(Boolean).join(" · ")}</div></div>
                  <span className="mono">{p.amount !== undefined ? money(p.amount) : ""}</span>
                </li>
              ))}
            </ul>
          </section>
          <section>
            <h3>Recurring bills {d.bills?.recurring_monthly_total !== undefined && <span className="acct-total mono">{money(d.bills.recurring_monthly_total)}/mo</span>}</h3>
            <ul className="acct-list">
              {bills.map((b, i) => (
                <li key={i}>
                  <div><div className="acct-what">{b.name ?? b.payee}</div><div className="dim sm">{[b.payee, b.recurring_day_of_month ? `day ${b.recurring_day_of_month} of each month` : null].filter(Boolean).join(" · ")}</div></div>
                  <span className="mono">{b.amount !== undefined ? money(b.amount) : ""}</span>
                </li>
              ))}
            </ul>
          </section>
          <p className="dim sm">Read-only. The agent never moves money or changes accounts.</p>
        </div>
      )}
    </aside>
  );
}
