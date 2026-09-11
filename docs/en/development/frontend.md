# Airalogy Platform JavaScript Workspace

The repository root is the pnpm workspace for Airalogy Platform Community Edition. It contains the Vue 3 web app and the shared frontend packages used by the app.

## Requirements

- Node.js 20.19+ or 22.12+
- pnpm 10.15+

## Setup

```bash
corepack enable
pnpm install
pnpm dev
```

The dev server listens on `http://localhost:3000` and proxies `/api` to `http://127.0.0.1:4000` by default.

To point the frontend to another backend:

```bash
VITE_API_BASE_URL=http://127.0.0.1:4000 pnpm dev
```

Optional local environment:

```bash
cp apps/web/.env.example apps/web/.env.local
```

## Scripts

```bash
pnpm dev
pnpm build
pnpm lint
pnpm --filter @airalogy/web type-check
pnpm i18n:generate
```

## Structure

```txt
platform/
├── apps/web/            # Main Airalogy web app
├── apps/admin/          # Reserved admin workspace slot
├── packages/components/ # Shared UI components
├── packages/composables/# Shared Vue composables
├── packages/shared/     # Shared types, i18n, constants, utilities
└── scripts/             # Workspace scripts
```

User-facing strings should live in the i18n locale files under `packages/shared/src/locales/langs/`.

## Shared UI contracts

Product typography, layout and interaction rules are documented in `apps/web/src/styles/README.md`. Use the opt-in `aira-dialog` class for card modals, with an inline `--aira-dialog-width` when needed: headers and confirmation footers remain visible while long content scrolls. Optional fields use keyboard-operable disclosures; errors remain visible and preserve input. An interrupted confirmation must not be reported as a definitely failed write.

Core navigation uses one set of destinations for desktop links and the compact current-module menu. APIs, not navigation visibility, enforce access. Extend `tests/e2e/specs/workspace-interactions.spec.ts` when changing these contracts; test small screens and the AI-disabled path as well as desktop.

## Record table dependency boundary

Column selection belongs to `@airalogy/aimd-renderer`, including its native **Show all columns** / **Restore default columns** menu, default-column policy and localized labels. Platform binds the existing field/metadata selection events and stores preferences per user and Protocol; do not duplicate AIMD field traversal in the page.

Use the published AIMD packages through the default catalog in `pnpm-workspace.yaml`: Core 2.16.0, Editor 1.12.0 and Renderer 2.13.0. All direct consumers declare `catalog:`; the workspace catalog is the single version source and the lockfile records the resolved packages and integrity. The former Renderer 2.12.0 patch is removed: no local source override, sibling checkout or Python `airalogy` upgrade is required. For future upgrades, change the catalog, regenerate the lockfile, and repeat the browser tests and production build against the actual published packages. `pnpm aimd:dependencies:test` checks exact release pins, shared consumers and the absence of a Renderer patch; it also runs as part of `pnpm type-check`.

Run `pnpm e2e record-export.spec.ts record-columns.spec.ts` for responsive export dialogs, actual export/download, native column actions, hidden metadata restoration, keyboard use, wide-table scrolling and preference reloads in both languages. Include `first-record.spec.ts` and `schema-governance.spec.ts` when upgrading Core or Editor to check Protocol creation, Record submission/revision and versioned evidence. Column tests expand only the displayed Protocol catalogue with synthetic fields; authentication and Record loading remain real. Repeat with `AI_ENABLED=false`. Keep per-run screenshots and logs out of Git.
