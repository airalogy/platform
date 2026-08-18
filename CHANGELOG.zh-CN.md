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
- 新增按权限范围导出原始 Records：Lab Owner 可导出实验室，Project Owner/Manager 可导出项目或 Protocol；支持固定快照的后台任务、`.aira`、JSONL、单 Schema CSV、可选修订历史、附件去重、实验室级不可变审计、7 天下载、站内完成通知以及导出历史与重新生成。
- Protocol Editor 新增无代码 Aira 工作流：用户可用自然语言描述实验需求，生成并预览结构化 Protocol，再通过对话继续讨论或修改。普通问题只返回回答而不改动文件；安全修改会立即应用，并提供自然语言摘要、行内或左右可视化差异与撤销；校验警告和文件删除仍需人工确认。
- 新增推荐的“AI 帮助撰写 Protocol”创建方式，可在当前 Lab 与 Project 上下文中直接打开现有 Aira 草拟流程。
- 新增端到端发布与部署身份机制：运行时版本自报、Alembic revision、四个核心镜像的不可变清单、Tag 触发发布、持久部署历史、不透明部署 ID 和脱敏运维支持包。
- 新增 Community Edition 公开发行中的商标与客户数据边界说明。
- 新增统一、使用 Airalogy 品牌标识的双语 VitePress 文档体系，同时用于公开站与单实验室镜像内的版本匹配文档；产品内新增按部署方式和角色展示使用手册、实验室管理、自托管运维与托管支持入口的帮助中心。

### 变更

- 将 Platform UI 字体规范集中为共享的标题、正文、标签、元信息、状态、指标和代码语义层级；浏览器、Naive UI 与 UnoCSS 统一使用同一套中英文字体栈，并将首页、Lab、Project、Protocol 与 Record 核心界面迁移到共享体系。
- 将首页改为按角色和真实工作状态组织的任务工作台：可继续当前设备上的 Record 草稿、直接填写最近 Protocol、创建 Protocol 时继承最近 Project，仅根据实际成员关系显示管理快捷入口，并为宽屏提供最大 1920px 的有界工作画布，不拉伸其他产品页面。
- 改进 Record 填写体验，新增当前设备草稿状态、手动保存反馈、必填进度、首个错误定位、包含保存位置和资源影响的确定性提交预览，以及提交后的明确下一步。
- 将 AI 改为实例明确上报的能力：只有模型供应商可用时才显示 Aira 入口；关闭 AI 后不保留空白聊天控件，Protocol 和 Record 的确定性完整流程不受影响。
- 将 Protocol 创建入口整理为推荐的 Aira/模板方式，以及复用、Hub、`.aira`、ZIP 和从头编辑等更多方式，并保留当前或最近 Project 上下文。
- 将公开版版本号与发布历史重置为 Community Edition 初始发布。
- 将公开仓库整理为产品级 monorepo：`apps/api`、`apps/web`、`apps/admin` 与共享 `packages/*`。
- 将持久化 workflow 领域模型从 `ResearchWorkflow` 改名为 `ProtocolWorkflow`，公开版初始 schema 表名同步为 `protocol_workflows`。
- 将数据库初始化整理为单一初始 schema migration。
- 从公开源码树中排除生成的 API 产物、本地缓存、日志、证书、环境文件和数据库 dump 文件。
- Platform 更新为 `masterbrain==0.11.0` 以及正式发布的 `@airalogy/masterbrain-client` / `@airalogy/masterbrain-vue` 包。Protocol 草稿使用 Masterbrain 单文件生成契约，AI 编辑契约、风险处理、安全应用与撤销逻辑和 Diff 渲染则统一由 Masterbrain 共享包提供，Platform 不再维护重复的智能与 UI 基础设施。
- 将 `@airalogy/masterbrain-vue` 更新到 `0.2.0`，变更状态、审核、Diff、文件与风险等共享 UI 文案改由包内置的响应式中英文国际化提供。Platform 只传入当前语言，并保留 Aira 产品文案和弹窗外壳文案。
- 将 API 封装包更新为 `airalogy-engine==0.0.9`，将浮动的 Airalogy Engine 镜像替换为官方 `0.16.0` 多架构不可变摘要，同时支持 `linux/amd64` 和 `linux/arm64`；隔离 Protocol Executor 镜像也可配置并随 Platform 发布统一版本。
- 将已被上游撤回的 `numpy==2.4.0` 构建依赖替换为兼容的补丁版本 `2.4.6`，同步用于 API 环境与隔离 Protocol Executor。
- 完整 Web 生产构建已超出原 4 GB 限额，因此将默认构建 heap 提高到 6 GB。

### 修复

- 改进 Protocol 列表行的响应式布局，使长标题、归属上下文、次级创建信息、指标和操作保持清晰视觉层级，并在窄屏自然换行，不再被挤进一行造成横向溢出；聚合列表继续展示非敏感的收藏与复用指标，Record 操作仍按权限显示。
- 修复浏览器继续使用无关的旧站点图标、未显示 Airalogy favicon 的问题。
- 为聚合 Protocol 列表补充所属 Lab 与 Project 路径，使“我的协议”和用户资料页保留工作空间上下文。
- 修复 Protocol、Project、Lab 与 Group 描述已在三行预览中完整显示时，仍出现无实际展开内容的“展开”操作。
- 修复 AI Protocol 变更审查中的 Diff 编辑器塌缩成一条细缝的问题，并将 Aira 侧栏说明整理为更清晰的助手卡片。
- 修复 Protocol 生成后进入 Aira 对话时错用通用窄侧边栏宽度、导致标题、消息和输入区被过度挤压的问题。
- 修复实验室资源库因弹窗根节点与路由过渡不兼容，首次通过客户端导航进入时无法渲染的问题。
- 修复记录日记提交热图无法完成绘制且加载指示器持续显示的问题。
- 保持隔离 Protocol 执行器与后端的 Airalogy 依赖版本一致，避免执行器模块变化后 `.aira` 导入失败。
- 修复非 UTC API 主机上的 Record 导出快照时间偏差，并确保 MinIO 与 OSS 预签名下载保留用户看到的文件名。
