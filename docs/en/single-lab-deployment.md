# Single-Lab Deployment

The `single_lab` profile packages Airalogy Platform as one private laboratory workspace. It uses the same domain model and source tree as Community Edition; there is no separate Lab Edition fork.

The profile creates one configured Lab, a default private Project, an initial owner account, invite-only membership, administrator-issued recovery links, and a reduced navigation surface. The production stack includes the web application, API, PostgreSQL, Redis, MinIO, Caddy reverse proxy, automatic TLS, configuration validation, and lifecycle scripts.

## Intended Scope

This profile is suitable for a laboratory that can operate one Linux server and accepts short maintenance windows. A practical runtime starting point is 4 CPU cores and 8 GB RAM. A host that builds the web image from source should have 16 GB RAM, with at least 8 GB available to Docker. Size SSD storage for the laboratory's records, file payloads, images, build cache, and backups. Keep backups on a different host or storage system.

It is not an HA cluster or an enterprise identity system. SSO/LDAP, multi-node failover, air-gapped installers, and compliance-specific controls remain outside this profile.

## Prerequisites

- A Linux host with Docker Engine and Docker Compose v2
- A public DNS name pointing to the host for automatic HTTPS
- Inbound TCP ports 80 and 443, plus UDP 443 if HTTP/3 is desired
- Enough free disk space for PostgreSQL, MinIO, images, builds, and backups

For a local evaluation, a domain is not required and the generated default uses `http://localhost:8080`.

## Install

From the repository root:

```bash
cd deploy/single-lab
./scripts/generate-env.sh \
  --site-url https://lab.example.org \
  --tls-email admin@example.org \
  --lab-name "Example Laboratory"
./scripts/start.sh
```

`generate-env.sh` creates `.env` with mode `600` and cryptographically random application, database, storage, encryption, and bootstrap secrets. It refuses to replace an existing file unless `--force` is supplied.

For local HTTP evaluation:

```bash
./scripts/generate-env.sh --site-url http://localhost:8080
./scripts/start.sh
```

The first build can take time because it compiles PostgreSQL extensions and the web application. Subsequent starts reuse the images.

## First Setup

1. Open `<SITE_URL>/setup`.
2. Read the initial setup code with `./scripts/show-setup-code.sh`.
3. Create the owner account.
4. Confirm that the configured Lab and `lab_protocols` private Project are visible.

The API serializes bootstrap requests and refuses setup if any user or Lab already exists. Production startup also requires the setup code from `.env`, which prevents an unauthenticated first visitor from claiming the instance.

## Members And Accounts

The owner and Lab managers can create single-use invitation URLs from the Lab member view. New users register through the URL; existing users sign in and accept it. Invitations are bound to an email address, expire, and are stored only as SHA-256 hashes.

The owner or a manager can also create a one-time password-reset URL for an eligible member. Managers can manage ordinary members but not the owner or other managers. Changing or resetting a password revokes previously issued login tokens.

The deployment does not require SMTP or SMS. Invitation and recovery URLs are copied and delivered through a channel chosen by the laboratory.

If no owner or manager can sign in, a Docker host administrator can issue a reset link without exposing a recovery endpoint on the network:

```bash
./scripts/operator-reset-link.sh owner@example.org
```

This command works only for a current member of the configured Lab and requires local access to the running API container and deployment `.env`. Creating a new link invalidates any previous unused reset link for that account.

## Organization And Access Control

The single-Lab profile enables `LAB_STRUCTURE_MODE=structured` by default. A Lab can define an organizational-unit tree up to three levels deep. Units can be departments, research groups, core facilities, project teams, committees, or other structures. A member may belong to multiple units, and a parent-unit manager can maintain descendants. Organizational units express membership; Projects and Protocols form a separate resource hierarchy, connected through many-to-many scoped grants.

The access workspace provides fixed roles, Lab / Project / Protocol scopes, downward inheritance, resource inheritance breaks, grant expiry, revocation, and effective-access explanations. Effective capabilities are the union of direct grants, grants from the member's organizational units and ancestor units, grants inherited from ancestor resources, and compatible legacy roles. Arbitrary policy expressions and explicit deny rules are intentionally excluded so decisions remain explainable.

An actor can delegate only capabilities they already hold at the target scope. Lab owner and administrator are membership identities managed on the Members screen, not ordinary scoped grants. Project managers can delegate lower roles inside Projects they manage; organizational-unit managers can maintain their unit and descendants but gain no research-resource access from that responsibility alone. Grant creation, updates, revocation, and revocation caused by Lab-member removal are recorded in an append-only audit trail.

Existing `ProjectUser`, Lab Group, `ProtocolUser`, and Project Group assignments remain compatibility inputs to the same effective-access resolver. Groups created before this upgrade remain as organizational units with the `other` type. New deployments should prefer organizational units plus scoped grants.

