# Airalogy Web App

This package is the main Vue application for Airalogy Platform Community Edition.

## Development

Enable the pinned pnpm version first:

```bash
corepack enable
```

```bash
pnpm install
pnpm --filter @airalogy/web dev
```

Defaults:

- Web: `http://localhost:3000`
- Backend proxy target: `http://127.0.0.1:4000`
- MinIO proxy target: `http://127.0.0.1:9200`

Override backend target when needed:

```bash
VITE_API_BASE_URL=http://127.0.0.1:4000 pnpm --filter @airalogy/web dev
```

## Build

```bash
pnpm --filter @airalogy/web build
```

## Environment

Use `apps/web/.env.example` as the public template. Do not commit real `.env` files, local TLS keys, analytics IDs, or deployment-specific endpoints.

China mainland compliance footer links are disabled by default. Set `VITE_CHINA_COMPLIANCE_FOOTER=Y` and provide the ICP / public-security record values only for deployments that legally use those records.
