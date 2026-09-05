# Platform browser E2E tests

This suite verifies the product through a real Chromium browser and a real PostgreSQL database. It is intentionally isolated from normal development:

- Web: `127.0.0.1:3100`
- API: `127.0.0.1:4100`
- PostgreSQL: `127.0.0.1:55432`
- Redis: `127.0.0.1:56379`
- MinIO: `127.0.0.1:59200`

The runner creates a dedicated Docker Compose project and removes its volumes after the run. It never reuses `apps/api/.data` or the normal development database.

## Run

Install dependencies and the Chromium runtime once:

```bash
pnpm install
pnpm exec playwright install chromium
```

Then run:

```bash
pnpm e2e
```

Use `pnpm e2e:headed` to watch the browser. Set `E2E_KEEP_INFRA=1` when debugging the database after a failed run.

## Coverage and artifacts

Run `pnpm research:integration` for authenticated Research API, persistent-worker and PostgreSQL acceptance without browser response mocks. It uses the same isolated infrastructure and migrations; do not run it concurrently with browser E2E on the same host. The four `research:benchmarks` scenarios remain fast function-level contract tests, not complete physical research demonstrations.

The suite exercises:

- real email/password login for owner and viewer roles;
- Lab-visible versus restricted resource access;
- resource creation and Schema validation;
- inventory receipt, over-consumption rollback, valid consumption and audit;
- old Record rendering with explicit cross-version projection/migration entry;
- private Paper → Knowledge, manual Research Tasks, My Log, responsive workbench, immediate Record draft persistence and storage/network failure recovery.

Run `AI_ENABLED=false pnpm e2e researcher-journey.spec.ts` for the core researcher journeys with the backend AI disabled.

Failures retain screenshots, video and traces in `test-results/`. The HTML report is written to `playwright-report/`. CI uploads both directories, plus the API log.

Prefer `data-testid` for workflow controls and user-visible text for business outcomes. Seed only through the development fixture endpoint and public APIs, so browser tests do not depend on private database implementation details.
