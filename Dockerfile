# a5s: one image that runs as the gateway, the scheduler or a worker.
# The same image is what Azure, Google Cloud and AWS run, and what runs on premises.
# Its base images are pinned by digest, its Python packages by uv.lock, and the studio's
# by studio/package-lock.json.

FROM ghcr.io/astral-sh/uv:0.11.32@sha256:df4cae8f3a96d175e2e5f992e597550000edbe78fdc2594d5cd8de1a217f504c AS uv

# The studio's pages, built from studio/ into the package's webchat/studio. Nothing its
# packages install runs a script of theirs (studio/.npmrc).
FROM node:24-alpine@sha256:116b800c3754b440ee0aa3ed2f20f5bf3d99a554bfd9adeea09ea8017f6e85f5 AS studio
WORKDIR /build/studio
COPY studio/package.json studio/package-lock.json studio/.npmrc ./
RUN --mount=type=cache,target=/root/.npm --mount=type=secret,id=ca,required=false \
    if [ -f /run/secrets/ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/ca; fi; \
    npm ci
COPY studio ./
COPY src/a5s/core/webchat/app.css /build/src/a5s/core/webchat/app.css
RUN npm run build

# The built studio alone, which the tests take without Node:
# docker build --target studio-built --output src/a5s/core/webchat/studio .
FROM scratch AS studio-built
COPY --from=studio /build/src/a5s/core/webchat/studio /

FROM python:3.13-slim@sha256:2d44738ebf4ce5f63b9d9ea871e9c7cfdc0426f7b0c97cac915fd88ded1d86bb AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
# Behind a TLS-inspecting proxy, pass its CA as the build secret `ca`.
RUN --mount=type=cache,target=/root/.cache/uv --mount=type=secret,id=ca,required=false \
    if [ -f /run/secrets/ca ]; then export SSL_CERT_FILE=/run/secrets/ca; fi; \
    uv sync --locked --no-dev --no-install-project
COPY src ./src
COPY --from=studio /build/src/a5s/core/webchat/studio ./src/a5s/core/webchat/studio
RUN --mount=type=cache,target=/root/.cache/uv --mount=type=secret,id=ca,required=false \
    if [ -f /run/secrets/ca ]; then export SSL_CERT_FILE=/run/secrets/ca; fi; \
    uv sync --locked --no-dev --no-editable
# The release's manifest: every file the image runs, the studio's pages as it built them
# among them, and what it was built from. The core checks its code against it, and each
# organisation approves it by signing it.
COPY . /context
COPY --from=studio /build/src/a5s/core/webchat/studio /context/src/a5s/core/webchat/studio
RUN /app/.venv/bin/a5s release manifest --root /context > /app/release.yaml

FROM python:3.13-slim@sha256:2d44738ebf4ce5f63b9d9ea871e9c7cfdc0426f7b0c97cac915fd88ded1d86bb
RUN useradd --create-home --uid 10001 a5s
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/release.yaml ./release.yaml
COPY agents ./agents
COPY config ./config
# Every scenario a5s ships, for A5S_SCENARIO to choose; .dockerignore leaves out their keys
COPY scenarios ./scenarios
ENV PATH=/app/.venv/bin:$PATH A5S_ROOT=/app PYTHONUNBUFFERED=1
USER a5s
ENTRYPOINT ["a5s"]
