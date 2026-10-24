// Mirror of server/schemas.py — FROZEN contracts.
// Change only with team agreement, in the same commit as schemas.py and docs/API.md.

// ---------- Agent configuration ----------

export type ToolConfig = {
  name: string;
  settings: Record<string, unknown>;
};

export type Guardrails = {
  read_only_financial_data: boolean;
  max_tool_calls: number;
  require_confirmation_for_external_actions: boolean;
  /** "flag" = mark unverified figures; "block" = redact them; "off" = skip */
  fact_check: "flag" | "block" | "off";
};

export type AgentStatus = "draft" | "deployed";

export type AgentConfig = {
  id: string;
  name: string;
  template: string; // "smart_spend" | "news_monitor" | "blank"
  model: string;
  instructions: string;
  tools: ToolConfig[];
  guardrails: Guardrails;
  status: AgentStatus;
  version: number;
  created_at: string | null;
  updated_at: string | null;
  deployed_at: string | null;
};

export type AgentCreate = {
  name: string;
  template: string;
  model?: string | null;
  instructions: string;
  tools: ToolConfig[];
  guardrails?: Guardrails;
};

export type AgentUpdate = Partial<Pick<AgentConfig, "name" | "model" | "instructions" | "tools" | "guardrails">>;

// ---------- Tools ----------

export type JsonSchema = {
  type: "object";
  properties: Record<string, { type: string; description?: string; enum?: string[]; default?: unknown }>;
  required?: string[];
};

export type ToolMetadata = {
  name: string;
  label: string;
  source: string;
  category: string;
  description: string;
  parameters: JsonSchema;
  settingsSchema: JsonSchema;
};

// ---------- Runs ----------

export type StepType = "llm" | "tool" | "verify";
export type RunStatus = "running" | "completed" | "failed";
export type DataMode = "live" | "cached" | "fixture";

export type RunStep = {
  runId: string;
  agentId: string;
  step: number;
  type: StepType;
  toolName: string | null;
  input: unknown;
  output: unknown;
  ms: number;
  tokens: number | null;
  inputTokens: number | null;
  outputTokens: number | null;
  success: boolean;
  cached: boolean | null;
  fixture: boolean | null;
  error: string | null;
};

export type Claim = {
  text: string;
  context: string;
  verified: boolean;
  source_step: number | null;
  source_tool: string | null;
  how: "exact" | "difference" | "sum" | "annualized" | null;
};

export type Usage = { input_tokens: number | null; output_tokens: number | null };

export type ChatRequest = {
  message: string;
  session_id?: string;
  demo_user_id?: string;
};

export type ChatResponse = {
  run_id: string;
  assistant_message: string;
  status: RunStatus;
  usage: Usage;
  total_latency_ms: number;
  steps: RunStep[];
  claims: Claim[];
  blocked: boolean;
  data_modes: DataMode[];
  error: string | null;
};

export type Run = {
  id: string;
  agent_id: string;
  session_id: string | null;
  status: RunStatus;
  user_message: string;
  assistant_message: string | null;
  started_at: string;
  completed_at: string | null;
  total_latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  estimated_cost_usd: number | null;
  claims_total: number;
  claims_verified: number;
  blocked: boolean;
  error: string | null;
  steps?: RunStep[] | null;
};

// ---------- Analytics ----------

export type AnalyticsSummary = {
  total_runs: number;
  completed_runs: number;
  failed_runs: number;
  error_rate: number;
  avg_latency_ms: number | null;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number | null;
  serpapi_calls: number;
  cache_hits: number;
  claims_total: number;
  claims_verified: number;
  runs_over_time: { bucket: string; runs: number; failed: number }[];
};

export type ToolAnalytics = {
  tool_name: string;
  calls: number;
  errors: number;
  avg_ms: number | null;
  cache_hits: number;
  fixture_calls: number;
};
