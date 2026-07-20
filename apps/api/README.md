# Airalogy Platform Backend

FastAPI backend for Airalogy Platform Community Edition.

## Requirements

- Python 3.13
- uv
- Docker Compose for local PostgreSQL, Redis, and MinIO

## Local Stack

```bash
cp .env.example .env
docker compose --env-file .env up --build
```

After the first build completes, normal starts do not need `--build`:

```bash
docker compose --env-file .env up
```

To run the stack in the background:

```bash
docker compose --env-file .env up -d
```

Run `docker compose --env-file .env up --build` again only when Dockerfiles, dependency lock files, or Compose build settings change.

The default Docker mode does not automatically restart the API after backend code changes. For Docker-based backend development, use the reload override:

```bash
docker compose --env-file .env -f docker-compose.yml -f docker-compose.dev.yml up
```

Without the reload override, restart the API container after backend code changes:

```bash
docker compose --env-file .env restart api-server
```

Use the appropriate refresh action for each type of backend change:

| Change | How to apply it |
| --- | --- |
| `app/**/*.py` | The reload override reloads automatically; in the default Docker mode, run `docker compose --env-file .env restart api-server` |
| `migrations/` | Reload does not apply database migrations; run `docker compose --env-file .env exec api-server alembic upgrade head`, or restart `api-server` |
| `pyproject.toml` or `uv.lock` | Dependencies are built into the image; run `docker compose --env-file .env up -d --build api-server` |
| `.env` | Environment variables are read when the container is created; run `docker compose --env-file .env up -d --force-recreate api-server` |
| Dockerfile or Compose build settings | Run `docker compose --env-file .env up -d --build` |

Compose bind-mounts this directory into the API container, so source changes are immediately visible inside the container. Whether the Python process restarts automatically depends on whether the reload override is enabled.

If Debian or PostgreSQL apt sources are unstable while building the PostgreSQL extension image, set these optional build mirrors in `.env`:

```env
APT_DEBIAN_MIRROR=http://deb.debian.org/debian
APT_DEBIAN_SECURITY_MIRROR=http://deb.debian.org/debian-security
APT_POSTGRES_MIRROR=http://apt.postgresql.org/pub/repos/apt
```

For example, users in mainland China can switch the Debian mirrors to Aliyun. Use `http://` here because this build step runs before `ca-certificates` is installed:

```env
APT_DEBIAN_MIRROR=http://mirrors.aliyun.com/debian
APT_DEBIAN_SECURITY_MIRROR=http://mirrors.aliyun.com/debian-security
```

`APT_POSTGRES_MIRROR` must point to a PostgreSQL PGDG apt repository mirror.

This starts:

- API: `http://127.0.0.1:4000`
- PostgreSQL: `127.0.0.1:54322`
- Redis: `127.0.0.1:6379`
- MinIO API: `http://127.0.0.1:9200` by default (`MINIO_API_PORT`)
- MinIO console: `http://127.0.0.1:9202` by default (`MINIO_CONSOLE_PORT`)

The Compose stack creates the default MinIO bucket from `MINIO_BUCKET`.

Development quick-start fixtures use protocol examples packaged in the published `airalogy` Python package by default. To test local protocol examples before they are packaged in Airalogy, set `AIRALOGY_PROTOCOL_EXAMPLES_DIR` in `.env` to an API-visible local `examples/protocols` directory with an `index.json`; when set, the fixture loads that local directory instead of the packaged examples.

## Manual Development

If you run dependencies through Docker but the API directly on the host, adjust `.env` hostnames from Docker service names to localhost:

```env
DATABASE_URL=postgresql+asyncpg://airalogy:airalogy@127.0.0.1:54322/airalogy
REDIS_URL=redis://127.0.0.1:6379/0
MINIO_ENDPOINT=127.0.0.1:9200
```

Then run:

```bash
uv sync --locked --dev
uv run alembic upgrade head
uv run fastapi dev app --host 0.0.0.0 --port 4000 --reload
```

## Masterbrain

The recommended path is to use the published `masterbrain` Python package in-process. Keep `MASTERBRAIN_CALL_MODE` unset or set to `package`.

The old separately deployed Masterbrain API path is retained only as a compatibility escape hatch. Set `MASTERBRAIN_CALL_MODE=external` and `CHAT_API_ENDPOINT` only when intentionally routing AI requests to a legacy external service.

The GPT chat option is disabled by default. Configure `OPENAI_API_KEY` and set `ENABLE_GPT_MODEL=true` to expose it in the Web model selector and allow GPT requests. When using an external Masterbrain endpoint, the endpoint configuration can satisfy the provider requirement instead of a local OpenAI key.

## Safety

Do not commit real `.env` files, provider API keys, deployment-specific endpoints, TLS private keys, or production object-storage credentials.
