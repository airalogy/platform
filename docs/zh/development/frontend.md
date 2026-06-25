# Airalogy Platform JavaScript Workspace

仓库根目录是 Airalogy Platform Community Edition 的 pnpm workspace，包含 Vue 3 Web 应用，以及 Web 应用使用的共享前端包。

## 环境要求

- Node.js 20.19+ 或 22.12+
- pnpm 10.15+

## 启动

```bash
corepack enable
pnpm install
pnpm dev
```

开发服务器默认监听 `http://localhost:3000`，并把 `/api` 代理到 `http://127.0.0.1:4000`。

如果需要连接其他后端：

```bash
VITE_API_BASE_URL=http://127.0.0.1:4000 pnpm dev
```

可选的本地环境文件：

```bash
cp apps/web/.env.example apps/web/.env.local
```

## 常用脚本

```bash
pnpm dev
pnpm build
pnpm lint
pnpm --filter @airalogy/web type-check
pnpm i18n:generate
```

## 目录结构

```txt
platform/
├── apps/web/            # 主 Airalogy Web 应用
├── apps/admin/          # 预留的管理端 workspace
├── packages/components/ # 共享 UI 组件
├── packages/composables/# 共享 Vue composables
├── packages/shared/     # 共享类型、i18n、常量和工具函数
└── scripts/             # workspace 脚本
```

面向用户展示的文案应放在 `packages/shared/src/locales/langs/` 下的 i18n 语言文件中。
