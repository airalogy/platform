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
