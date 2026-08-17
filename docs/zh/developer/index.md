# Platform 开发

Airalogy Platform 是一个 monorepo，包含 FastAPI 后端、Vue Web 应用、共享包、部署资源、测试和本统一文档。修改代码前应阅读仓库 `AGENTS.md` 以及相关子系统文档。

## 仓库结构

| 路径                | 责任                                                             |
| ------------------- | ---------------------------------------------------------------- |
| `apps/api`          | FastAPI API、数据库模型与迁移、后台任务、存储和执行器集成。      |
| `apps/web`          | 登录后的 Vue 产品体验和部署感知导航。                            |
| `packages/*`        | 共享 UI、composable、类型、国际化和跨界面契约。                  |
| `deploy/single-lab` | 面向生产的单实验室镜像、代理配置、初始化、校验、备份与升级工具。 |
| `docs`              | Platform 公开站和镜像内本地站的唯一文档源码。                    |

## 本地开发流程

使用仓库指定的包管理器和运行时版本。按锁文件安装依赖，先运行最小相关测试，再运行受影响子系统要求的广泛检查。国际化生成类型应通过仓库脚本生成，不应手工修改。

文档开发命令：

```bash
pnpm docs:dev
DOCS_BASE=/platform/ pnpm docs:build
```

`DOCS_BASE` 是唯一的基础路径输入。GitHub Pages 公开镜像使用 `/platform/`，正式 Platform 部署使用同源 `/docs/`。根目录的 `pnpm dev` 和 `pnpm build` 会先在 Web 公共资源中生成与当前版本匹配的文档。

## 架构与契约

- [前端开发](../development/frontend)：JavaScript workspace 和 Web 构建。
- [文件存储桥接](../architecture/file-storage-bridge)：稳定文件身份和存储解析。
- [自托管架构](../architecture/self-hosted-architecture)：服务与数据位置。
- [访问控制](../access-control)：角色、授权、继承和后端执行。

应优先维护单一共享契约，避免各界面重复实现。权限、校验和运维决定应由确定性代码负责；AI 生成的叙述不能暗中改变这些决定。

## 文档边界

产品行为、公开架构、部署步骤和更新日志属于本仓库。客户服务器细节、账号密钥、私有网络拓扑、SLA 和交付记录不得进入公开仓库。帮助中心按角色显示卡片只用于优化导航，不能作为公开文档文件的权限控制。

调整导航时应保持既有公开文档路径可用。旧的独立文档仓库只作为迁移参考保留到新站上线；是否归档应单独决定。
