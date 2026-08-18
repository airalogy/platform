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
- Added scoped raw Record exports for Lab Owners and Project Owners/Managers, with snapshot-consistent background jobs, `.aira`, JSONL and single-Schema CSV formats, optional revision history, deduplicated attachments, immutable Lab audit events, seven-day downloads, in-app completion notifications, and export history/regeneration controls.
- Added a no-code Aira workflow in Protocol Editor: users can describe an experiment in natural language, generate and preview a structured Protocol, then discuss or refine it conversationally. Questions receive answers without changing files, while safe requested changes apply immediately with plain-language summaries, inline or side-by-side visual diffs, and undo controls; validation warnings and file deletions remain gated for review.
- Added a recommended “Write a Protocol with AI” creation method that opens the existing Aira drafting workflow directly in the current Lab and Project context.
- Added end-to-end release and deployment identity: runtime version reporting, Alembic revision visibility, immutable four-image release manifests, tag-triggered verified releases, persisted deployment history, an opaque deployment ID, and sanitized operator support bundles.
- Added an explicit trademark and customer-data boundary for public Community Edition distributions.
- Added a unified, Airalogy-branded bilingual VitePress documentation system for the public site and version-matched Single-Lab images, plus a deployment-aware in-product Help Center with role-relevant user, Lab administration, self-hosting, and managed-support entry points.

### Changed

- Centralized Platform UI typography into shared semantic roles for titles, body copy, labels, metadata, status, metrics, and code; the browser, Naive UI, and UnoCSS now use one Chinese/English font stack, with core Home, Lab, Project, Protocol, and Record surfaces migrated to the shared system.
- Reworked the home page into a role- and work-state-aware task workbench that resumes real local Record drafts, starts the most recent Protocol directly, inherits recent Project context for Protocol creation, exposes management shortcuts only from actual memberships, and uses a bounded 1920px wide-screen canvas without stretching other product pages.
- Improved Record entry with visible device-local draft status, manual save feedback, required-field progress, first-error focus, a deterministic destination/resource submission preview, and explicit post-submit next steps.
- Made AI an explicit instance capability: provider-backed Aira entry points appear only when available, while AI-disabled instances retain the complete deterministic Protocol and Record experience without empty chat controls.
- Simplified Protocol creation into recommended Aira/template paths and secondary reuse, Hub, `.aira`, ZIP, and from-scratch paths, preserving current or recent Project context.
- Reset public versioning and release history for the Community Edition initial release.
- Reorganized the public repository as a product monorepo with `apps/api`, `apps/web`, `apps/admin`, and shared `packages/*`.
- Renamed the persisted workflow domain model from `ResearchWorkflow` to `ProtocolWorkflow`, including the public initial schema table name `protocol_workflows`.
- Consolidated database setup into a single initial schema migration.
- Excluded generated API artifacts, local caches, logs, certificates, environment files, and database dump files from the public source tree.
- Updated Platform to `masterbrain==0.11.0` and the released `@airalogy/masterbrain-client` / `@airalogy/masterbrain-vue` packages. Protocol drafting now uses Masterbrain's single-file generation contract, while shared packages own AI edit contracts, risk handling, safe apply/undo logic, and Diff rendering instead of Platform maintaining duplicate intelligence and UI infrastructure.
- Updated `@airalogy/masterbrain-vue` to `0.2.0` and delegated its change status, review, Diff, file, and risk labels to the package's reactive built-in English/Chinese localization. Platform now passes only its active locale and retains product-specific Aira and modal-shell copy.
- Updated the API wrapper to `airalogy-engine==0.0.9`, replaced the floating Airalogy Engine image with the immutable official `0.16.0` multi-architecture digest for `linux/amd64` and `linux/arm64`, and made the isolated Protocol Executor image configurable and versioned with the Platform release.
- Replaced the withdrawn `numpy==2.4.0` build dependency with compatible patch release `2.4.6` in the API environment and isolated Protocol Executor.
- Raised the production Web build heap default to 6 GB after the complete application build exceeded the former 4 GB limit.

### Fixed

- Made Protocol list rows responsive so long titles, ownership context, secondary creation metadata, metrics, and actions retain a stable visual hierarchy and wrap cleanly on narrow screens instead of compressing into one overflowing line; aggregated lists now retain the non-sensitive star and reuse metrics while record actions remain permission-gated.
- Fixed browsers retaining an unrelated cached site icon instead of the Airalogy favicon.
- Added the owning Lab and Project path to aggregated Protocol lists so “My Protocols” and profile views retain their workspace context.
- Fixed Protocol, Project, Lab, and Group descriptions showing a non-functional “Read more” action when the full text already fit within the three-line preview.
- Fixed the AI Protocol review Diff editor collapsing into a thin strip, and reorganized the Aira sidebar guidance into a clearer assistant card.
- Fixed the Protocol Editor's post-generation handoff opening the Aira conversation pane at the generic narrow sidebar width instead of its intended readable width.
- Fixed the Lab resource library failing to render on first client-side navigation because its modal roots were incompatible with route transitions.
- Fixed the Record diary submission heatmap failing to finish rendering and leaving its loading indicator visible.
- Kept the isolated Protocol executor's Airalogy dependency aligned with the backend to prevent `.aira` imports from failing when executor modules change.
- Fixed Record export snapshots on non-UTC API hosts and preserved requested filenames on MinIO and OSS presigned downloads.
