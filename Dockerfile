# TEPHRA on Cloud Run: one request-driven service; Cloud Scheduler calls POST /tasks/tick.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /usr/local/bin/uv

WORKDIR /app

# Dependencies first so code edits do not invalidate the layer. Build with
# --build-arg SCIENCE=1 to include satpy for the raw-Himawari split-window layer.
ARG SCIENCE=0
COPY pyproject.toml uv.lock* README.md LICENSE ./
RUN extras="--extra gcp"; \
    if [ "$SCIENCE" = "1" ]; then extras="$extras --extra science"; fi; \
    if [ -f uv.lock ]; then uv sync --frozen --no-dev --no-install-project $extras; \
    else uv sync --no-dev --no-install-project $extras; fi

COPY tephra ./tephra
COPY data ./data
RUN extras="--extra gcp"; \
    if [ "$SCIENCE" = "1" ]; then extras="$extras --extra science"; fi; \
    if [ -f uv.lock ]; then uv sync --frozen --no-dev $extras; else uv sync --no-dev $extras; fi

RUN useradd --create-home --uid 10001 tephra && mkdir -p /tmp/tephra-cache && chown tephra /tmp/tephra-cache
USER tephra

ENV PATH="/app/.venv/bin:$PATH" \
    TEPHRA_DATA_DIR=/app/data \
    TEPHRA_CACHE_DIR=/tmp/tephra-cache \
    TEPHRA_SQLITE_PATH=/tmp/tephra-cache/tephra.sqlite3 \
    PORT=8080

EXPOSE 8080
CMD ["tephra"]
