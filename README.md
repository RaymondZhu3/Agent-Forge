# Agent Forge

Configure, deploy and monitor AI agents that use real tools — and verify every figure they state against live data.
HackTX 2026 · Tracks: NMC2, SerpApi, Capital One.

- Plan: [`docs/PLAN.md`](docs/PLAN.md)
- Contracts & example responses: [`docs/API.md`](docs/API.md)
- Shared types: [`server/schemas.py`](server/schemas.py), [`web/src/types.ts`](web/src/types.ts)

## Structure & ownership

| Folder | Owner |
|---|---|
| `/tools`, `/server/runtime` | Person 1 — tools, Gemini runtime, fact-check |
| `/server` (except `runtime`), `/server/tests` | Person 2 — API, DB, analytics, deploy |
| `/web` | Person 3 — frontend |

Contracts are frozen; change them only with team agreement.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in keys; missing SerpApi/Nessie keys fall back to labeled demo fixtures
```

Run commands are added by each owner as their part lands.

## Working rules

- `main` always runs. Small commits; `git pull --rebase` before every push.
- Never commit `.env` or API keys.
- Stuck > 30 min → pair up, simplify, or cut.
