from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import (routes_approvals, routes_auth, routes_debug, routes_goals, routes_runs, routes_sessions,
                  routes_tools, routes_voice)
from .config import settings
from .db import init_db


async def _ticker() -> None:
    import asyncio
    import logging

    from . import watchers

    while True:
        try:
            await watchers.tick(None)
        except Exception:  # a bad tick must not stop the loop
            logging.exception("watcher tick failed")
        await asyncio.sleep(max(5, settings.watch_interval_sec))


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    init_db()
    task = asyncio.create_task(_ticker()) if settings.background_ticker else None
    yield
    if task:
        task.cancel()


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


# Single-container deploys (root Dockerfile): the UI is a static export served from here, so
# UI and API share one origin. Mounted last, so every API route above takes precedence.
if settings.static_dir:
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="ui")
