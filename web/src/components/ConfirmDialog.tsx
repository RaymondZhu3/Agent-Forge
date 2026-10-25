import { AlertTriangle, Loader2 } from "lucide-react";
import { useEffect } from "react";

export default function ConfirmDialog({ title, body, confirmLabel, busy, error, onConfirm, onCancel }: {
  title: string; body: string; confirmLabel: string; busy?: boolean; error?: string | null; onConfirm: () => void; onCancel: () => void;
}) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && !busy && onCancel();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [busy, onCancel]);
  return (
    <div className="modal-scrim" onClick={() => !busy && onCancel()} role="presentation">
      <div className="modal confirm" role="alertdialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <header>
          <span className="tool-icon verify" style={{ width: 36, height: 36 }}><AlertTriangle size={17} /></span>
          <div><h2>{title}</h2></div>
        </header>
        <p className="muted">{body}</p>
        {error && <p className="note warn"><AlertTriangle size={12} /> {error}</p>}
        <footer>
          <button className="btn ghost" onClick={onCancel} disabled={busy} autoFocus>Cancel</button>
          <button className="btn danger-solid" onClick={onConfirm} disabled={busy}>{busy && <Loader2 size={14} className="spin" />}{confirmLabel}</button>
        </footer>
      </div>
    </div>
  );
}
