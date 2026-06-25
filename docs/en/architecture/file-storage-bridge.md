# File Storage Bridge

Airalogy Protocols should record stable file references, not storage-provider URLs. A `FileId` value such as `airalogy.id.file.<uuid>.<ext>` is the logical identity of a file. The backend resolves that identity to the current storage location only when a user with permission needs a preview, download, or AI processing input.

## Data Model

The `airalogy_files` table is the file reference index. It stores:

- logical file identity and filename
- content type, size, and checksum metadata
- project, protocol, and owner references
- storage backend, namespace, and object key for managed object storage
- optional external URI metadata for registered files that already live in another data center

Managed uploads write the file into the configured object storage backend and persist the exact backend, namespace, and object key used for that file. Registered external files create a FileId without copying the payload into Airalogy.

## Resolver Flow

```text
Record FileId
  -> airalogy_files row
  -> permission check
  -> storage backend resolver
  -> short-lived URL or backend stream
```

Protocol and Record payloads remain stable if a deployment moves from MinIO to OSS, uses a central file server, or adds a data-center connector. Only the resolver and storage adapter need to know about the physical layout.

## Current Backends

- `minio`: Community default for local and self-hosted deployments.
- `oss`: optional Aliyun OSS backend. Configure `OSS_REGION`, `OSS_ENDPOINT`, `OSS_BUCKET`, and OSS credentials.
- `external` or deployment-specific names: registered external locations. These are indexed by Airalogy and can be resolved by an added connector.

## API Surface

- `POST /airalogy_files`: upload and create a managed FileId.
- `POST /airalogy_files/register`: register an existing external file and create a FileId.
- `GET /airalogy_files/{id}`: resolve metadata and an access URL.
- `GET /airalogy_files/{id}/url`: resolve a short-lived access URL.
- `GET /airalogy_files/{id}/download`: stream or redirect a file after permission checks.
