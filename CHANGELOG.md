# Changelog

All notable changes to Airalogy Platform Community Edition are documented in this file.

Airalogy Platform uses a product version plus component versions:

- Product release version: tracked in [VERSION](./VERSION), used to describe one deployable platform release.
- Backend component version: tracked in [apps/api/pyproject.toml](./apps/api/pyproject.toml).
- JavaScript workspace version: tracked in [package.json](./package.json) and [apps/web/package.json](./apps/web/package.json).

Component versions may differ when only the backend or frontend changes. The product changelog should still record what shipped in each release.

中文更新日志见 [CHANGELOG.zh-CN.md](./CHANGELOG.zh-CN.md)。

## [Unreleased]

Target initial version: `0.1.0`.

### Added

- Initialized the Airalogy Platform Community Edition repository layout.
- Added local-first development defaults for PostgreSQL, Redis, and MinIO through Docker Compose.
- Added public setup, contribution, security, backend, and frontend documentation.
- Added GitHub Actions workflows for backend smoke checks and frontend linting.
- Added end-to-end Airalogy Protocol Workflow support with persisted workflow state, backend `/workflow` and `/workflow/step` APIs, Masterbrain AIRA integration, protocol context assembly, and record-data injection for multi-protocol runs.
- Added a File Storage Bridge for stable FileId references, explicit `airalogy_files` storage mappings, external file registration, and resolver-based file access.

### Changed

- Reset public versioning and release history for the Community Edition initial release.
- Reorganized the public repository as a product monorepo with `apps/api`, `apps/web`, `apps/admin`, and shared `packages/*`.
- Renamed the persisted workflow domain model from `ResearchWorkflow` to `ProtocolWorkflow`, including the public initial schema table name `protocol_workflows`.
- Consolidated database setup into a single initial schema migration.
- Excluded generated API artifacts, local caches, logs, certificates, environment files, and database dump files from the public source tree.
