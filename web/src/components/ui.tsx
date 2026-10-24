import { AlertTriangle, Check, CircleDashed, Database, Loader2, RefreshCw, Sparkles, X, Zap } from "lucide-react";
import type { ReactNode } from "react";
import type { DataMode, RunStatus } from "../types";

export function StatusPill({ status }: { status: RunStatus | "draft" | "deployed" | "deploying" | "error" }) {
  const map: Record<string, { cls: string; label: string; icon: ReactNode }> = {
    completed: { cls: "ok", label: "Completed", icon: <Check size={11} /> },
    deployed: { cls: "ok", label: "Deployed", icon: <Check size={11} /> },
    failed: { cls: "err", label: "Failed", icon: <X size={11} /> },
    error: { cls: "err", label: "Error", icon: <AlertTriangle size={11} /> },
    running: { cls: "info", label: "Running", icon: <Loader2 size={11} className="spin" /> },
    deploying: { cls: "info", label: "Deploying", icon: <Loader2 size={11} className="spin" /> },
    draft: { cls: "muted", label: "Draft", icon: <CircleDashed size={11} /> },
  };
  const s = map[status] ?? map.draft;
  return (
    <span className={`pill ${s.cls}`}>
      {s.icon}
      {s.label}
    </span>
  );
}

export function modeOf(step: { cached: boolean | null; fixture: boolean | null }): DataMode {
  return step.fixture ? "fixture" : step.cached ? "cached" : "live";
}

const MODE_LABEL: Record<DataMode, string> = { live: "Live", cached: "Cached", fixture: "Demo data" };
const MODE_TIP: Record<DataMode, string> = {
  live: "Fetched from the real API during this run",
  cached: "Served from the cache of an earlier live request",
  fixture: "Local demo data, not a live API call",
};

export function ModeBadge({ mode }: { mode: DataMode }) {
  const icon = mode === "live" ? <Zap size={10} /> : mode === "cached" ? <Database size={10} /> : <Sparkles size={10} />;
  return (
    <span className={`mode ${mode}`} title={MODE_TIP[mode]}>
      {icon}
      {MODE_LABEL[mode]}
    </span>
  );
}

export function Skeleton({ h = 14, w = "100%", style }: { h?: number; w?: number | string; style?: React.CSSProperties }) {
  return <div className="skeleton" style={{ height: h, width: w, ...style }} aria-hidden />;
}

export function EmptyState({ icon, title, children, action }: { icon: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      <div className="empty-icon">{icon}</div>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function ErrorBanner({ message, onRetry, title = "Something went wrong" }: { message: string; onRetry?: () => void; title?: string }) {
  return (
    <div className="banner err" role="alert">
      <AlertTriangle size={16} />
      <div>
        <strong>{title}</strong>
        <span>{message}</span>
      </div>
      {onRetry && (
        <button className="btn ghost sm" onClick={onRetry}>
          <RefreshCw size={13} /> Retry
        </button>
      )}
    </div>
  );
}

export function Mono({ children, dim }: { children: ReactNode; dim?: boolean }) {
  return <span className={`mono${dim ? " dim" : ""}`}>{children}</span>;
}
