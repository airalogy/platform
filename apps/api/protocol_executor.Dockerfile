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

# retrieve packages from build stage
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages

# add a no-root user
RUN useradd -ms /bin/bash deploy
USER deploy
WORKDIR /home/deploy/app
