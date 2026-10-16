# Banyan

Agents that grow their own tools, with humans as the gatekeepers. See PLAN.md.

## Setup
1. `cp .env.example .env` (Phase 0 needs no keys).
2. Backend: `cd backend && uv sync && uv run uvicorn app.main:app --reload` (port 8000).
3. Frontend: `cd frontend && pnpm install && pnpm dev` (port 3000).
4. Open http://localhost:3000 and click "Run fake run". Refresh to replay the run.
