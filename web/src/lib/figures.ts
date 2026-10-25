/** Fact-check result for one figure as written, used to mark it in the answer and explain where it came from. */
export type FigureInfo = { ok: boolean; step?: number | null; tool?: string | null; how?: string | null };

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
