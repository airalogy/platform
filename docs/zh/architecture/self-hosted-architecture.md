# 自托管架构

Airalogy Platform Community Edition 面向团队和机构自托管部署。对于大体量科研数据，推荐把业务平台、对象存储和数据接入链路放在靠近数据的位置运行，避免把所有原始文件默认上传到公网云端。

## 设计原则

- `Airalogy Platform` 负责账号、Lab、Project、Protocol、Record、权限、搜索和协作。
- 原始大文件优先进入本地对象存储，例如自托管 MinIO 或机构已有对象存储。
- 数据库保存业务元数据、权限关系、索引字段和对象引用，不直接承载大文件本体。
- AI 与自动化能力通过配置的模型服务和已发布的 Airalogy / Masterbrain 包接入。
- 公开版默认提供清晰的本地部署路径，企业级多站点同步、复杂审计和专有存储连接器可以在此基础上扩展。

## 默认本地拓扑

```text
Browser
  -> Airalogy frontend
  -> Airalogy backend
  -> PostgreSQL
  -> Redis
  -> MinIO
```

Docker Compose 默认启动 PostgreSQL、Redis、MinIO 和后端服务。前端可以在本机通过 Vite 开发服务器连接后端。

## 数据持久化与安全

默认本地部署会通过 `.env` 中的路径把数据持久化到 `apps/api/.data`：

- `POSTGRES_DATA_PATH=./.data/postgres`：保存 PostgreSQL 数据库文件。
- `MINIO_DATA_PATH=./.data/minio`：保存 MinIO 对象存储文件。

容器停止、重启或重新构建不会自动删除这些目录。部署方应把 `.data` 视为真实业务数据目录，不应把它当作临时缓存处理。

面向团队或机构部署时，建议至少满足以下要求：

- 使用稳定的绝对路径、专用磁盘或托管 volume 保存 PostgreSQL 和对象存储数据。
- 定期备份 PostgreSQL 数据库和对象存储 bucket；只备份数据库无法恢复 FileId 指向的文件本体，只备份对象存储也无法恢复权限和业务索引。
- 替换 `.env.example` 中的所有示例密钥和默认密码，包括 `SECRET_KEY`、`AES_KEY`、`INNER_API_KEY`、数据库密码和对象存储凭据。
- 不把 PostgreSQL、Redis、MinIO 管理端口直接暴露到公网；公网访问应经过反向代理、TLS、认证和网络访问控制。
- 对备份文件、对象存储 bucket 和数据库 volume 配置独立访问权限，避免应用账号、运维账号和备份账号共用同一组长期凭据。
- 制定恢复演练流程，确认数据库备份、对象存储备份和 `.env`/密钥材料能够在新机器上恢复为可用系统。

Redis 默认用于缓存、队列或短期状态，不应作为核心业务数据唯一来源。如果部署方把任务队列或异步状态做成强依赖，应额外配置 Redis 持久化和备份策略。

## 大文件策略

科研原始文件可能非常大，直接经公网或应用后端中转会增加带宽、成本和稳定性风险。推荐策略如下：

- 浏览器上传适合轻量文件和常规附件。
- 大文件应尽量在局域网内写入对象存储。
- 后端通过 `airalogy_files` 保存 FileId 到 storage backend、namespace、object key 或 external URI 的映射，以及校验信息、权限关系、预览引用和分析结果引用。
- 需要跨站点协作时，优先同步元数据、预览和结果；原始文件按策略异步同步或按需调取。

Protocol 和 Record 中保存的是稳定的 `airalogy.id.file.<uuid>.<ext>`，不是 OSS 或中心服务器的物理 URL。具体设计见 [文件存储桥接](./file-storage-bridge.md)。

## 权限边界

Community Edition 的核心权限边界由 Lab、Project、Protocol 和 Record 组成。部署方应同时配置：

- 强随机 `SECRET_KEY`、`AES_KEY` 和 `INNER_API_KEY`
- 私有网络或反向代理访问控制
- 对象存储 bucket 权限
- 数据库和 Redis 访问权限
- 备份、日志保留和密钥轮换策略

## 扩展方向

公开仓库保持平台主体代码清晰可部署。后续可以在不改变核心数据模型的前提下增加：

- 机构级身份提供商集成
- 多站点接入与同步代理
- 大文件断点续传与本地采集工具
- 细粒度审计和合规报表
- 专有对象存储、HPC 或仪器连接器
