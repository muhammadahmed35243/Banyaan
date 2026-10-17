# Banyan in ONE container: the API (FastAPI) also serves the UI (a static Next.js export),
# so there is one URL and no CORS. Built from the repo root:  docker build -t banyan .
# (backend/Dockerfile + frontend/Dockerfile + docker-compose.yml are the two-service option.)

# ---- 1. UI: static export; API calls are relative (same origin) ----
FROM node:22-alpine AS ui
RUN corepack enable
WORKDIR /ui
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
ENV NEXT_OUTPUT=export NEXT_PUBLIC_API_URL="" NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

# ---- 2. API + UI ----
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /usr/local/bin/uv
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/app ./app
COPY --from=ui /ui/out ./static

RUN useradd --create-home banyan && mkdir -p /app/data && chown -R banyan /app
USER banyan

# Long-running server: watchers are woken in-process (alerts with every tab closed) and goals
# get 20 minutes. Without DATABASE_URL, data lives in SQLite under /app/data (mount a volume).
ENV STATIC_DIR=/app/static \
    DATABASE_URL=sqlite:////app/data/banyan.db \
    BACKGROUND_TICKER=true \
    RUN_TIME_BUDGET_SEC=1200 \
    PORT=3000
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health')"
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
