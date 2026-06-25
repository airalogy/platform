FROM python:3.13 AS builder

RUN pip install --no-cache-dir uv

WORKDIR /builder

# Install backend dependencies from the locked uv dependency graph.
COPY pyproject.toml uv.lock README.md ./

ENV UV_PROJECT_ENVIRONMENT=/opt/venv

RUN uv sync --frozen --no-dev --no-install-project


# run stage
FROM python:3.13-slim

# retrieve packages from build stage
COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

# add a no-root user
RUN useradd -ms /bin/bash deploy
USER deploy
WORKDIR /home/deploy/app

COPY --chown=deploy:deploy . .
