# app/streamlit/Dockerfile. Build context is the repository root (see docker-compose.yml):
#   docker build -f app/streamlit/Dockerfile .
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# curl for the healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Dependencies first (cached layer). The workspace lock needs EVERY member's pyproject.toml,
# but only this app's dependency tree is installed (`--package`).
COPY pyproject.toml uv.lock README.md ./
COPY app/streamlit/pyproject.toml ./app/streamlit/pyproject.toml
COPY app/dash/pyproject.toml ./app/dash/pyproject.toml
RUN uv sync --frozen --no-dev --package shopping-list-streamlit --no-install-workspace

# Shared backend, templates and this app only
COPY src/ ./src/
COPY docs/ ./docs/
COPY app/streamlit/ ./app/streamlit/
RUN uv sync --frozen --no-dev --package shopping-list-streamlit

WORKDIR /app/app/streamlit
EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# `--no-sync`: the venv was synced at build time.
CMD ["uv", "run", "--no-sync", "streamlit", "run", "main.py", "--server.port=8501", "--server.address=0.0.0.0"]
