# Airalogy Platform

[English](README.md)

Airalogy Platform 是 Airalogy 研究数据与智能平台的自托管 Community Edition，包含 Web 应用、后端 API、本地对象存储集成、Protocol / Record 工作流，以及 AI 辅助科研协作界面。

这个仓库定位为公开的自托管平台层。Airalogy 核心标准、schema 和 SDK 包位于 `airalogy/airalogy`；Masterbrain AI 服务位于 `airalogy/masterbrain`。

## 版本边界

Community Edition 包含：

- Lab、Project、Protocol、Record、Chat 和 Protocol Editor 的 Web UI。
- 基于 FastAPI、PostgreSQL、Redis 和 S3-compatible object storage 的后端 API。
- 默认面向本地自托管的 MinIO 存储配置。
- 对已发布的 `airalogy`、`masterbrain` 和 `@airalogy/aimd-*` 包的集成。
- 基础 Project / Lab 权限。

Enterprise 扩展不应直接混入这个仓库，除非该能力对开源版也有通用价值。典型 Enterprise-only 能力包括高级 RBAC/ABAC、SSO/LDAP/AD/SAML、合规审计日志、离线安装包、集群运维和企业支持工具。

面向用户的能力说明见 [Community Edition 功能概览](docs/zh/community-edition.md)。

## 仓库结构

```txt
platform/
├── apps/
│   ├── api/    # FastAPI backend、migrations、Docker Compose stack
│   ├── web/    # Vue 3 Web 应用
│   └── admin/  # 为后续管理端预留的 workspace
├── packages/
│   ├── components/
│   ├── composables/
│   └── shared/
├── docs/
└── VERSION
```

## 快速开始

前置依赖：

- Python 3.13
- uv
- Node.js 20+
- 通过 Corepack 管理的 pnpm 10.15+
- Docker，或本地 PostgreSQL / Redis / S3-compatible stack

执行前端命令前先启用固定的 package manager：

```bash
corepack enable
```

启动后端依赖和 API：

```bash
cd apps/api
cp .env.example .env
docker compose --env-file .env up --build
```

首次构建完成后，后续正常启动不需要再加 `--build`：

```bash
docker compose --env-file .env up
```

如果希望在后台运行：

```bash
docker compose --env-file .env up -d
```

只有 Dockerfile、依赖锁文件或 Compose 构建配置发生变化时，才需要重新执行 `docker compose --env-file .env up --build`。

默认 Docker 模式不会在后端代码修改后自动重启 API。开发后端时可以启用 reload override：

```bash
docker compose --env-file .env -f docker-compose.yml -f docker-compose.dev.yml up
```

如果不用 reload override，后端代码改动后重启 API 容器即可：

```bash
docker compose --env-file .env restart api-server
```

API 默认监听 `http://127.0.0.1:4000`。

如果构建 PostgreSQL 扩展镜像时 Debian 或 PostgreSQL apt 源不稳定，可以在 `apps/api/.env` 中把以下变量切换到可访问的镜像源或内网源：

```env
APT_DEBIAN_MIRROR=http://deb.debian.org/debian
APT_DEBIAN_SECURITY_MIRROR=http://deb.debian.org/debian-security
APT_POSTGRES_MIRROR=http://apt.postgresql.org/pub/repos/apt
```

例如，中国大陆网络可以把 Debian 源切换为阿里云。这里建议使用 `http://`，因为这个构建步骤发生在安装 `ca-certificates` 之前：

```env
APT_DEBIAN_MIRROR=http://mirrors.aliyun.com/debian
APT_DEBIAN_SECURITY_MIRROR=http://mirrors.aliyun.com/debian-security
```

`APT_POSTGRES_MIRROR` 必须指向 PostgreSQL PGDG apt 仓库镜像，不能填写普通 Debian 镜像。

另开一个终端，回到仓库根目录启动前端：

```bash
cd /path/to/platform
pnpm install
pnpm dev
```

Web app 默认监听 `http://localhost:3000`，并把 `/api` 代理到本地后端。

## 数据持久化与存储安全

默认 Docker Compose 会把核心数据持久化到 `apps/api/.data`：

- PostgreSQL 业务数据：`apps/api/.data/postgres`
- MinIO 文件对象：`apps/api/.data/minio`

停止或重新构建容器不会删除这些文件。只有删除 `.data` 目录，或修改 `.env` 中的数据目录配置后指向了新的位置，才会影响已有数据。

用于团队共享或生产部署时，请替换 `.env` 中的示例密钥，使用稳定的绝对路径或托管 volume，限制 PostgreSQL、Redis 和 MinIO 的网络访问，在反向代理或存储层启用 TLS，并同时备份 PostgreSQL 和对象存储。Redis 默认按缓存/队列基础设施处理，不作为核心业务数据的唯一持久化来源。

Community Edition 当前提供两种托管对象存储 backend：本地/自托管 `minio` 和阿里云 `oss`。使用阿里云 OSS 时，在 `apps/api/.env` 中设置 `STORAGE_BACKEND=oss`，并配置 `OSS_REGION`、`OSS_ENDPOINT`、`OSS_BUCKET` 和 OSS 凭据。

## 开发检查

后端：

```bash
pnpm api:check
```

前端：

```bash
pnpm lint
pnpm --filter @airalogy/web type-check
```

## Public Snapshot 说明

这个 Community Edition 源码树有意排除了：

- 运行时 `.env` 文件和本地专用密钥。
- 本地 TLS 证书和私钥。
- 部署专用脚本和发布 workflow。
- 本地缓存、虚拟环境、日志和构建产物。
- vendored development checkout；后端使用已发布的 `masterbrain` 包。

公开发布前建议执行安全扫描：

```bash
rg -n "PRIVATE KEY|your-private-domain.example" .
find . -name ".env" -o -name "*.pem" -o -name "*.key"
```

推送到 public 仓库前需要人工复核所有命中项。

## 社区

- 贡献指南：[CONTRIBUTING.zh-CN.md](CONTRIBUTING.zh-CN.md) / [English](CONTRIBUTING.md)
- 安全政策：[SECURITY.zh-CN.md](SECURITY.zh-CN.md) / [English](SECURITY.md)

## License

Apache License 2.0. See [LICENSE](LICENSE).
