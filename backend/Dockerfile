# Banyan API (FastAPI). Build from this folder:  docker build -t banyan-backend backend
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /usr/local/bin/uv

WORKDIR /app
# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY index.py ./

# Non-root; /app/data holds the SQLite file when no DATABASE_URL is given.
RUN useradd --create-home banyan && mkdir -p /app/data && chown -R banyan /app
USER banyan

# A long-running server: no 300s serverless limit, and watchers are woken in-process.
ENV DATABASE_URL=sqlite:////app/data/banyan.db \
    BACKGROUND_TICKER=true \
    RUN_TIME_BUDGET_SEC=1200 \
    PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health')"
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
