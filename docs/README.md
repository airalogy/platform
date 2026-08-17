# Documentation

This directory is the only documentation source for Airalogy Platform. VitePress builds it for both the public documentation mirror and the same-origin `/docs/` site bundled with versioned Platform Web artifacts.

## Languages

- [English](./en/index.md)
- [中文](./zh/index.md)

The `en/` and `zh/` directories use the same audience structure:

```txt
docs/
├── en/
│   ├── user-guide/
│   ├── lab-admin/
│   ├── self-hosting/
│   └── developer/
└── zh/
    ├── user-guide/
    ├── lab-admin/
    ├── self-hosting/
    └── developer/
```

Existing top-level deployment, access-control, architecture, and development document paths remain stable and are included in the VitePress navigation.

## Build

```bash
pnpm docs:dev
DOCS_BASE=/platform/ pnpm docs:build
DOCS_BASE=/docs/ pnpm docs:build
```

`DOCS_BASE` is the only base-path setting. GitHub Pages uses `/platform/` as a public mirror; packaged Platform deployments use `/docs/`. The root `pnpm dev` and `pnpm build` commands generate the version-matched documentation inside the Web public assets before starting or building the application.

The repository contains public product documentation only. Customer-specific servers, accounts, network topology, SLA terms, support cases, and delivery records must remain in private customer systems.
