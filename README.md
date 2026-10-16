# Banyan

Agents that grow their own tools, with humans as the gatekeepers. See PLAN.md.

## Setup
1. `cp .env.example .env` (Phase 0 needs no keys).
2. Backend: `cd backend && uv sync && uv run uvicorn app.main:app --reload` (port 8000).
3. Frontend: `cd frontend && pnpm install && pnpm dev` (port 3000).
4. Open http://localhost:3000 and click "Run fake run". Refresh to replay the run.

## Deploy (Vercel)
Two Vercel projects with Root Directory `backend` and `frontend`. Pushing to `main` deploys
both; to deploy without a push run `./deploy.sh` (or `./deploy.sh backend`) from the repo root.
Do not run `vercel` from inside `backend/` or `frontend/`: the Root Directory setting would
make it look for `backend/backend`.

See [ARCHITECTURE.md](ARCHITECTURE.md) for how the agents coordinate, where humans step in, and how the Toolsmith keeps new tools safe.
