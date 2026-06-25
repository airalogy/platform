# 更新日志

这里记录 Airalogy Platform Community Edition 的重要变更。

Airalogy Platform 采用“产品版本 + 组件版本”的方式：

- 产品发布版本：记录在 [VERSION](./VERSION)，用于描述一次可部署的平台版本。
- 后端组件版本：记录在 [apps/api/pyproject.toml](./apps/api/pyproject.toml)。
- JavaScript workspace 版本：记录在 [package.json](./package.json) 与 [apps/web/package.json](./apps/web/package.json)。

如果只更新后端或只更新前端，组件版本可以不同。产品更新日志仍然记录每次发布实际包含的内容。

English changelog: [CHANGELOG.md](./CHANGELOG.md)。

## [未发布]

目标初始版本：`0.1.0`。

### 新增

- 初始化 Airalogy Platform Community Edition 仓库结构。
- 新增基于 Docker Compose 的 PostgreSQL、Redis 和 MinIO 本地开发默认配置。
- 新增公开版安装、贡献、安全、后端和前端文档。
- 新增后端 smoke check 与前端 lint 的 GitHub Actions workflow。
- 新增端到端 Airalogy Protocol Workflow 支持，包括 workflow 状态持久化、后端 `/workflow` 与 `/workflow/step` API、Masterbrain AIRA 集成、Protocol 上下文组装，以及多 Protocol 运行时的 Record 数据注入。
- 新增 File Storage Bridge，支持稳定 FileId 引用、`airalogy_files` 显式存储映射、外部文件注册和基于 resolver 的文件访问。

### 变更

- 将公开版版本号与发布历史重置为 Community Edition 初始发布。
- 将公开仓库整理为产品级 monorepo：`apps/api`、`apps/web`、`apps/admin` 与共享 `packages/*`。
- 将持久化 workflow 领域模型从 `ResearchWorkflow` 改名为 `ProtocolWorkflow`，公开版初始 schema 表名同步为 `protocol_workflows`。
- 将数据库初始化整理为单一初始 schema migration。
- 从公开源码树中排除生成的 API 产物、本地缓存、日志、证书、环境文件和数据库 dump 文件。
