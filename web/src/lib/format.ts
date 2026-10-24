export const fmtMs = (ms: number | null | undefined): string => {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(ms < 10000 ? 2 : 1)} s`;
};

export const fmtInt = (n: number | null | undefined): string => (n === null || n === undefined ? "—" : n.toLocaleString("en-US"));

export const fmtCompact = (n: number): string =>
  new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(n);

export const fmtPct = (x: number): string => `${(x * 100).toFixed(x > 0 && x < 0.1 ? 1 : 0)}%`;

export const fmtUsd = (x: number | null | undefined): string => (x === null || x === undefined ? "Not available" : `$${x.toFixed(4)}`);

export const fmtDateTime = (iso: string | null | undefined): string => {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", second: "2-digit" });
};

export const fmtTime = (iso: string): string => new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });

export const relTime = (iso: string | null | undefined): string => {
  if (!iso) return "—";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
};

export const shortId = (id: string): string => (id.length > 14 ? id.slice(0, 14) : id);

export const TEMPLATE_LABEL: Record<string, string> = { smart_spend: "Smart Spend", news_monitor: "News Monitor", blank: "Custom" };
export const templateLabel = (t: string): string => TEMPLATE_LABEL[t] ?? t;

export const uid = (prefix: string): string => `${prefix}_${Math.random().toString(36).slice(2, 10)}`;

export const hashStr = (s: string): number => {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
};

export const extractUrls = (text: string): string[] => {
  const found = text.match(/https?:\/\/[^\s)\]>"']+/g) ?? [];
  return [...new Set(found.map((u) => u.replace(/[.,;]+$/, "")))];
};

export const hostOf = (url: string): string => {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
};
