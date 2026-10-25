import { History, Loader2, X } from "lucide-react";
import { useEffect } from "react";
import { api } from "../lib/api";
import { claimsFromSteps } from "../lib/figures";
import { relTime } from "../lib/format";
import { useAsync } from "../lib/hooks";
import type { ChatResponse, DataMode, Run } from "../types";

/** A stored run, shaped like a live chat response so the chat can show it the same way. */
export function runToResponse(run: Run): ChatResponse {
  const steps = run.steps ?? [];
  const modes = new Set<DataMode>();
  for (const s of steps) {
    const m = (s.output as { mode?: DataMode } | null)?.mode;
    if (s.type === "tool" && m) modes.add(m);
  }
  return {
    run_id: run.id,
    assistant_message: run.assistant_message ?? "",
    status: run.status,
    usage: { input_tokens: run.input_tokens, output_tokens: run.output_tokens },
    total_latency_ms: run.total_latency_ms ?? 0,
    steps,
    claims: claimsFromSteps(steps) as ChatResponse["claims"],
    blocked: run.blocked,
    data_modes: [...modes],
    error: run.error,
  };
}

/** Pick a recorded run to replay when the model is down or slow. Replays are always labeled as such. */
export default function ReplayPicker({ agentId, onPick, onClose }: { agentId: string; onPick: (run: Run) => void; onClose: () => void }) {
  const runs = useAsync(() => api.runs({ agent_id: agentId, limit: 20 }), [agentId]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  const done = (runs.data ?? []).filter((r) => r.status === "completed" && r.assistant_message);

  const pick = async (id: string) => {
    try { onPick(await api.run(id)); } catch { /* the list stays open; try another */ }
  };

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal replay" role="dialog" aria-label="Replay a recorded run" onClick={(e) => e.stopPropagation()}>
        <header className="replay-head">
          <History size={16} />
          <div>
            <strong>Replay a recorded run</strong>
            <div className="muted sm">Shows a stored answer exactly as it was checked, labeled as a replay. Use it if the model is down or slow.</div>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><X size={16} /></button>
        </header>
        {runs.loading && !runs.data && <p className="muted sm"><Loader2 size={13} className="spin" /> Loading runs…</p>}
        {runs.error && <p className="err-t sm">{runs.error}</p>}
        {runs.data && done.length === 0 && <p className="muted sm">No completed runs for this agent yet.</p>}
        <ul className="replay-list">
          {done.map((r) => (
            <li key={r.id}>
              <button onClick={() => pick(r.id)}>
                <span className="replay-q">{r.user_message}</span>
                <span className="dim sm">{relTime(r.started_at)} · {r.claims_total ? `${r.claims_verified} of ${r.claims_total} figures verified` : "no figures"}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
