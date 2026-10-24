# Build status — Person 2 (server)

_Last verified: Sat Oct 24, 2026._

## Works (verified live)
- FastAPI app `server/main.py`: every endpoint in docs/API.md incl. `/api/templates`; errors as `{detail}` (400/404/409)
- Postgres on Tiger Data: schema auto-created (`python -m server.db`), runs + steps + analytics read back through the API
- `DbHooks` + DB tool cache (expiry respected); startup seeding of `agent-smart-spend` / `agent-news-monitor`
- Real Smart Spend chat: Gemini + live Nessie + live SerpApi, 9 steps, fact-check 18/18 verified, ~35 s
- Real News Monitor chat: live SerpApi news, 4 steps, ~8 s
- Deployed on Vultr: `http://144.202.28.129:8000` (systemd service `agentforge`, auto-restarts and starts on boot). `/api/health` -> ok/db true
- Analytics computed from stored rows only; cost is `null` unless `PRICE_INPUT_PER_MTOK`/`PRICE_OUTPUT_PER_MTOK` are set

## Tests
`pytest server tools` — 24 passed (SQLite, fake LLM, fixture tools): create -> deploy -> chat -> run saved -> analytics counts.

## Gotchas
- **Nessie host is `https://api.nessieisreal.com`** (no "ity", HTTPS only). `.env.example`, `docs/API.md`, `tools/nessie.py` still default to the wrong `http://api.nessieisreality.com` (not my files — Person 1 to fix).
- **Gemini model:** `gemini-2.5-flash` is blocked for new keys; `gemini-3.8-flash` takes ~70 s per call. Use `GEMINI_MODEL=gemini-3.5-flash`.
- Nessie sandbox appears to store purchase amounts as whole dollars (total $607.00 vs fixture $607.51). Fact-check still passes because it compares against tool output.
- Possible verifier tolerance issue: an answer said Uber Eats "$96" while the fixture items sum to $97.35 (Person 1).
- API is plain HTTP; an HTTPS-served frontend may be blocked by the browser. Add the web origin to `CORS_ORIGINS` on the server.

## Deploy / update
First deploy: `server/deploy_vultr.sh`, details in `server/DEPLOY.md`. Update: `cd /opt/agent-forge && git pull && systemctl restart agentforge`.
Delete the Vultr instance when the event is over (billing).

## Blockers
None. To do before the demo: delete leftover test runs (`live_check`, `live_news`, `vultr_check`), warm the SerpApi cache by rehearsing the demo prompts.
