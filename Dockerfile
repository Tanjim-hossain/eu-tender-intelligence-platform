# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim-bookworm AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils \
    && rm -rf /var/lib/apt/lists/*
RUN groupadd --gid 10001 tendergraph && useradd --uid 10001 --gid 10001 --create-home tendergraph
WORKDIR /app
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv
COPY --from=builder /app/.venv /app/.venv
# Model downloads occur at runtime, never while building or checking the image.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/home/tendergraph/.cache/huggingface \
    UV_CACHE_DIR=/home/tendergraph/.cache/uv \
    RAG_PROVIDER=evidence
RUN mkdir -p /app/data/refresh /app/data/documents /home/tendergraph/.cache/huggingface \
    && chown -R tendergraph:tendergraph /app/data /home/tendergraph/.cache
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=15s --start-period=180s --retries=3 \
    CMD uv run --no-project --python /app/.venv/bin/python --no-sync python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=12)" || exit 1
CMD ["/app/.venv/bin/uvicorn", "tendergraph.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers"]
