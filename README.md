# Airalogy Platform

[中文版](README.zh-CN.md)

Airalogy Platform is the self-hosted Community Edition of the Airalogy research data and intelligence platform. It provides the web application, backend API, local object storage integration, Protocol and Record workflows, and AI-assisted scientific collaboration surfaces.

This repository is intended to be the public, self-hosted platform layer. The core Airalogy standards, schemas, and SDK packages live in `airalogy/airalogy`; Masterbrain AI services live in `airalogy/masterbrain`.

## Edition Boundary

Community Edition includes:

- Web UI for labs, projects, protocols, records, chat, and protocol editing.
- Backend API based on FastAPI, PostgreSQL, Redis, and S3-compatible object storage.
- Local-first self-hosting defaults with MinIO.
- Published `airalogy`, `masterbrain`, and `@airalogy/aimd-*` package integrations.
- Basic project and lab permissions.

Enterprise extensions should stay outside this repository unless they are generally useful to the open-source edition. Typical Enterprise-only areas include advanced RBAC/ABAC, SSO/LDAP/AD/SAML, compliance audit logs, air-gapped installers, cluster operations, and enterprise support tooling.

For a user-facing capability overview, see [Community Edition Overview](docs/en/community-edition.md).

## Repository Layout

```txt
platform/
├── apps/
│   ├── api/    # FastAPI backend, migrations, Docker Compose stack
│   ├── web/    # Vue 3 web application
│   └── admin/  # Reserved workspace slot for future admin surfaces
├── packages/
│   ├── components/
│   ├── composables/
│   └── shared/
├── docs/
└── VERSION
```

## Quick Start

Prerequisites:

- Python 3.13
- uv
- Node.js 20+
- Corepack-managed pnpm 10.15+
- Docker or another local PostgreSQL / Redis / S3-compatible stack

Enable the pinned package manager before running frontend commands:

```bash
corepack enable
```

Start the backend dependencies and API:

```bash
cd apps/api
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

The default Docker mode does not automatically restart the API after backend code changes. For backend development, use the reload override:

```bash
docker compose --env-file .env -f docker-compose.yml -f docker-compose.dev.yml up
```

Without the reload override, restart the API container after backend code changes:

```bash
docker compose --env-file .env restart api-server
```

The API listens on `http://127.0.0.1:4000`.

Development quick-start fixtures use protocol examples packaged in the published `airalogy` Python package by default. To test local protocol examples before they are packaged in Airalogy, set `AIRALOGY_PROTOCOL_EXAMPLES_DIR` in `apps/api/.env` to an API-visible local `examples/protocols` directory with an `index.json`; when set, the fixture loads that local directory instead of the packaged examples.

If Debian or PostgreSQL apt sources are unstable while building the PostgreSQL extension image, update these variables in `apps/api/.env` to point to reachable mirrors or internal package sources:

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

In another terminal, return to the repository root and start the frontend:

```bash
cd /path/to/platform
pnpm install
pnpm dev
```

The web app listens on `http://localhost:3000` and proxies `/api` to the local backend.

## Data Persistence And Storage Safety

The default Compose stack persists core data under `apps/api/.data`:

- PostgreSQL records: `apps/api/.data/postgres`
- MinIO object files: `apps/api/.data/minio`

Stopping or rebuilding containers does not remove these files. Data is lost only if the `.data` directory or the configured storage paths are deleted.

For shared or production deployments, replace the example secrets in `.env`, use stable absolute paths or managed volumes, restrict access to PostgreSQL, Redis, and MinIO, enable TLS at the reverse proxy or storage layer, and set up regular backups for both PostgreSQL and object storage. Redis is treated as cache/queue infrastructure by default and is not the primary system of record.

Community Edition currently provides two managed object-storage backends: local/self-hosted `minio` and Aliyun `oss`. For Aliyun OSS deployments, set `STORAGE_BACKEND=oss` and configure `OSS_REGION`, `OSS_ENDPOINT`, `OSS_BUCKET`, and OSS credentials in `apps/api/.env`.

## Development

Backend checks:

```bash
pnpm api:check
```

Frontend checks:

```bash
pnpm lint
pnpm --filter @airalogy/web type-check
```

## Public Snapshot Notes

This Community Edition source tree intentionally excludes:

- Runtime `.env` files and local-only secrets.
- Local TLS certificates and private keys.
- Deployment-specific scripts and release workflows.
- Local caches, virtual environments, logs, and generated build artifacts.
- Vendored development checkouts; the backend uses the published `masterbrain` package instead.

Run the public-safety scan before publishing:

```bash
rg -n "PRIVATE KEY|your-private-domain.example" .
find . -name ".env" -o -name "*.pem" -o -name "*.key"
```

Review any findings before pushing to a public repository.

## Community

- Contributions: [CONTRIBUTING.md](CONTRIBUTING.md) / [中文](CONTRIBUTING.zh-CN.md)
- Security policy: [SECURITY.md](SECURITY.md) / [中文](SECURITY.zh-CN.md)

## License

Apache License 2.0. See [LICENSE](LICENSE).
