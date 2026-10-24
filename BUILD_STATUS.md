# Build status — Person 2 (server)

## Works
- FastAPI app `server/main.py`; every endpoint in docs/API.md incl. `/api/templates`; 400/404/409 errors as `{detail}`
- Models + idempotent schema (`server/db.py`, `python -m server.db`): agents, runs, run_steps, tool_cache (JSONB on Postgres)
- `DbHooks` + DB tool cache (expiry respected), registered at startup (`server/hooks.py`)
- Analytics from stored rows only (`server/analytics.py`); cost stays null unless `PRICE_*` env set
- Startup seeding of `agent-smart-spend` / `agent-news-monitor` (deployed)
- `server/seed_nessie.py` (needs NESSIE_API_KEY)
- Deploy notes: `server/DEPLOY.md`

## Tests
`pytest server/tests` — 6 passed (SQLite, fake LLM, fixture tools): create → deploy → chat → run saved → analytics counts.

## Not verified yet
- Against real Tiger Data Postgres (code uses SQLAlchemy + psycopg3, tested on SQLite only)
- Real Gemini chat via Smart Spend (needs GEMINI_API_KEY)
- `seed_nessie.py` against the live Nessie API
- Vultr deployment

## Blockers
- None in code; need DATABASE_URL, GEMINI_API_KEY, NESSIE_API_KEY in the environment.
