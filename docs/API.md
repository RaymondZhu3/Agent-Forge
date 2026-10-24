# Agent Forge — API & Integration Contracts

**Frozen.** Canonical types: `server/schemas.py` (Python) and `web/src/types.ts` (TypeScript).
Change only with team agreement, updating all three files in one commit.

Base URL: `/api`. JSON everywhere. Run steps use camelCase keys; everything else is snake_case.

---

## Ownership

| Folder | Owner | Notes |
|---|---|---|
| `/tools`, `/server/runtime` | Person 1 | Tool registry, SerpApi + Nessie tools, cache hooks, Gemini runtime, fact-check |
| `/server` (except `runtime`), `/server/tests` | Person 2 | FastAPI app, DB models, routes, analytics, Nessie seed, Vultr deploy |
| `/web` | Person 3 | Builder, chat, dashboard, run detail |
| `server/schemas.py`, `web/src/types.ts`, `docs/API.md` | Everyone | Frozen; change only by agreement |

---

## Python integration points (Person 1 ↔ Person 2)

```python
# Person 1 provides:
from server.runtime import run_agent, RunHooks
from tools.registry import registry          # registry.list_metadata() -> GET /api/tools
from tools.cache import set_cache_backend    # Person 2 plugs in the tool_cache table
from server.runtime.templates import TEMPLATES  # list[AgentCreate] -> GET /api/templates

response: ChatResponse = run_agent(
    agent: AgentConfig,          # loaded from DB; must be status="deployed"
    message: str,
    session_id: str | None,
    hooks: RunHooks,             # Person 2's DB writer
)

# Person 2 implements (class with these methods) and passes it as `hooks`:
class RunHooks(Protocol):
    def on_run_start(self, run_id: str, agent_id: str, session_id: str | None, user_message: str) -> None: ...
    def on_step(self, step: RunStep) -> None: ...                 # called as each step finishes
    def on_run_finish(self, response: ChatResponse) -> None: ...  # final status, answer, usage, claims

# Person 2 implements for the tool_cache table, registered at app startup:
set_cache_backend(
    get=lambda key: dict | None,                                   # None if missing or expired
    set=lambda key, tool_name, result: dict, ttl_seconds: int: None,
)
```

`run_agent` never raises for model/tool failures: it returns `status="failed"` with a user-safe `error`, and still calls `on_run_finish`.
Default hooks/cache are in-memory, so each side can run without the other.

---

