# Community Edition 功能概览

Airalogy Platform Community Edition 是 Airalogy 面向自托管场景的研究数据、Protocol、Record 和 AI 辅助科研协作平台层。它适合希望把大体量科研数据留在本地、内网或自有对象存储中的团队，同时提供 Web 化的 Protocol / Record 工作流。

## 核心能力

- 工作空间模型：管理 Lab、Project、Protocol、Record、文件夹、成员、收藏、评论和基础权限。
- 适合自托管的认证方式：默认使用 email/password 注册和登录，不要求部署方配置短信供应商。
- 以 Protocol 为中心的科研流程：创建和管理基于 AIMD 的 Protocol，记录结构化实验数据，并让 Protocol / Record 数据持续受 schema 约束。
- Protocol Workflow：把多个 Protocol 连接成流程，配置节点、边和起始 Protocol，并通过后端持久化执行状态。
- AI 辅助：配置模型供应商密钥后，通过已发布的 Masterbrain 包提供对话、Protocol 辅助、Record 上下文和 Workflow 支持。
- Protocol Editor 与 Recorder：在浏览器中编辑 Protocol 代码、元数据、变量、文件和记录表单。
- File Storage Bridge：Protocol 和 Record 中保存稳定的 `FileId`，后端再解析到真实文件位置。
- 托管对象存储：默认使用本地/自托管 MinIO，也可以通过配置切换托管上传到阿里云 OSS。
- 自托管启动路径：用 Docker Compose 启动 PostgreSQL、Redis、MinIO 和 API，再通过 Vue Web app 连接本地 API。
- 公开 monorepo 结构：API、Web app、共享类型、组件和 composables 放在同一个仓库中，便于审计、部署和扩展。

## 特色功能

### 稳定文件引用

Protocol 和 Record 应保存 `airalogy.id.file.<uuid>.<ext>` 这类逻辑文件身份，而不是 OSS、MinIO 或中心文件服务器的物理 URL。这样即使部署方以后从 MinIO 切换到 OSS，或接入新的文件中心，历史记录中的文件引用也不需要重写。

### 面向大数据量科研场景

平台把业务元数据和文件本体分开。PostgreSQL 保存用户、项目、记录、权限和 FileId 索引；MinIO 或 OSS 保存真正的文件对象。这避免把大型科研文件直接塞进关系型数据库，也便于做独立备份和存储扩展。

### 多 Protocol Workflow

Community Edition 已包含多个 Protocol 组合成 Workflow 所需的前后端集成。它适合一个 Protocol 的输出值、文件或判断结果会继续进入后续 Protocol 的研究流程。

### 可控的 AI 集成

AI 能力是可选的，取决于部署方配置的模型供应商密钥。平台默认通过已发布的 Masterbrain 包在后端集成 AI 能力，自托管部署不需要默认依赖额外的私有 AI 服务。

### 不强制依赖短信供应商

Community 部署可以选择仅邮箱注册，或强制先完成手机号验证。短信不是本地启动的前置条件；需要手机号实名核验的公网服务应显式启用注册策略。

`SMS_LOGIN_ENABLED` 是后端实例级配置：留空时根据完整的短信供应商配置自动判断；设置为 `false` 时强制关闭短信登录；设置为 `true` 时强制启用，如果配置不完整，API 会在启动时列出缺少的供应商字段并终止。所有地区都需要非空的 `SMS_COUNTRY_CODE_ALLOWLIST` 和阿里云 access key；allowlist 包含中国区 `86` 时，还需要短信签名和验证码模板；包含任何非 `86` 地区时，还需要 sender ID。登录页通过 `/api/instance` 获取最终能力；接口请求失败时会安全回退为仅显示邮箱登录。

`SMS_SIGNUP_REQUIRED` 独立控制注册流程。Community 部署留空时同样根据短信供应商配置自动判断；设置为 `false` 时保留仅邮箱注册；设置为 `true` 时强制验证手机号，且供应商配置不完整会导致 API 启动失败。需要手机号实名核验的 Airalogy 公网云部署应显式设置 `SMS_SIGNUP_REQUIRED=true`。注册页会先校验手机验证码，后端签发一个 30 分钟有效、只能使用一次的注册凭证，然后才填写邮箱、密码、用户名和显示名；最终创建账号时使用凭证中绑定的手机号，不信任浏览器另行提交的手机号。

当 Web 无法从 `/api/instance` 取得 `sms_signup_required` 时，注册流程采用失败关闭策略：页面显示注册服务暂不可用，不会自行假定允许邮箱注册。短信供应商运行时故障也只会导致验证码发送或验证失败，不会降级为邮箱注册。与此同时，只要 `SMS_SIGNUP_REQUIRED=true`，后端始终拒绝没有有效手机号注册凭证的注册请求。

修改任一后端配置后都需重启 API。本功能首次部署时需要重新构建包含登录和注册能力判断代码的 Web；此后仅切换配置值不需要再次构建 Web。`SMS_LOGIN_ENABLED` 只控制短信登录，`SMS_SIGNUP_REQUIRED` 只控制手机号优先注册；两者都不会禁用短信重置密码或修改手机号。

## 默认包含

- FastAPI 后端
- Vue 3 Web 应用
- PostgreSQL、Redis 和 MinIO Docker Compose stack
- Community 初始 schema 的 Alembic migrations
- 文件上传、外部文件登记、FileId 解析和下载 API
- Protocol Workflow API
- 中英文公开文档
- 后端 smoke check 和前端 lint/type check 的 GitHub Actions

## 相关文档

- [文件存储桥接](./architecture/file-storage-bridge.md)
- [自托管架构](./architecture/self-hosted-architecture.md)
- [前端开发说明](./development/frontend.md)
- [English documentation](../en/README.md)
