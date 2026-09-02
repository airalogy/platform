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
- 新增可持久化的 Research Task 与 Run，并在产品内提供任务、指派工作与审批工作台：固定版本化 Research Environment，使用类型明确的 Protocol Action、绑定预览摘要的 `allow / ask / deny` 策略门禁、经过校验的 Record 表单交付与回传和仅追加的来源事件；Aira 可在服务重启后安全续跑，AI 不可用时仍可手工执行，科研结论必须由人明确审核。
- 新增 Knowledge Core 和按范围私有化的 Paper Library：支持 DOI 规范化、无 DOI 候选冲突显式确认、DOI/PDF/URL/BibTeX/RIS 的“解析预览→确认导入”、内容哈希去重但不继承权限的文件存储、真实 PDF 与配额校验、全文检索、集合和 Project 关联、BibTeX/RIS 导出、Knowledge 修订与审核，以及保留来源关系且不扩大原文件权限的 Personal→Project、Project→Lab 发布；文件预览使用短时令牌、读取时再鉴权和仅追加审计，Restricted 内容使用对象级显式授权；可选 Scholar 只作为只读文献候选服务。
- Research Environment 现可固定 Project/Lab 中已审核 Knowledge 的具体修订，并将其作为受边界约束的 Aira 规划上下文；Restricted Knowledge 不进入共享 Task 快照，避免绕过对象级权限。
- 新增保留修订历史的 Personal、Project 和 Lab Research Log：支持结构化进展、会议记录、反思、阻塞和里程碑，按角色控制发布，通过预览后确认保存，并在不可编辑的聚合时间线中呈现真实 Record、Protocol、Knowledge 与 Research Task 活动；现有 Record 热图、日历、导出与历史链接继续保留。
- 新增版本化 DataAsset、按 Research Task 隔离的 Evidence 质量审核和关联 Evidence 且保留修订的科学 Claim；支持预览后确认创建、来源事件留痕、从已完成 Record 待办自动登记已校验 Evidence，并在 Research Result Package 与任务工作台中统一呈现正式科研资产。
- 新增白名单与版本锁定的数字 Research Action：Tool Job 在 Schema 校验后通过可重试的持久化工作器限时执行并保留来源记录；类型化 Wait Event 会暂停 Run，只有经授权、预览确认且满足锁定载荷契约的外部信号才能恢复；AI 关闭时安全回到手工控制。
- Research Task 工作台新增数字 Action 控件，支持预览确认的工具检索、外部结果边界、根据契约生成的信号表单、结果查看、中英文完整状态和产品内使用指南。
- 新增由 Platform 治理的 Aira Action Planner，可在固定版本 Protocol、白名单且固定版本的 Tool、类型化外部 Wait 与结束研究路径之间选择；AI 提案必须经过 Schema 校验、摘要绑定、审批与完整留痕，也能在未预选 Protocol 的纯数字科研任务中运行，不会把 Tool 伪装成 Protocol。
- 新增由 Project Protocol、白名单 Tool 与 Lab 资源定义派生的 Capability Registry；创建 Research Task 时现需明确选择并固定数字能力版本，记录初始 Executor Binding，Aira 和手工 Tool Action 对 Research Environment 之外的能力或已不可用的固定版本必须失败关闭。
- 新增 Lab 治理、保留修订的 Protocol/Tool Executor Binding：只有 Owner/Manager 可通过“预览→确认”配置，每次变更留下不可变审计快照，可限制 Project、自主等级与每次 Run 的 Action 数，按优先级确定性解析，禁止策略必须失败关闭，仅 Platform 内部只读 Tool 可窄范围自动放行；已运行 Run 继续使用固定策略。
- 新增受治理的 Protocol 人工 Executor 直接指派：Lab 管理员可选择 Task 负责人或当前 Project 中具备科研执行权限的具体成员，确定用户会固定到 Research Environment；若其后来离开 Lab 或失去执行权，派发工作时必须失败关闭。
- 新增保留修订的 Lab 人工 Executor 档案，对可用时段、并行工作容量、技能等级、验证状态和资质到期时间留下审计；Protocol Binding 可按当前权限和归一化负载确定性解析已验证技能池，将选定人员和档案证据固定到 Research Environment，并在派发前加锁复核技能、可用性、容量与权限。
- 新增私有 Research 待处理通知，由工作指派和审批请求在同一事务中投影生成，读取时复核当前权限，支持未读导航、显式启用的可选 SMTP 邮件、收件地址脱敏、持久重试和可见投递状态；邮件失败不会阻塞作为权威入口的站内工作流。
- 新增受治理的 Instrument Gateway 配置边界：Lab 管理员可在预览后确认创建网关，仅一次获取或轮换高熵密钥，并管理保留修订的设备指令允许清单；指令固定 Resource 修订、受限输入/输出 JSON Schema、明确风险等级，中高风险必须在设备端确认，变更留下审计并可立即停用。
- 新增端到端 Instrument Job 执行：用户通过“预览→确认”将固定版本的白名单指令绑定已批准设备预约；本地 Gateway 独立鉴权，主动领取签名短租约，在设备端确认后执行、持续心跳并回传经 Schema 校验的结果。租约丢失、执行失败、暂停/取消和显式停止请求均失败关闭到人工检查，绝不自动重试物理操作。
- 新增 Research 资源需求与受治理的 Resource Reservation Action：Task 固定 Lab 资源类型的具体修订，用户通过“预览→确认”预约准确的库存数量或设备时段；Platform 复用现有权限化库存与设备预约账本，可用量变化和时段冲突会失败关闭，待审批设备预约可同步状态，释放过程完整留痕，Task 进入终态时自动归还尚未使用的资源承诺。
- 新增资源感知的 Aira 规划：模型只能请求已固定的资源类型及准确数量或设备时段，由 Platform 确定性选择有权使用的具体候选，始终要求人工审批，在锁内重新校验可用性后才写入权威库存或设备预约账本。
- 新增 Research Task 硬性运行边界：可设置截止时间及绑定币种的预算上限，使用不可变的预留/释放/支出/冲销账本和摘要绑定的“预览→确认”写入；所有执行入口在 API 层检查限额，预算写入耗尽上限时立即暂停，其他超限状态在下一次运行边界安全暂停。
- 新增可追溯的后续 Research Run，用于重试、复现和延续研究：用户先预览再确认一条终态来源 Run，Platform 精确继承其环境并记录来源与结果摘要，既有执行证据保持不变，Task 级限额继续生效，工作台可对比每次 Run 及审核后结果。
- 新增受治理的 Knowledge → Protocol 流程：用户先预览准确的 Knowledge 修订与目标 Project，再由 Aira 生成可编辑草稿；最终确认 Protocol 时重新检查来源访问、范围、Project 权限与修订新鲜度，并原子记录不可变的 Knowledge 修订到 Protocol 版本 provenance，同时不会向只可读取 Protocol 的用户泄露 Restricted Knowledge。
- 新增受 Evidence 门禁的反向流转：只有已校验的 Record/DataAsset Evidence 才能经预览确认生成可编辑的 Project Suggested Knowledge；确认时锁定来源状态，保留不可变 Evidence 快照和修订来源关系，同时保持独立 Knowledge 审核边界与完整非 AI 路径。
- 新增受治理的 Protocol 演进闭环：用户可从 Research Task 中已校验 Evidence 发起固定方法版本的改进建议，经“预览→确认”保留不可变来源快照；只有同时具备科研审批和 Protocol 更新权的人员审核后才能创建可编辑新版本草稿，最终保存会失败关闭地重新校验基线，并精确记录 Evidence→建议→Protocol 新版本来源链，不改写既有版本或活动 Run。
- 在同一受治理流程上新增 Aira 辅助的 Protocol 改进草稿：模型调用不占用数据库事务，返回后重新绑定并校验当前 Task、Protocol 与 Evidence 状态；一小时有效的签名凭据保留可防篡改的模型来源，用户仍须编辑或核对、预览、确认、审核，并创建普通的 Protocol 新版本。
- 新增基于准确 Research Result 上下文的独立建议型 Reviewer Agent：使用独立提示的深度模型检查成功条件、支持与反驳 Evidence、不确定性、缺失对照、失败尝试、风险和可复现性；系统会校验引用的 Evidence，将建议保存为绑定上下文的不可变资产，最终 Task 结论只能由获授权人员复制、编辑并确认。

