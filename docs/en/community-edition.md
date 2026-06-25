# Community Edition Overview

Airalogy Platform Community Edition is the self-hosted platform layer for research data, protocols, records, and AI-assisted scientific collaboration. It is designed for teams that need to keep large research files close to their own storage environment while still using a web-based workflow system.

## Core Capabilities

- Workspace model: manage labs, projects, protocols, records, folders, members, stars, comments, and basic permissions.
- Self-hosted friendly authentication: use email/password registration and sign-in by default, without requiring an SMS provider.
- Protocol-centered research workflow: create and manage AIMD-based protocols, record structured experimental data, and keep protocol / record data connected through stable schemas.
- Protocol Workflow: connect multiple protocols into a workflow, define graph edges and starting points, and run workflow steps with backend persistence.
- AI assistance: use configured model providers and the installed Masterbrain package for chat, protocol assistance, record context, and workflow support.
- Protocol Editor and Recorder: provide browser-based editing and recording surfaces for protocol code, metadata, variables, files, and record entry.
- File Storage Bridge: store stable `FileId` references in protocols and records while resolving the real file location through the backend.
- Managed object storage: use local/self-hosted MinIO by default, or switch managed uploads to Aliyun OSS through configuration.
- Self-hosted deployment path: run PostgreSQL, Redis, MinIO, and the API with Docker Compose, then connect the Vue web app through the local API proxy.
- Public monorepo structure: keep the API, web app, shared types, components, and composables in one repository that can be audited and extended.

## Distinctive Features

### Stable File References

Protocols and Records should store logical file identities such as `airalogy.id.file.<uuid>.<ext>`, not physical OSS, MinIO, or file-server URLs. This lets a deployment move files between storage backends without rewriting historical research records.

### Large Data Friendly Architecture

The platform separates business metadata from file payloads. PostgreSQL stores users, projects, records, permissions, and FileId indexes. MinIO or OSS stores the actual file objects. This avoids putting large scientific files directly into the relational database.

### Protocol Workflow

Community Edition includes the backend and frontend integration needed to compose multiple protocols into a workflow. This supports research processes where one protocol produces values, files, or decisions that feed later protocols.

### AI With Local Control

AI features are optional and depend on configured provider keys. The platform integrates with the published Masterbrain package so self-hosted deployments can use AI assistance without depending on a separate private service by default.

### No Mandatory SMS Provider

Community deployments can create accounts with email and password by default. Phone verification and SMS delivery are treated as optional deployment-specific extensions, not as a requirement for local startup.

## Included By Default

- FastAPI backend
- Vue 3 web app
- PostgreSQL, Redis, and MinIO Docker Compose stack
- Alembic migrations for the initial Community schema
- File upload, file registration, FileId resolution, and download APIs
- Protocol Workflow APIs
- English and Chinese public documentation
- GitHub Actions for backend smoke checks and frontend lint/type checks

## Related Documents

- [File Storage Bridge](./architecture/file-storage-bridge.md)
- [Self-Hosted Architecture](./architecture/self-hosted-architecture.md)
- [Frontend Development](./development/frontend.md)
- [Chinese documentation](../zh/README.md)
