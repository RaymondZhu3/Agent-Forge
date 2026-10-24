# Tools + runtime (Person 1)

`/tools` — shared tool registry, SerpApi + Nessie tools, cache hooks, labeled fixtures.
`/server/runtime` — Gemini function-calling loop, fact-check (`verify`), templates, CLI.

## Try it

```bash
pip install -r requirements.txt
cp .env.example .env          # GEMINI_API_KEY required; SerpApi/Nessie keys optional (fixtures otherwise)
python -m server.runtime.cli --tools
python -m server.runtime.cli smart_spend "Find three ways I could reduce my spending."
python -m server.runtime.cli news_monitor "Brief me on NVIDIA and semiconductor supply chains."
python -m server.runtime.cli smart_spend "What will AirPods cost on Black Friday?" --fact-check block
pytest tools/tests server/runtime/tests
```

## For Person 2 (server)

```python
from server.runtime import run_agent, RunHooks, TEMPLATES
from tools.registry import registry
from tools.cache import set_cache_backend

# GET /api/tools      -> registry.list_metadata()
# GET /api/templates  -> [t.model_dump() for t in TEMPLATES]
# POST /api/agents/{id}/chat:
response = run_agent(agent_config, body.message, body.session_id, hooks=DbHooks(db))
# at startup:
set_cache_backend(get=db_cache_get, set=db_cache_set)
```

`DbHooks` implements `on_run_start(run_id, agent_id, session_id, user_message)`, `on_step(step: RunStep)`,
`on_run_finish(response: ChatResponse)`. See `docs/API.md`.

Validate configured tools with `registry.get(name)` (None = unknown tool → 400) and tool settings with
`tools.base.validate(settings, tool.settings_schema)` when an agent is created/updated.

## Tools

| Tool | Source | Notes |
|---|---|---|
| `serpapi_shopping` | Google Shopping | products with price, merchant, URL; lowest/highest price |
| `serpapi_news` | Google News | stories with source, date if known, URL |
| `serpapi_web_search` | Google Search | organic results + answer box |
| `serpapi_local_places` | Google Local | places with address, rating, hours |
| `nessie_accounts` | Nessie | account type + balance (no account ids) |
| `nessie_purchases` | Nessie | purchases + deterministic totals per merchant |
| `nessie_bills` | Nessie | bills + recurring monthly total |

Every result is labeled `live`, `cached` or `fixture`. SerpApi responses are cached per tool + normalized query
(TTL: shopping 6h, news 30m, search/local 24h). `SERPAPI_CACHE_ONLY=1` replays cached searches only (demo backup).

## Fact-check

After the final answer, `verify` checks every `$` amount and `%` against money fields the tools returned in that
run: exact match, a difference/sum of two figures (e.g. savings), or a monthly figure ×12. Guardrail
`fact_check`: `flag` marks unverified figures, `block` redacts them, `off` skips. Logged as a `verify` run step.

## API limits (free tiers, checked Oct 24 2026)

| API | Limit | Notes |
|---|---|---|
| SerpApi | 250 searches/month, 50/hour per key | Only successful, non-cached searches count. `/account.json` is free: `python -m tools.check_keys`. Use `SERPAPI_CACHE_ONLY=1` for repeat debugging; the CLI caches to `tools/.cache/`. Keep one key just for the deployed demo. |
| Gemini | Free tier, per project and per model; daily quota resets at midnight Pacific | `gemini-2.5-flash` is 404 for new keys. `gemini-3.8-flash` gave 503 "high demand" and 30-60 s per step on Oct 24. Runtime retries 503/429 once, then falls back (`GEMINI_FALLBACK_MODELS`, default `gemini-3.8-flash,gemini-3.7-flash,gemini-3.5-flash`), then one more round after 4 s; 429s name the quota (per-day skips the model, per-minute waits ≤35 s); 30 s timeout (`GEMINI_TIMEOUT_S`), and a 504/timeout moves to the next model. Pick the fastest: `python -m tools.check_keys --latency --write`. One key per teammate = separate quotas. |
| Nessie | No published limits | Data is per API key: seed and run with the same key. Unreachable from the HackTX network on Oct 24; tools then use labeled fixtures for 60 s (`NESSIE_FALLBACK=0` to fail instead). |
