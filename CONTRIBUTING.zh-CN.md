# 贡献指南

[English](CONTRIBUTING.md)

感谢你为 Airalogy Platform 做贡献。

## 开发原则

- 保持 Community Edition 作为自托管产品可用。
- 不要把特定部署环境假设加入公开默认配置。
- Enterprise-only 能力应通过明确扩展点接入，而不是形成 fork。
- 优先集成成熟基础设施，例如 PostgreSQL、Redis、MinIO、OIDC 和 S3-compatible storage。
- 前端用户可见文案应通过现有 i18n 系统维护。

## 本地检查

后端：

```bash
pnpm api:check
```

前端：

```bash
corepack enable
pnpm install
pnpm lint
pnpm --filter @airalogy/web type-check
```

## 公开安全要求

不要提交：

- `.env` 文件
- 私钥或证书
- 生产环境凭证
- 部署环境专用 endpoint
- 生成的缓存、日志或构建产物

提交 pull request 前运行：

```bash
rg -n "PRIVATE KEY|your-private-domain.example" .
find . -name ".env" -o -name "*.pem" -o -name "*.key"
```
