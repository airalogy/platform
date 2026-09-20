# Repository Working Rules

## Scope and ownership

- Treat this repository as the source of truth for Airalogy Platform product code, deployment behavior, release notes, and operational fixes.
- Read the relevant objective, specification, and nearby documentation before changing a subsystem.
- Preserve unrelated user changes. Stage and commit only the files that belong to the accepted change.

## Versioning

- `VERSION` is the canonical Airalogy Platform product release version.
- `apps/api/pyproject.toml`, the root `package.json`, and `apps/web/package.json` track component versions. Keep them aligned with the product version at release time unless a component is intentionally released independently.
- Ordinary feature, fix, and dependency commits update the `Unreleased` section of both changelogs when they affect shipped behavior. Do not bump the product version in every development commit.
- A release change must:
  - choose the SemVer increment from the shipped compatibility impact;
  - update `VERSION` and every component version included in the release;
  - move the relevant changelog entries from `Unreleased` into the new release section;
  - create an annotated Git tag named `v<version>` from the verified release commit.

## Dependency consistency

- Production dependency changes must update their lockfiles, affected runtime manifests, tests, and `Unreleased` changelog entries.
- When the same dependency is declared for multiple runtimes, keep the versions aligned or document and test the intentional compatibility range.
- The API host and isolated Protocol executor must use the same exact Airalogy version. Keep the automated consistency test passing.
- Prefer one generated or shared dependency source over manually duplicated pins when the build tooling can support it safely.

## Deployment identity

- Deploy production from a clean, committed revision and record both the Platform version and Git SHA.
- Treat an emergency server fix as temporary until the corresponding source change is committed and deployed reproducibly.
- Tag deployable images with the Platform version and an immutable Git SHA. `latest` may be a convenience alias, but must not be the only deployment identity.
- Rebuild the Protocol executor image whenever its Dockerfile, dependency manifest, or mounted executor code changes incompatibly.

## Verification and commits

- Run the smallest relevant tests first, then the broader release checks required by the affected subsystem.
- Treat failed hooks, migrations, image builds, and deployment checks as blockers until their cause is identified.
- Run `git diff --check`, inspect the staged diff, and keep operational fixes separate from unrelated feature work.

## Production incidents and patch releases

- Follow `docs/en/release-and-deployment-identity.md` (Chinese equivalent: `docs/zh/release-and-deployment-identity.md`) for incident classification, release gates, backup evidence, and recovery.
- Separate incident recovery from feature upgrades. A production hotfix branches from the deployed release (use `codex/hotfix-*`), contains only the necessary fix and regression coverage, and is also applied to the development branch.
- Ship compatible product fixes as patch releases. Configuration or missing-artifact repairs do not inherently require a product version bump, but must have a private operational change record and a reproducible deployment procedure.
- Never overwrite a published release tag or artifact. Deploy the same immutable artifacts that passed validation; failed checks block routine publication and deployment.
- Prefer a verified compatible rollback during an incident. Direct server edits are emergency-only, require explicit authorization and a recovery plan, and must be reconciled into source and a reproducible deployment before incident closure.
- For database changes, verify a suitable recovery point and rehearse the actual source-to-target migration. Do not assume cloud redundancy is a backup or that switching application images reverses a schema migration. Record the impact on writes made after cutover.
- Keep real server addresses, credentials, backup locations, customer data, and incident evidence in private operational records, not this public repository.
