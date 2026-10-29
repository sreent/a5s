# a5s: one image that runs as the gateway, the scheduler or a worker.
# The same image is what Azure, Google Cloud and AWS run.

FROM ghcr.io/astral-sh/uv:0.11.32 AS uv

FROM python:3.13-slim AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
# Behind a TLS-inspecting proxy, pass its CA as the build secret `ca`.
RUN --mount=type=cache,target=/root/.cache/uv --mount=type=secret,id=ca,required=false \
    if [ -f /run/secrets/ca ]; then export SSL_CERT_FILE=/run/secrets/ca; fi; \
    uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv --mount=type=secret,id=ca,required=false \
    if [ -f /run/secrets/ca ]; then export SSL_CERT_FILE=/run/secrets/ca; fi; \
    uv sync --locked --no-dev --no-editable

FROM python:3.13-slim
RUN useradd --create-home --uid 10001 a5s
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY agents ./agents
COPY config ./config
COPY scenarios/sample ./scenarios/sample
ENV PATH=/app/.venv/bin:$PATH A5S_ROOT=/app PYTHONUNBUFFERED=1
USER a5s
ENTRYPOINT ["a5s"]
