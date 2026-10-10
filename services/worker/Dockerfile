# syntax=docker/dockerfile:1.7

# Build stage: install locked runtime dependencies into a virtualenv with uv.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# Runtime stage: slim Python, no build tools, non-root user.
FROM python:3.13-slim-bookworm
ARG VERSION=dev
ARG GIT_SHA=unknown
ARG BUILD_TIME=unknown
LABEL org.opencontainers.image.title="shipyard-worker" \
      org.opencontainers.image.description="Shipyard worker service" \
      org.opencontainers.image.source="https://github.com/devwithvino/cicd_demo" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_TIME}"
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
COPY --from=build --chown=app:app /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    APP_VERSION=${VERSION} \
    GIT_SHA=${GIT_SHA} \
    BUILD_TIME=${BUILD_TIME} \
    PORT=8081
EXPOSE 8081
USER 10001
CMD ["python", "-m", "shipyard_worker.main"]
