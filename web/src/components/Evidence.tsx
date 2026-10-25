import { ExternalLink, X } from "lucide-react";
import { describeFigure, money, toolName, type EvidenceRef, type FigureInfo } from "../lib/figures";

const pick = (item: EvidenceRef["item"], ...keys: string[]) => {
  for (const k of keys) {
    const v = item?.[k];
    if (v !== undefined && v !== null && v !== "") return String(v);
  }
  return null;
};

function Record({ r }: { r: EvidenceRef }) {
  const it = r.item ?? null;
  const title = pick(it, "title", "name", "description", "payee", "query");
  const who = pick(it, "merchant", "source", "seller", "payee");
  const when = pick(it, "purchase_date", "date", "published");
  const snippet = pick(it, "snippet");
  const url = pick(it, "url", "link");
  return (
    <div className="ev-rec">
      <div className="ev-src"><span className="mono">{money(r.value)}</span> · {toolName(r.tool)}, step {r.step}</div>
      {title && <div className="ev-title">{title}</div>}
      {(who || when) && <div className="ev-meta">{[who, when].filter(Boolean).join(" · ")}</div>}
      {snippet && <div className="ev-snip">"{snippet}"</div>}
      {url && /^https?:\/\//.test(url) && (
        <a className="ev-link" href={url} target="_blank" rel="noopener noreferrer">Open source <ExternalLink size={11} /></a>
      )}
    </div>
  );
}

/** What backs a figure: the tool record it matched, the two figures it was computed from, or where it came from. */
export default function EvidenceCard({ text, f, question, onClose }: { text: string; f: FigureInfo; question?: string; onClose: () => void }) {
  const ev = f.evidence;
  let body;
  if (f.ok && ev?.operands?.length === 2) {
    const [a, b] = ev.operands;
    const sign = ev.op === "+" ? "+" : "−";
    body = (
      <>
        <div className="ev-math mono">
          {money(Math.max(a.value, b.value))} {sign} {money(Math.min(a.value, b.value))}{ev.op === "-x12" ? " × 12" : ""} = {text}
        </div>
        <p className="ev-note">Computed from two figures that each match tool data:</p>
        <Record r={a} />
        <Record r={b} />
      </>
    );
  } else if (f.ok && ev) {
    body = (
      <>
        {ev.op === "x12" && <div className="ev-math mono">{money(ev.value)} per month × 12 = {text}</div>}
        <Record r={ev} />
      </>
    );
  } else if (f.ok) {
    body = <p className="ev-note">{describeFigure(f)}</p>;
  } else if (f.tool === "user_message") {
    body = (
      <>
        <p className="ev-note">This figure came from your message (or was computed from it). No tool returned it, so it stays flagged.</p>
        {question && <blockquote className="ev-quote">{question}</blockquote>}
      </>
    );
  } else {
    body = <p className="ev-note">Nothing in this run's tool data matches {text}. The agent stated it without a source.</p>;
  }
  return (
    <div className={`ev-card${f.ok ? "" : " u"}`} role="dialog" aria-label={`Evidence for ${text}`} onClick={(e) => e.stopPropagation()}>
      <div className="ev-head">
        <strong className="mono">{text}</strong>
        <span className={f.ok ? "ok-t" : "err-t"}>{f.ok ? "Backed by tool data" : "Not backed by tool data"}</span>
        <button className="icon-btn" onClick={onClose} aria-label="Close"><X size={14} /></button>
      </div>
      {body}
    </div>
  );
}
