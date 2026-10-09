# Bundled object storage

Platform builds the unmodified official MinIO server and `mc` sources into one versioned companion image. `sources.env` pins upstream commits, release identities and archive SHA-256 checksums; the Dockerfile pins the Go builder and base image by multi-architecture digest. Go modules are checksum-verified and vendored before compilation. This is not a fork, a shared database, or a dependency on an arbitrary third-party image mirror.

The pinned server is `RELEASE.2025-10-15T17-29-55Z`, which includes the fix for [CVE-2025-62506](https://github.com/minio/minio/security/advisories/GHSA-jjjj-jwhf-8rgr). The upstream repository is archived and distribution is source-only. This pin is not a promise of ongoing upstream maintenance: operators must continue reviewing security advisories and plan storage replacement separately when necessary. The newer embedded console is not equivalent to the old administration UI; use `mc` for administration. See the [upstream UI change](https://github.com/minio/minio/releases/tag/RELEASE.2025-05-24T17-08-30Z).

## Build and verify

```bash
node scripts/prepare-object-storage.mjs
node scripts/object-storage-acceptance.mjs
```

The helper reuses only an image whose input fingerprint and native architecture match this checkout. Browser CI builds once, tests recovery, then transfers that exact image to independent disposable test runners. It does not transfer accounts, database volumes or test data. Cold preflight checks the public base manifests and exact source URLs; the actual build checks archive hashes. Registry or source failures block CI rather than falling back to cached old upstream images.

Formal releases publish `platform-object-storage` alongside API/Web/Executor/DB, with the same Platform version, Git SHA, provenance, SBOM and public-pull gate. Both `MINIO_IMAGE` and `MINIO_MC_IMAGE` resolve to the same manifest-pinned image. Production installs these verified artifacts; it does not compile Go locally.

## Licenses and corresponding source

MinIO and mc retain their upstream AGPL-3.0 notices in `/licenses`. Every image contains the original checksum-verified archives, complete vendored source (including dependency license files), source lock and build instructions in `/usr/share/airalogy-object-storage/source`. Export these from a created container with `docker cp` when redistributing corresponding source; no running server or credentials are needed. The image's Platform packaging does not relicense MinIO. Consult the included licenses for redistribution obligations.

## Existing installations and recovery boundary

This does not change deployments using an external PostgreSQL or OSS service. For bundled MinIO, application upgrade/rollback checks the running engine commit. Repacking the same engine is allowed; a different or unknown engine is blocked before backup, write pause or volume reuse. Do not bypass this guard by manually pointing a new binary at an old volume or downgrading its files.

A separately approved storage migration must export to independent storage, restore onto a fresh destination, verify object hashes and access policies, rehearse rollback, and arrange a final write pause. The automated synthetic test covers private reads, signed URLs, multipart writes and current-object logical backup/restore. It does **not** certify every historical MinIO deployment or copy object version history, IAM, retention locks, lifecycle rules or replication. The existing single-Lab `mc mirror` backup has the same current-object limitation. Installations using those features need an appropriate additional recovery plan.
