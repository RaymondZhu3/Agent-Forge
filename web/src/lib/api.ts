import type {
  AgentConfig, AgentCreate, AgentUpdate, AnalyticsSummary, ChatRequest, ChatResponse, Run, ToolAnalytics, ToolMetadata,
} from "../types";

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api";

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit & { signal?: AbortSignal }): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError("Can't reach the Agent Forge API. Check your connection or that the server is running.", 0);
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* keep default */
    }
    throw new ApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}

const qs = (params: Record<string, string | number | undefined | null>) => {
  const p = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "");
  return p.length ? "?" + p.map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&") : "";
};

export type Health = { ok: boolean; db: boolean; gemini: boolean; serpapi: "live" | "fixture"; nessie: "live" | "fixture" };

export const api = {
  health: () => request<Health>("/health"),
  tools: () => request<ToolMetadata[]>("/tools"),
  templates: () => request<AgentCreate[]>("/templates"),
  agents: () => request<AgentConfig[]>("/agents"),
  agent: (id: string) => request<AgentConfig>(`/agents/${id}`),
  createAgent: (body: AgentCreate) => request<AgentConfig>("/agents", { method: "POST", body: JSON.stringify(body) }),
  updateAgent: (id: string, body: AgentUpdate) => request<AgentConfig>(`/agents/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deploy: (id: string) => request<AgentConfig>(`/agents/${id}/deploy`, { method: "POST" }),
  chat: (id: string, body: ChatRequest, signal?: AbortSignal) =>
    request<ChatResponse>(`/agents/${id}/chat`, { method: "POST", body: JSON.stringify(body), signal }),
  runs: (p: { agent_id?: string; limit?: number }) => request<Run[]>(`/runs${qs(p)}`),
  run: (id: string) => request<Run>(`/runs/${id}`),
  summary: (agent_id?: string) => request<AnalyticsSummary>(`/analytics/summary${qs({ agent_id })}`),
  toolStats: (agent_id?: string) => request<ToolAnalytics[]>(`/analytics/tools${qs({ agent_id })}`),
};
