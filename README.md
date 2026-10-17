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

## Deploy (Docker, anywhere)
```bash
cp .env.example .env        # fill in GEMINI_API_KEY, SERPAPI_API_KEY, VAULT_KEY, ...
docker compose up --build   # UI :3000, API :8000
```
- No `DATABASE_URL` → SQLite on the `banyan-data` volume; set a Supabase URL to share data with Vercel.
- On a real server set `BACKEND_URL` and `FRONTEND_ORIGIN` to the public addresses, then rebuild
  (the UI bakes the API address in at build time). For Google sign-in, add
  `<BACKEND_URL>/api/auth/google/callback` as a redirect URI in Google Cloud.
- Differences from Vercel: no 300 s request limit, and the API wakes watchers itself every
  `WATCH_INTERVAL_SEC`, so alerts (and ntfy pushes) arrive within seconds with every tab closed.
- Images can also be deployed separately (Railway, Render, Fly, a VPS): `backend/Dockerfile`
  and `frontend/Dockerfile` (pass `--build-arg NEXT_PUBLIC_API_URL=...`).

See [ARCHITECTURE.md](ARCHITECTURE.md) for how the agents coordinate, where humans step in, and how the Toolsmith keeps new tools safe.
