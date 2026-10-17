from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import (routes_approvals, routes_auth, routes_debug, routes_goals, routes_runs, routes_sessions,
                  routes_tools, routes_voice)
from .config import settings
from .db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Banyan", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    # Vercel preview/production frontends (no credentials/cookies are used).
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(routes_debug.router)
app.include_router(routes_runs.router)
app.include_router(routes_goals.router)
app.include_router(routes_approvals.router)
app.include_router(routes_tools.router)
app.include_router(routes_sessions.router)
app.include_router(routes_voice.router)
app.include_router(routes_auth.router)


@app.get("/health")
@app.get("/api/health")
def health() -> dict:
    return {"ok": True}