## Endpoints

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/api/health` | – | `{ "ok": true, "db": true, "gemini": true, "serpapi": "live" \| "fixture", "nessie": "live" \| "fixture" }` |
| GET | `/api/tools` | – | `ToolMetadata[]` |
| GET | `/api/templates` | – | `AgentCreate[]` (prefilled starting configs) |
| GET | `/api/agents` | – | `AgentConfig[]` |
| POST | `/api/agents` | `AgentCreate` | `AgentConfig` (status `draft`) |
| GET | `/api/agents/{id}` | – | `AgentConfig` |
| PATCH | `/api/agents/{id}` | `AgentUpdate` | `AgentConfig` (version + 1) |
| POST | `/api/agents/{id}/deploy` | – | `AgentConfig` (status `deployed`, `deployed_at` set) |
| POST | `/api/agents/{id}/chat` | `ChatRequest` | `ChatResponse` |
| GET | `/api/runs?agent_id=&limit=50` | – | `Run[]` (no steps) |
| GET | `/api/runs/{id}` | – | `Run` with `steps` |
| GET | `/api/analytics/summary?agent_id=` | – | `AnalyticsSummary` |
| GET | `/api/analytics/tools?agent_id=` | – | `ToolAnalytics[]` |

Errors: `{ "detail": "user-safe message" }` with 400 (validation), 404 (unknown agent/run), 409 (chat with a non-deployed agent), 502 (upstream API down and nothing cached).

---

## Example data (frontend can build against these)

### `GET /api/tools`
```json
[
  {
    "name": "serpapi_shopping",
    "label": "Shopping Prices",
    "source": "serpapi:google_shopping",
    "category": "search",
    "description": "Look up current prices for a product across online stores...",
    "parameters": { "type": "object", "properties": { "query": { "type": "string", "description": "Product name" } }, "required": ["query"] },
    "settingsSchema": { "type": "object", "properties": { "location": { "type": "string", "default": "Austin, Texas" } } }
  },
  {
    "name": "nessie_purchases",
    "label": "Purchases",
    "source": "nessie",
    "category": "banking",
    "description": "Get the customer's recent purchases with deterministic totals by merchant.",
    "parameters": { "type": "object", "properties": {} },
    "settingsSchema": { "type": "object", "properties": { "customer_id": { "type": "string" } } }
  }
]
```
Full tool list: `serpapi_shopping`, `serpapi_news`, `serpapi_web_search`, `serpapi_local_places`, `nessie_accounts`, `nessie_purchases`, `nessie_bills`.

### `AgentConfig`
```json
{
  "id": "agent-smart-spend",
  "name": "Smart Spend",
  "template": "smart_spend",
  "model": "gemini-2.5-flash",
  "instructions": "Analyze purchases and identify realistic savings opportunities.",
  "tools": [
    { "name": "nessie_accounts", "settings": { "customer_id": "DEMO_CUSTOMER_ID" } },
    { "name": "nessie_purchases", "settings": { "customer_id": "DEMO_CUSTOMER_ID" } },
    { "name": "nessie_bills", "settings": { "customer_id": "DEMO_CUSTOMER_ID" } },
    { "name": "serpapi_shopping", "settings": { "location": "Austin, Texas" } }
  ],
  "guardrails": {
    "read_only_financial_data": true,
    "max_tool_calls": 8,
    "require_confirmation_for_external_actions": true,
    "fact_check": "flag"
  },
  "status": "deployed",
  "version": 3,
  "created_at": "2026-10-24T20:05:00Z",
  "updated_at": "2026-10-24T20:12:00Z",
  "deployed_at": "2026-10-24T20:12:00Z"
}
```

### `POST /api/agents/{id}/chat`
Request:
```json
{ "message": "Find three ways I could reduce my spending.", "session_id": "session_demo_01", "demo_user_id": "demo_user_01" }
```
Response:
```json
{
  "run_id": "run_8f2c1a",
  "assistant_message": "Here are three potential savings...\n1. AirPods Pro 2: you paid $249.00 at Target; Amazon lists them at $189.99 (potential saving $59.01)...",
  "status": "completed",
  "usage": { "input_tokens": 4120, "output_tokens": 610 },
  "total_latency_ms": 6840,
  "steps": [
    { "runId": "run_8f2c1a", "agentId": "agent-smart-spend", "step": 1, "type": "llm", "toolName": null,
      "input": { "message_chars": 44, "tools_offered": 4 }, "output": { "function_calls": ["nessie_purchases"] },
      "ms": 1210, "tokens": 1350, "inputTokens": 1300, "outputTokens": 50, "success": true, "cached": null, "fixture": null, "error": null },
    { "runId": "run_8f2c1a", "agentId": "agent-smart-spend", "step": 2, "type": "tool", "toolName": "nessie_purchases",
      "input": {}, "output": { "summary": "11 purchases, total $607.51", "mode": "live" },
      "ms": 284, "tokens": null, "inputTokens": null, "outputTokens": null, "success": true, "cached": false, "fixture": false, "error": null },
    { "runId": "run_8f2c1a", "agentId": "agent-smart-spend", "step": 3, "type": "llm", "toolName": null,
      "input": {}, "output": { "function_calls": ["serpapi_shopping"] },
      "ms": 980, "tokens": 1500, "inputTokens": 1460, "outputTokens": 40, "success": true, "cached": null, "fixture": null, "error": null },
    { "runId": "run_8f2c1a", "agentId": "agent-smart-spend", "step": 4, "type": "tool", "toolName": "serpapi_shopping",
      "input": { "query": "AirPods Pro 2" }, "output": { "summary": "4 products, $189.99–$249.00", "mode": "cached" },
      "ms": 12, "tokens": null, "inputTokens": null, "outputTokens": null, "success": true, "cached": true, "fixture": false, "error": null },
    { "runId": "run_8f2c1a", "agentId": "agent-smart-spend", "step": 5, "type": "llm", "toolName": null,
      "input": {}, "output": { "final_answer_chars": 820 },
      "ms": 2950, "tokens": 1880, "inputTokens": 1360, "outputTokens": 520, "success": true, "cached": null, "fixture": null, "error": null },
    { "runId": "run_8f2c1a", "agentId": "agent-smart-spend", "step": 6, "type": "verify", "toolName": null,
      "input": { "mode": "flag" }, "output": { "claims": 6, "verified": 5, "unverified": ["$15.00"] },
      "ms": 3, "tokens": null, "inputTokens": null, "outputTokens": null, "success": true, "cached": null, "fixture": null, "error": null }
  ],
  "claims": [
    { "text": "$249.00", "context": "you paid $249.00 at Target", "verified": true, "source_step": 2, "source_tool": "nessie_purchases", "how": "exact" },
    { "text": "$189.99", "context": "Amazon lists them at $189.99", "verified": true, "source_step": 4, "source_tool": "serpapi_shopping", "how": "exact" },
    { "text": "$59.01", "context": "(potential saving $59.01)", "verified": true, "source_step": 2, "source_tool": "nessie_purchases", "how": "difference" },
    { "text": "$15.00", "context": "could save about $15.00 per month", "verified": false, "source_step": null, "source_tool": null, "how": null }
  ],
  "blocked": false,
  "data_modes": ["live", "cached"],
  "error": null
}
```

Step `input`/`output` are **safe summaries** for display — never API keys, auth headers or raw account numbers.
Tool step `output` always includes `summary` (one line) and `mode` (`live` | `cached` | `fixture`).
UI must label `fixture` data as "Demo data" and `cached` as "Cached".

### `GET /api/runs/{id}`
```json
{
  "id": "run_8f2c1a", "agent_id": "agent-smart-spend", "session_id": "session_demo_01", "status": "completed",
  "user_message": "Find three ways I could reduce my spending.",
  "assistant_message": "Here are three potential savings...",
  "started_at": "2026-10-24T20:15:01Z", "completed_at": "2026-10-24T20:15:08Z",
  "total_latency_ms": 6840, "input_tokens": 4120, "output_tokens": 610, "estimated_cost_usd": null,
  "claims_total": 6, "claims_verified": 5, "blocked": false, "error": null,
  "steps": [ "...same RunStep objects as above..." ]
}
```

### `GET /api/analytics/summary`
```json
{
  "total_runs": 42, "completed_runs": 40, "failed_runs": 2, "error_rate": 0.048,
  "avg_latency_ms": 5210.4, "input_tokens": 151200, "output_tokens": 20400, "estimated_cost_usd": null,
  "serpapi_calls": 31, "cache_hits": 57, "claims_total": 230, "claims_verified": 221,
  "runs_over_time": [ { "bucket": "2026-10-24T20:00:00Z", "runs": 12, "failed": 1 } ]
}
```

### `GET /api/analytics/tools`
```json
[
  { "tool_name": "serpapi_shopping", "calls": 40, "errors": 1, "avg_ms": 610.2, "cache_hits": 25, "fixture_calls": 0 },
  { "tool_name": "nessie_purchases", "calls": 38, "errors": 0, "avg_ms": 290.5, "cache_hits": 0, "fixture_calls": 0 }
]
```

---

## Environment variables (`.env.example`)

| Name | Used by | Notes |
|---|---|---|
| `GEMINI_API_KEY` | runtime | |
| `GEMINI_MODEL` | runtime | default model for new agents; verify ID is enabled for the key |
| `SERPAPI_KEY` | tools | missing → labeled fixtures |
| `SERPAPI_MOCK` | tools | `1` forces fixtures |
| `SERPAPI_CACHE_ONLY` | tools | `1` = never call SerpApi; serve cache only (demo backup) |
| `NESSIE_API_KEY` | tools | missing → labeled fixtures |
| `NESSIE_BASE_URL` | tools | default `http://api.nessieisreality.com` |
| `NESSIE_MOCK` | tools | `1` forces fixtures |
| `DATABASE_URL` | server | Tiger Data Postgres connection string |
