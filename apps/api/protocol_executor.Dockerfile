FROM m.daocloud.io/docker.io/library/python:3.13.5-slim AS builder

WORKDIR /builder

# build: docker build -t airalogy-protocol-executor:latest -f protocol_executor.Dockerfile .
COPY protocol_requirements.txt ./

# set pip source
RUN pip install -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple pip -U && \
    pip config set global.index-url https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple

# Install requirements
RUN pip install --no-cache-dir -r protocol_requirements.txt


# run stage
FROM m.daocloud.io/docker.io/library/python:3.13.5-slim

ARG PLATFORM_VERSION=development
ARG GIT_COMMIT=unknown
ARG GIT_TAG=
ARG BUILD_TIME=
ARG BUILD_DIRTY=false

LABEL org.opencontainers.image.title="Airalogy Platform Protocol Executor" \
      org.opencontainers.image.source="https://github.com/airalogy/platform" \
      org.opencontainers.image.version="$PLATFORM_VERSION" \
      org.opencontainers.image.revision="$GIT_COMMIT"

ENV PLATFORM_VERSION=$PLATFORM_VERSION \
    GIT_COMMIT=$GIT_COMMIT \
    GIT_TAG=$GIT_TAG \
    BUILD_TIME=$BUILD_TIME \
    BUILD_DIRTY=$BUILD_DIRTY

# retrieve packages from build stage
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages

# add a no-root user
RUN useradd -ms /bin/bash deploy
USER deploy
WORKDIR /home/deploy/app
