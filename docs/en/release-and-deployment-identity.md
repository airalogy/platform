# Release and Deployment Identity

Airalogy Platform identifies a deployable product as one indivisible release set rather than versioning Web and API independently in production.

## Identity layers

| Layer | Field | Purpose |
| --- | --- | --- |
| Product | `PLATFORM_VERSION` | User-facing semantic version |
| Source | Git tag and full Git SHA | Reproducible source identity |
| Release | SHA-256 of `release-manifest.json` | Binds API, Web, Protocol Executor, PostgreSQL, and the Alembic revision |
| Deployment | `AIRALOGY_DEPLOYMENT_ID` | Identifies one installation without carrying customer semantics |

`AIRALOGY_DEPLOYMENT_ID` is an opaque value such as `dep_<32 random hexadecimal characters>`. Do not put customer, Lab, domain, address, or contract information in it. A commercial operator may privately map this ID to customer and support records; that mapping does not belong in this public repository.

Platform does not send deployment identity, customer data, or runtime status back to Airalogy by default. A deployment administrator must explicitly create and share a sanitized support bundle when remote support is needed.

## Formal releases

`VERSION` is the canonical product version. A formal release synchronizes the root, API, Web, Compute Runner, Instrument Gateway and Instrument Interface package versions; moves both changelogs out of `Unreleased`; and creates an annotated `v<version>` tag from a clean verified commit. See the [v0.1.0 release overview](./releases/v0.1.0.md) for qualification boundaries.

The tag-triggered Release workflow runs backend, frontend, Instrument Gateway, deployment, and release checks; builds multi-architecture API, Web, Protocol Executor, and PostgreSQL images; builds version-matched Compute Runner and Instrument Gateway wheels and source distributions; generates SBOM and provenance attestations; and assembles an immutable release package. Before packaging, the exact image set undergoes account/permission acceptance, backup/restore and same-release upgrade/rollback rehearsals. Test configuration, backups and state stay outside the archive; unexpected files and symbolic links block packaging. Production uses `image:version@sha256:digest`, never `latest` as its sole identity. Equipment hosts install the Gateway artifact attached to the same GitHub release and verify its release provenance before adding a local hardware adapter.

A source checkout remains suitable for development and evaluation. It may be marked dirty and does not carry the verification meaning of a formal release manifest.

Release metadata generation requires Node.js and Python 3.11+. The standard-library AST reader accepts annotated and ordinary literal Alembic declarations without executing migration modules. It checks ancestry, missing parents, duplicate revisions and cycles before selecting the single head. Non-literal declarations or `depends_on` relationships require explicit tooling support and block publication instead of being silently ignored.

The official `ghcr.io/airalogy/airalogy-engine:0.16.0` image supports both `linux/amd64` and `linux/arm64`. Platform pins its immutable SHA-256 manifest digest instead of relying on `latest`, so deployments on both architectures resolve to the same verified release identity.

## Incident recovery and patch releases

This is the operating policy for maintainers; the checklist below is not a claim that every gate is automated. **Recover service separately from upgrading features.**

| Change | Delivery path |
| --- | --- |
| Compatible product defect fix | Regression test, patch release, then deploy the verified artifacts |
| Configuration, certificate, or missing matching image | Repair the environment, verify service, record the operational change; no automatic product version bump |
| Schema or data migration | Versioned release with compatibility assessment, migration rehearsal, and a data recovery plan |
| Urgent outage | Prefer a known-good compatible rollback; an explicitly authorized minimal emergency repair is temporary |

For example, a missing Protocol Executor image can be repaired by installing the image matching the running release. Improving the product's startup validation or error handling is a separate source fix and release. Do not bundle a broad feature/schema upgrade into that recovery.

### Hotfix lifecycle

1. Record the deployed version, SHA, artifact digests, database revision, impact, and sanitized diagnosis. Classify the cause before changing anything.
2. If development has moved ahead, branch from the deployed release (for example, `codex/hotfix-executor-startup`), not from unreleased feature work. Keep the fix, regression tests, and bilingual release notes focused. Apply the fix to the development branch as well.
3. Use a patch version for compatible fixes (for example, `0.2.0` to `0.2.1`); assess compatibility rather than labeling every urgent change a patch. Follow the formal release procedure above, including component versions and lockfiles. Published tags and artifacts are immutable.
4. Run focused regression tests first, then affected integration/security checks and required release gates. Local hooks provide early feedback; hosted CI and release checks remain required. Do not bypass failures to publish.
5. Validate the exact release artifacts in isolation and rehearse the actual deployed-to-target migration when relevant. Same-release upgrade tests do not qualify an older production schema. Record backup and recovery evidence before authorizing cutover.
6. Schedule any required write pause, obtain a final suitable recovery point, deploy the validated artifacts, and verify version identity, health, errors, and critical user flows such as Protocol saving and Record submission. Use designated test assets without modifying user research data.
7. Close the incident only after recording the result, remaining risks, and rollback disposition. For emergency server changes, reconcile source, tests, documentation, and reproducible deployment first. A published release is not evidence of deployment; a healthy endpoint alone is not evidence that the original task works.

### Backup and rollback gate

- Cloud replication or multi-zone redundancy does not itself establish historical recovery. Verify the actual backup policy, latest successful backup, retention, recoverable time range, restore permissions, and a successful restoration. For object storage, verify version history or a separate backup and its lifecycle rules.
- A verified cloud recovery point may satisfy the gate; a second full backup is not mandatory for every deployment. For a substantial migration or an unproven cloud recovery path, retain a dedicated pre-upgrade export/backup and rehearse restoration. A same-host copy is useful for rollback but is not independent disaster recovery.
- Cover the database, referenced files, configuration, and matching application artifacts. Document cross-store consistency and the write-pause strategy; unrelated live snapshots are not automatically one consistent recovery point.
- Decide whether the old application can run against the migrated schema. If not, image rollback alone is unsafe. Specify restore-to-new-database or other tested recovery steps, expected recovery time, and treatment of writes made after cutover. Do not automatically restore over production or discard new writes.
- Keep cloud database and object-storage infrastructure unless their replacement is a separately planned change. An application release does not authorize database engine downgrades or replacing external storage with bundled defaults.

### Private operational change record

Keep one restricted record per incident/deployment with: owner and approval; impact and cause; before/after version, SHA, artifact digests and schema; change classification and source fix; verification evidence; backup time and restore rehearsal; maintenance/write pause; rollback triggers and steps; post-cutover checks; and follow-up owner. Production addresses, credentials, data, backup paths, and unsanitized logs must not be placed in public issues, release notes, or this repository. Public changelogs describe the product fix, not the deployment topology.

## Deployment commands and support artifacts

After extracting a formal release package and completing `.env`, run:

```bash
./platformctl preflight
./platformctl install
./platformctl status
```

`GET /system/version` reports the product version, tag, Git SHA, build time, dirty state, release-manifest digest, Alembic revision, and opaque deployment ID. `platformctl status` verifies the running API against the release manifest.

Create an explicitly shared diagnostic artifact with:

```bash
./platformctl support-bundle
```

The bundle contains release identity, opaque core-image IDs and digests, database revision, and service health. It excludes image repository names, `.env`, secrets, logs, database contents, Records, attachments, user identities, and customer names. Treat it as restricted operational material nonetheless.

`AIRALOGY_STATE_DIR` retains the current release, install/upgrade/rollback events, release-manifest snapshots, and failure-recovery evidence. It stores neither secrets nor customer business information.