### 变更

- 将 Platform 顶层页面统一到共享的语义布局宽度体系：主导航与业务工作区默认使用同一套最大 1920px 的有界画布，表单聚焦页和阅读页可按标准档位收窄，不再各自编写页面外壳宽度。
- 将 Platform UI 字体规范集中为共享的标题、正文、标签、元信息、状态、指标和代码语义层级；浏览器、Naive UI 与 UnoCSS 统一使用同一套中英文字体栈，并将首页、Lab、Project、Protocol 与 Record 核心界面迁移到共享体系。
- 将首页改为按角色和真实工作状态组织的任务工作台：可继续当前设备上的 Record 草稿、直接填写最近 Protocol、创建 Protocol 时继承最近 Project，仅根据实际成员关系显示管理快捷入口，并使用统一的有界工作区画布。
- 改进 Record 填写体验，新增当前设备草稿状态、手动保存反馈、必填进度、首个错误定位、包含保存位置和资源影响的确定性提交预览，以及提交后的明确下一步。
- 将 AI 改为实例明确上报的能力：只有模型供应商可用时才显示 Aira 入口；关闭 AI 后不保留空白聊天控件，Protocol 和 Record 的确定性完整流程不受影响。
- 将短信登录改为实例明确上报的能力，支持供应商配置自动检测、显式启用时严格校验、后端强制执行和前端安全回退；Single-Lab 默认关闭且不影响其他短信验证码用途。
- 新增独立且失败关闭的短信注册策略与手机号优先注册流程：后端先校验验证码，再签发经过哈希存储、短期且一次性的注册凭证，最终创建账号时绑定已验证手机号；能力未知或短信供应商故障时不会把公网注册降级为邮箱注册，Single-Lab 默认继续使用不依赖短信的邮箱注册。
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

- 修复窄屏字体挤压和视觉重叠：全局回退行高改为随字号按比例继承，公开落地页及展示卡片迁移到共享语义字体体系，并仅在空间充足时启用双栏布局。
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
