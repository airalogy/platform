# Platform development

Airalogy Platform is a monorepo containing the FastAPI backend, Vue Web application, shared packages, deployment assets, tests, and this documentation. Read the repository `AGENTS.md` and the relevant subsystem documentation before changing code.

## Repository map

| Path | Responsibility |
| --- | --- |
| `apps/api` | FastAPI API, database models and migrations, background work, storage, and executor integration. |
| `apps/web` | Authenticated Vue product experience and deployment-aware navigation. |
| `packages/*` | Shared UI, composables, types, localization, and cross-surface contracts. |
| `deploy/single-lab` | Production-oriented Single-Lab images, proxy configuration, setup, validation, backup, and upgrade tools. |
| `docs` | The only Platform documentation source for both public and image-bundled sites. |

## Local workflow

Use the checked-in package-manager and runtime versions. Install with the lockfile, run the smallest relevant tests first, then the broader checks for the affected subsystem. Generated localization types should be regenerated through the repository script instead of being edited by hand.

For documentation:

```bash
pnpm docs:dev
DOCS_BASE=/platform/ pnpm docs:build
```

`DOCS_BASE` is the single base-path input. The public GitHub Pages mirror uses `/platform/`; packaged Platform deployments use the same-origin `/docs/` path. The root `pnpm dev` and `pnpm build` commands generate that version-matched documentation inside the Web public assets.

## Architecture and contracts

- [Frontend development](../development/frontend) covers the JavaScript workspace and Web build.
- [File Storage Bridge](../architecture/file-storage-bridge) defines stable file identity and storage resolution.
- [Self-hosted architecture](../architecture/self-hosted-architecture) explains service and data placement.
- [Access control](../access-control) documents roles, grants, inheritance, and backend enforcement.

Prefer one shared contract over repeated surface-specific logic. Keep deterministic authorization, validation, and operational decisions in code; AI-generated narrative must not silently change those decisions.

## Documentation boundary

Product behavior, public architecture, deployment procedures, and release notes belong in this repository. Customer server details, credentials, private network topology, SLA terms, and delivery history do not. Role-aware Help Center cards improve navigation but must never be treated as authorization for the public documentation files.

Keep existing public document paths working when reorganizing navigation. The former standalone documentation repository remains a migration reference until the new site is live; archiving it is a separate decision.
