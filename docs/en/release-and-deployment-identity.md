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

`VERSION` is the canonical product version. A formal release synchronizes the root, API, and Web versions; moves both changelogs out of `Unreleased`; and creates an annotated `v<version>` tag from a clean verified commit.

The tag-triggered Release workflow runs backend, frontend, deployment, and release checks; builds multi-architecture API, Web, Protocol Executor, and PostgreSQL images; generates SBOM and provenance attestations; and assembles an immutable release package. Production uses `image:version@sha256:digest`, never `latest` as its sole identity.

A source checkout remains suitable for development and evaluation. It may be marked dirty and does not carry the verification meaning of a formal release manifest.

The official `ghcr.io/airalogy/airalogy-engine:0.16.0` image supports both `linux/amd64` and `linux/arm64`. Platform pins its immutable SHA-256 manifest digest instead of relying on `latest`, so deployments on both architectures resolve to the same verified release identity.

## Deployment and support

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
