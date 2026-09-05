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
- 个人或 AI Agent 的执行流水账、工作站专属排障记录、逐次测试报告

可复用的测试场景、验收标准和已知限制应维护在相应测试目录的 README 中。产品变化写入更新日志；临时执行细节保留在经检查的 CI 产物或私有工作记录中，不作为长期公开文档。测试只使用模拟数据，向公开 issue 或 pull request 附加诊断材料前应先检查其内容。

提交 pull request 前运行：

```bash
rg -n "PRIVATE KEY|your-private-domain.example" .
find . -name ".env" -o -name "*.pem" -o -name "*.key"
```
