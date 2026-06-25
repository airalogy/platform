# Contributing

[中文版](CONTRIBUTING.zh-CN.md)

Thanks for contributing to Airalogy Platform.

## Development Principles

- Keep Community Edition usable as a self-hosted product.
- Do not add environment-specific deployment assumptions to public defaults.
- Keep Enterprise-only features behind explicit extension points rather than forks.
- Prefer integration with mature infrastructure such as PostgreSQL, Redis, MinIO, OIDC, and S3-compatible storage.
- Keep user-facing frontend text localized through the existing i18n system.

## Local Checks

Backend:

```bash
pnpm api:check
```

Frontend:

```bash
corepack enable
pnpm install
pnpm lint
pnpm --filter @airalogy/web type-check
```

## Public Safety

Do not commit:

- `.env` files
- private keys or certificates
- production credentials
- deployment-specific endpoints
- generated caches, logs, or build outputs

Run this before opening a pull request:

```bash
rg -n "PRIVATE KEY|your-private-domain.example" .
find . -name ".env" -o -name "*.pem" -o -name "*.key"
```
