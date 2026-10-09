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

## Commit, push and CI checks

- **pre-commit** formats and lints staged files only; it does not run browsers, databases or image tests.
- **pre-push** selects fast checks from the actual outgoing commit diff: workflow validation, affected unit/contract tests, lint and relevant types. Long database, container, browser and production-build gates are reported as deferred to CI. Manual invocation compares committed changes with upstream; uncommitted edits are not represented as a verified push.
- **GitHub CI** invokes the same registered gates and retains Linux/macOS matrices, hosted-runtime permissions, SDK packaging, real release provenance, image installation and backup/restore acceptance. Local success does not prove those remote gates have passed.

Install GitHub CLI `gh` and locked workspace dependencies, then explicitly provision the pinned workflow checker:

```bash
pnpm ci:tools:install
pnpm exec playwright install chromium
pnpm prepush:check --plan
pnpm prepush:affected --plan
pnpm prepush:full --plan
pnpm prepush:full
```

`ci:tools:install` downloads official actionlint 1.7.12, verifies archive and executable SHA-256 hashes and stores it in ignored `.cache/actionlint/`. Every execution rechecks the bytes. Linux/macOS x64 and arm64 are supported. Checks never implicitly install or upgrade tools or change system permissions; missing tools and corrupt caches block the affected gate with an error. actionlint validates workflow structure and expressions, not ShellCheck, every shell command's portability or remote permissions.

`prepush:affected` explicitly runs the extended gates selected by the outgoing diff. `prepush:full` runs all registered local gates regardless of the diff: versions, public service-image availability, Python locks, lint, types, API, Gateway, real offline `gh` rejection, Compute Runner, instrument contracts, synthetic browser/rehearsal, release metadata and deployment identity, research database integration, docs, production build and full browser E2E. macOS additionally compiles native helpers; Linux does not claim macOS compilation coverage. Full E2E includes the focused AI subset without running it twice.

Full checks need Docker and isolated test infrastructure and take substantially longer than an ordinary push. Do not move them into every commit or run another suite sharing the E2E infrastructure concurrently. They do not operate real instruments, request desktop permissions, push images, create releases or substitute for real provenance and cross-platform CI.

The external-image preflight uses an empty temporary Docker configuration and bounded anonymous registry manifest requests, not cached image presence. It does not download layers, modify credentials or choose mirrors. A failure blocks the affected gate and release; cached local tests cannot qualify a cold installation.

Hosted browser CI uses four AI-enabled shards and one AI-disabled job, each with its own runner, database, storage and accounts. Each shard keeps one Playwright worker; only dependency downloads are cached, not database state or authentication. `browser-gate` succeeds only when preflight and every shard pass. This can reduce elapsed time but increase runner usage; measure actual runs before quoting a speedup. Local full runs remain sequential because their infrastructure uses fixed ports.

Repository administrators must configure branch protection/rulesets to require `browser-gate` and the applicable source checks, replacing the former single `chromium` check when necessary. Workflow files do not configure those remote settings. Release independently verifies all required source workflows for the exact commit; a successful local hook alone never authorizes publication.

Run a focused gate or reproduce a CI step with:

```bash
pnpm ci:check
node scripts/pre-push.mjs --check gateway-cli
node scripts/pre-push.mjs --check interface-tests
```

`scripts/pre-push.mjs` is the shared source for commands, environments and selection rules. Update its regression tests when adding workflow paths or gates. Preparation tests use temporary files only; actual permission changes remain restricted to disposable GitHub-hosted runners. Graphical-session and physical-equipment acceptance always require separate explicit authorization.

## Architecture and contracts

- [Frontend development](../development/frontend) covers the JavaScript workspace and Web build.
- [File Storage Bridge](../architecture/file-storage-bridge) defines stable file identity and storage resolution.
- [Self-hosted architecture](../architecture/self-hosted-architecture) explains service and data placement.
- [Access control](../access-control) documents roles, grants, inheritance, and backend enforcement.

Prefer one shared contract over repeated surface-specific logic. Keep deterministic authorization, validation, and operational decisions in code; AI-generated narrative must not silently change those decisions.

## Documentation boundary

Product behavior, public architecture, deployment procedures, and release notes belong in this repository. Customer server details, credentials, private network topology, SLA terms, and delivery history do not. Role-aware Help Center cards improve navigation but must never be treated as authorization for the public documentation files.

Keep existing public document paths working when reorganizing navigation. The former standalone documentation repository remains a migration reference until the new site is live; archiving it is a separate decision.
