# syntax=docker/dockerfile:1.7

# Build stage: install locked runtime dependencies into a virtualenv with uv.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim@sha256:531f855bda2c73cd6ef67d56b733b357cea384185b3022bd09f05e002cd144ca AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# Runtime stage: slim Python, no build tools, non-root user.
FROM python:3.14-slim-bookworm@sha256:48b13b003dda20b16f9442b8475aa05fe21bf6579a8c881db92ffb4d8fd20f83
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
# The app runs from its own virtualenv, so the base image's pip (and the
# libraries it vendors) is removed to shrink the attack surface.
RUN python -m pip uninstall --yes --quiet pip \
    && rm -rf /usr/local/lib/python3.13/ensurepip \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
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
