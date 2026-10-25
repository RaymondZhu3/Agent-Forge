/** Fact-check result for one figure as written, used to mark it in the answer and explain where it came from. */
export type EvidenceRef = { value: number; step: number; tool: string; item?: Record<string, string | number> | null };
export type Evidence = EvidenceRef & { kind: string; op?: string; operands?: EvidenceRef[] };
export type FigureInfo = { ok: boolean; step?: number | null; tool?: string | null; how?: string | null; evidence?: Evidence | null };

export const TOOL_NAMES: Record<string, string> = {
  nessie_purchases: "Nessie purchases", nessie_bills: "Nessie bills", nessie_accounts: "Nessie accounts",
  serpapi_shopping: "Google Shopping", serpapi_web_search: "Google search", serpapi_news: "Google News", serpapi_local_places: "Google Local",
};

const HOW: Record<string, string> = {
  exact: "exact match", difference: "difference of two checked figures", sum: "sum of two checked figures", annualized: "monthly figure × 12",
};

export function toolName(t?: string | null) {
  return (t && TOOL_NAMES[t]) || t || "a tool";
}

export function describeFigure(f: FigureInfo): string {
  if (f.ok) return `${toolName(f.tool)}, step ${f.step}${f.how && HOW[f.how] ? ` · ${HOW[f.how]}` : ""}`;
  if (f.tool === "user_message") return "From your message. No tool confirms it.";
  return "No tool returned this figure.";
}

/** One entry per figure as written; a figure counts as backed if any mention of it is. */
export function figureMap(claims: { text: string; verified: boolean; source_step?: number | null; source_tool?: string | null; how?: string | null }[]) {
  const m = new Map<string, FigureInfo>();
  for (const c of claims) {
    const cur = m.get(c.text);
    if (!cur || (!cur.ok && c.verified)) m.set(c.text, { ok: c.verified, step: c.source_step, tool: c.source_tool, how: c.how });
  }
  return m;
}

type StepLike = { type: string; output?: unknown };

/** Figure results with evidence, from the run's final verify step ([text, verified, tool, step, how, evidence]). */
export function figureMapFromSteps(steps: StepLike[] | null | undefined): Map<string, FigureInfo> | null {
  for (let i = (steps?.length ?? 0) - 1; i >= 0; i--) {
    const figs = (steps![i].output as { figures?: unknown[][] } | null)?.figures;
    if (!Array.isArray(figs)) continue;
    const m = new Map<string, FigureInfo>();
    for (const [text, ok, tool, step, how, evidence] of figs as [string, boolean, string | null, number | null, string | null, Evidence | null][]) {
      const cur = m.get(text);
      if (!cur || (!cur.ok && ok)) m.set(text, { ok, tool, step, how, evidence: evidence ?? null });
    }
    return m;
  }
  return null;
}

export const money = (v: number) => "$" + v.toLocaleString("en-US", { minimumFractionDigits: v % 1 ? 2 : 0, maximumFractionDigits: 2 });

/** Rebuild a chat response from a stored run, for replaying it (figures carry the per-claim results). */
export function claimsFromSteps(steps: StepLike[] | null | undefined) {
  for (let i = (steps?.length ?? 0) - 1; i >= 0; i--) {
    const figs = (steps![i].output as { figures?: unknown[][] } | null)?.figures;
    if (!Array.isArray(figs)) continue;
    return (figs as [string, boolean, string | null, number | null, string | null, unknown, string?][]).map(
      ([text, verified, source_tool, source_step, how, , context]) => ({ text, verified, source_tool, source_step, how, context: context ?? "" }),
    );
  }
  return [];
}
