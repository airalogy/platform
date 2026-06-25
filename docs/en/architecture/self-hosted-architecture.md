# Self-Hosted Architecture

Airalogy Platform Community Edition is designed for team and institutional self-hosting. For large research datasets, the platform, object storage, and data ingestion path should run close to the data instead of uploading every raw file to a public cloud by default.

## Design Principles

- `Airalogy Platform` manages accounts, labs, projects, protocols, records, permissions, search, and collaboration.
- Large raw files should preferably land in local object storage, such as self-hosted MinIO or an institution-managed object store.
- The database stores business metadata, permission relations, indexed fields, and object references; it should not hold large file payloads directly.
- AI and automation features connect through configured model services and the published Airalogy / Masterbrain packages.
- The public edition provides a clear local deployment path. Enterprise-grade multi-site sync, advanced audit, and proprietary storage connectors can extend this foundation.

## Default Local Topology

```text
Browser
  -> Airalogy frontend
  -> Airalogy backend
  -> PostgreSQL
  -> Redis
  -> MinIO
```

Docker Compose starts PostgreSQL, Redis, MinIO, and the backend API by default. The frontend can connect to the backend through the local Vite development server.

## Data Persistence And Safety

The default local deployment persists data under `apps/api/.data` through paths configured in `.env`:

- `POSTGRES_DATA_PATH=./.data/postgres`: PostgreSQL database files.
- `MINIO_DATA_PATH=./.data/minio`: MinIO object storage files.

Stopping, restarting, or rebuilding containers does not remove these directories automatically. Treat `.data` as a real business data directory, not as disposable cache.

For team or institutional deployments, at minimum:

- Use stable absolute paths, dedicated disks, or managed volumes for PostgreSQL and object-storage data.
- Back up both the PostgreSQL database and object-storage buckets. Database-only backups cannot restore the file payloads behind FileIds, and object-storage-only backups cannot restore permissions or business indexes.
- Replace every example secret and default password from `.env.example`, including `SECRET_KEY`, `AES_KEY`, `INNER_API_KEY`, database passwords, and object-storage credentials.
- Do not expose PostgreSQL, Redis, or MinIO management ports directly to the public internet. Public access should go through a reverse proxy, TLS, authentication, and network access controls.
- Give backups, object-storage buckets, and database volumes separate access policies. Avoid sharing one long-lived credential across application, operations, and backup roles.
- Practice recovery on a clean machine to confirm database backups, object-storage backups, and `.env` / key material can restore a working system.

Redis is used as cache, queue, or short-lived state by default. It should not be the only persistence layer for core business data. If a deployment makes task queues or async state strongly dependent on Redis, configure Redis persistence and backup separately.

## Large File Strategy

Scientific raw files can be very large. Sending all files through the public internet or through the application backend increases bandwidth, cost, and reliability risk. Recommended strategy:

- Browser upload is suitable for lightweight files and regular attachments.
- Large files should preferably be written into object storage inside the local network.
- The backend stores FileId mappings in `airalogy_files`, including storage backend, namespace, object key or external URI, checksum metadata, permission relations, preview references, and analysis-result references.
- For cross-site collaboration, sync metadata, previews, and results first; raw files can be synchronized asynchronously or fetched on demand according to policy.

Protocols and Records store stable `airalogy.id.file.<uuid>.<ext>` values, not physical OSS or central file-server URLs. See [File Storage Bridge](./file-storage-bridge.md) for the detailed design.

## Permission Boundary

Community Edition's core permission boundary is formed by Labs, Projects, Protocols, and Records. Deployment operators should also configure:

- Strong random `SECRET_KEY`, `AES_KEY`, and `INNER_API_KEY`
- Private network or reverse-proxy access controls
- Object-storage bucket permissions
- Database and Redis access controls
- Backup retention, log retention, and key rotation policies

## Extension Points

The public repository keeps the core platform deployable and auditable. Future extensions can add capabilities without changing the core data model:

- Institutional identity provider integration
- Multi-site ingestion and synchronization agents
- Resumable uploads and local data collection tools
- Fine-grained audit and compliance reports
- Proprietary object storage, HPC, or instrument connectors
