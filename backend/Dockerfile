FROM python:3.11.9-slim-bookworm

ARG SOURCE_REVISION=unknown
LABEL org.opencontainers.image.revision=$SOURCE_REVISION

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /uvx /bin/
COPY backend/pyproject.toml backend/uv.lock ./
ARG INSTALL_RERANKER=false
ARG RERANKER_EXTRA=reranker
RUN if [ "$INSTALL_RERANKER" = "true" ]; then \
      uv sync --frozen --no-dev --no-install-project --extra "$RERANKER_EXTRA"; \
    else uv sync --frozen --no-dev --no-install-project; fi

COPY backend/app ./app
COPY backend/scripts ./scripts
COPY data /data
RUN if [ "$INSTALL_RERANKER" = "true" ]; then uv sync --frozen --no-dev --extra "$RERANKER_EXTRA"; \
    else uv sync --frozen --no-dev; fi

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log", "--no-proxy-headers"]
