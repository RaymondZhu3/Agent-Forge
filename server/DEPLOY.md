# Deploy the API to Vultr

Prereqs on the VM: Python 3.11+, git. Open the chosen port in the firewall (`ufw allow 8000`).

```bash
git clone <repo> && cd Agent-Forge
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # fill in, never commit
python -m server.db     # optional: idempotent schema setup (the app also does this at startup)
```

**Start command** (from the repo root):

```bash
uvicorn server.main:app --host 0.0.0.0 --port 8000
```

For a service that survives logout, use systemd with that `ExecStart`, `WorkingDirectory` = repo root and `EnvironmentFile` = `.env`.

## Environment variables (server)

| Name | Notes |
|---|---|
| `DATABASE_URL` | Tiger Data Postgres string (`postgresql://...?sslmode=require`). Unset = local SQLite file (dev only) |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | model |
| `SERPAPI_KEY`, `SERPAPI_MOCK`, `SERPAPI_CACHE_ONLY` | search |
| `NESSIE_API_KEY`, `NESSIE_BASE_URL`, `NESSIE_MOCK` | banking |
| `CORS_ORIGINS` | comma list, default the Vite dev server (`http://localhost:5173`). Add the deployed web origin |
| `CORS_ORIGIN_REGEX` | optional, e.g. `https://.*\.example\.com` |
| `DEMO_CUSTOMER_ID` | optional; used when seeding Smart Spend on an empty DB |
| `PRICE_INPUT_PER_MTOK`, `PRICE_OUTPUT_PER_MTOK` | USD per 1M tokens. Both unset = cost stays `null` |

## Verify

```bash
curl http://<vultr-ip>:8000/api/health        # {"ok":true,"db":true,...}
curl -X POST http://<vultr-ip>:8000/api/agents/agent-smart-spend/chat \
  -H 'content-type: application/json' -d '{"message":"Find three ways I could reduce my spending."}'
```

`/api/health` returns `ok:false, db:false` if the database is unreachable.

## Seed Nessie (once, needs NESSIE_API_KEY)

```bash
python -m server.seed_nessie    # prints customer_id and stores it in Smart Spend's Nessie tool settings
```