See [Lab Access Control](./access-control.md) for the complete role matrix, inheritance rules, administrative workflows, API index, and troubleshooting guidance.

## Network And TLS

Caddy is the only public service. It serves the Vue application and proxies same-origin requests:

- `/api/*` to FastAPI, with `/api` removed before forwarding
- `/minio/*` to MinIO, preserving the upstream host required by signed URLs

PostgreSQL, Redis, and the MinIO API are not published. The MinIO console is bound to `127.0.0.1` only. For a public domain, Caddy obtains and renews TLS certificates automatically; ports 80 and 443 must reach the host.

## Configuration

Edit `deploy/single-lab/.env`, then restart affected services. Backend-only changes need `docker compose` restart; values beginning with `VITE_` are compiled into the web image and require a web rebuild.

Before startup, both `preflight.sh` and the backend validate critical settings. Production rejects placeholder secrets, invalid AES keys, weak MinIO credentials, non-HTTPS remote origins, request-body logging, an incorrect API prefix, and a non-single-Lab profile.

AI features are optional. Set the provider keys in `.env`; protocol and record workflows remain available without them.

`LAB_STRUCTURE_MODE=structured` is required by the production single-Lab stack. The Community profile defaults to `flat` but can opt into `structured`; both profiles use the same authorization engine and database model.

`COMPONENT_BUILD_MEMORY_MB` and `WEB_BUILD_MEMORY_MB` control the Node.js heap limits used only while building the web image. Keep the generated defaults unless the host has a deliberately different Docker memory allocation.

## Operations

Check status and logs:

```bash
docker compose --env-file .env -f compose.yml ps
docker compose --env-file .env -f compose.yml logs -f api-server web
```

Stop the stack without deleting data:

```bash
./scripts/stop.sh
```

Do not add `--volumes` unless the persistent PostgreSQL, MinIO, Caddy, and application volumes are intentionally being destroyed.

### Backup

```bash
backup_path="$(./scripts/backup.sh)"
echo "$backup_path"
```

The script briefly pauses API writes, creates a PostgreSQL custom-format dump, mirrors and archives the MinIO bucket, copies the deployment secrets, writes a manifest and SHA-256 checksums, then restores API service. Backups contain plaintext credentials and encryption keys; keep them encrypted, access-controlled, and off-host.

### Restore

```bash
./scripts/restore.sh ./backups/20260711T120000Z-manual
```

Restore verifies checksums and the AES key, stops application writes, replaces the database and bucket, and waits for the API and web health checks. For disaster recovery on a new server, first use the backup's `secrets.env` as `deploy/single-lab/.env`, then run restore. This preserves the key needed to decrypt stored protocol secrets.

### Upgrade

Update the checked-out source to the intended release, review its release notes, then run:

```bash
./scripts/upgrade.sh
```

The script performs preflight checks, creates a consistent pre-upgrade backup, tags the current API and web images for rollback, stops API/Web during the memory-intensive build, rebuilds services sequentially, applies Alembic migrations at API startup, and waits for readiness. A build failure restarts the previous containers; a startup or health failure restores the pre-upgrade images and data automatically. Use `--build-db` when a release changes the PostgreSQL extension image.

### Rollback

```bash
./scripts/rollback.sh
```

Rollback uses the previous application image tags and restores the pre-upgrade database and object backup. It is intentionally confirmation-gated because post-upgrade writes are replaced.

## Verification

On a disposable, fresh deployment, run:

```bash
./scripts/acceptance-test.sh
```

This bootstraps an owner, verifies the default Project, invites a member, checks member permissions, changes and resets the member password, verifies JWT revocation, and confirms one-time token consumption. It creates test accounts and therefore refuses to run on an initialized instance.

The health endpoints are:

- `/api/health/live`: process liveness
- `/api/health/ready`: PostgreSQL, Redis, and object-storage readiness

## Security Checklist

- Keep `.env` and backups readable only by administrators.
- Use a dedicated host, current OS security updates, and a host firewall.
- Expose only Caddy ports; do not publish PostgreSQL, Redis, or the MinIO API.
- Keep `LOG_REQUEST_BODIES=false`; research records and credentials may be present in requests.
- Keep file log rotation enabled through `LOG_MAX_BYTES` and `LOG_BACKUP_COUNT`.
- Test restore regularly. A backup that has not been restored is not yet operationally proven.
- Rotate provider keys and deployment secrets under a documented maintenance procedure.

## Troubleshooting

Run `./scripts/preflight.sh` first. If startup fails, inspect `docker compose --env-file .env -f compose.yml logs api-server`. A migration or production configuration failure intentionally prevents the API from becoming healthy.

If signed object URLs fail, verify that `MINIO_PROXY_PATH=/minio` and that no additional proxy rewrites the path or upstream `Host` header. If automatic TLS fails, verify DNS and public reachability on ports 80 and 443.
