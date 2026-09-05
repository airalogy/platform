# Platform browser E2E tests

This suite runs Chromium against a local API and PostgreSQL database. Individual UI specs may mock selected responses; the researcher journey coverage below distinguishes real persistence from simulated interactions. The environment is isolated from normal development:

- Web: `127.0.0.1:3100`
- API: `127.0.0.1:4100`
- PostgreSQL: `127.0.0.1:55432`
- Redis: `127.0.0.1:56379`
- MinIO: `127.0.0.1:59200`

The runner creates a dedicated Docker Compose project and removes its volumes after the run. It never reuses `apps/api/.data` or the normal development database.

Use synthetic data only. Fixture accounts and passwords are intentionally public test values, not production credentials. Never reuse them on a deployed instance or point `E2E_WEB_URL` / `E2E_API_URL` at a production or customer environment.

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
- editable Protocol template publication, valid Record submission by a separate member, revision history, and API denial of Viewer writes;
- private Paper → Knowledge, manual Research Tasks, My Log, responsive workbench, immediate Record draft persistence and storage/network failure recovery.

### Researcher journey acceptance

Run the core journeys with the default instance configuration and with the backend AI disabled:

```bash
pnpm e2e first-record.spec.ts researcher-journey.spec.ts
AI_ENABLED=false pnpm e2e first-record.spec.ts researcher-journey.spec.ts
```

| Specification | Acceptance checks | Backend boundary |
| --- | --- | --- |
| [First Record](./specs/first-record.spec.ts) | An author publishes an editable practice Protocol; a different member submits a valid Record, opens the exact saved report, provides a correction reason, and can still read the original version. Invalid values and Viewer writes are rejected. | Real API writes and history reads; one field-error response is injected to check focus and input preservation. |
| [Researcher journeys](./specs/researcher-journey.spec.ts) | Private Paper import and Knowledge persistence, manual Task creation, My Log, tablet workbench, immediate draft saving, reload recovery, and truthful storage/network failure feedback. With AI disabled, Chinese Human Work labels receive distinct stable keys and the Action is created through preview and confirmation. | Real API persistence; explicit network and storage fault injection. |
| [Structured Human Work](./specs/research-human-work.spec.ts) | Structured submission, preview, validation feedback and review controls follow the declared contract. | Mocked API responses for UI behavior; this is not database acceptance. |

For real database and persistent-worker acceptance, use `pnpm research:integration` and inspect [the Research integration tests](../../apps/api/tests/test_research_integration.py). [Executor validation tests](../../apps/api/tests/test_protocol_executor_validation.py) exercise the same bilingual AIMD practice files used by the editor, including custom model constraints and configured package storage. Their optional Docker case requires a locally built Protocol executor image tagged `airalogy-platform-protocol-executor:local` and `RUN_DOCKER_PROTOCOL_TESTS=1`.

### Limits of this coverage

- Practice Protocols and observations are synthetic, not scientific evidence. Legacy display fixtures such as the IC50 example are not acceptance tests for scientific calculations or equipment execution.
- Automated completion times do not establish unaided usability. Evaluate first-Record completion, Protocol authoring, error recovery and understanding of save destinations separately with representative researchers.
- The covered journeys do not establish complete Lab administration, Workflow, data-governance, accessibility or device-integration usability. Keep uncovered cases explicit when reporting results.

### Diagnostic artifacts

Failures retain screenshots, video and traces in `test-results/`. The HTML report is written to `playwright-report/`. CI uploads both directories, plus the API log.

Keep generated reports, authentication state, logs, screenshots and per-run workstation notes out of Git. Inspect diagnostic artifacts before sharing them publicly; they may contain session data or submitted values. Repository documentation should describe reproducible scenarios, acceptance criteria and known limitations rather than individual execution journals or rolling pass counts.

Prefer `data-testid` for workflow controls and user-visible text for business outcomes. Seed only through the development fixture endpoint and public APIs, so browser tests do not depend on private database implementation details.
