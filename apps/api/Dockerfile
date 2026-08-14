FROM python:3.13 AS builder

RUN pip install --no-cache-dir uv==0.12.4

WORKDIR /builder

# Install backend dependencies from the locked uv dependency graph.
COPY pyproject.toml uv.lock README.md ./

ENV UV_PROJECT_ENVIRONMENT=/opt/venv

RUN uv sync --frozen --no-dev --no-install-project


# run stage
FROM python:3.13-slim

ARG PLATFORM_VERSION=development
ARG GIT_COMMIT=unknown
ARG GIT_TAG=
ARG BUILD_TIME=
ARG BUILD_DIRTY=false

LABEL org.opencontainers.image.title="Airalogy Platform API" \
      org.opencontainers.image.source="https://github.com/airalogy/platform" \
      org.opencontainers.image.version="$PLATFORM_VERSION" \
      org.opencontainers.image.revision="$GIT_COMMIT"

ENV PLATFORM_VERSION=$PLATFORM_VERSION \
    GIT_COMMIT=$GIT_COMMIT \
    GIT_TAG=$GIT_TAG \
    BUILD_TIME=$BUILD_TIME \
    BUILD_DIRTY=$BUILD_DIRTY

# retrieve packages from build stage
COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

# Add a non-root user and pre-create writable volume mount points. Docker copies
# these ownership bits into newly created named volumes.
RUN useradd -ms /bin/bash deploy && \
    install -d -o deploy -g deploy /home/deploy/app/log /home/deploy/app/protocols
USER deploy
WORKDIR /home/deploy/app

RUN mkdir -p log protocols

COPY --chown=deploy:deploy . .

RUN printf '{"version":"%s","tag":"%s","commit":"%s","build_time":"%s","dirty":%s}\n' \
    "$PLATFORM_VERSION" "$GIT_TAG" "$GIT_COMMIT" "$BUILD_TIME" "$BUILD_DIRTY" \
    > app/build-info.json
