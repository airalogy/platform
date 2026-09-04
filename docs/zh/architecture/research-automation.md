# AI 科研自动化架构

## 状态

本文是 Airalogy Platform 科研自动化的架构契约。实现必须保持本文中的对象边界、权限边界和兼容原则；未实现的能力必须明确标记，不得以对话或静态界面模拟已完成的执行。

## 产品目标

Airalogy Platform 的长期形态是一个 AI-native Research OS：用户给出科研目标和成功标准，Aira 在真实的科研环境中规划、执行、等待、验证和重规划，最后交付可追溯的研究结果包。

AI 是智能编排层，不是系统记录或权限系统。Platform 仍是所有任务、方法、执行、证据、审批和审计的确定性控制面。AI 关闭或暂时不可用时，人员仍能创建任务、安排方法、提交 Record/DataAsset、验证结果并完成研究。

## 核心分层

1. **体验层**：`Research Task Workbench` 和 Aira 意图入口。
2. **智能层**：AIRA Method 负责目标理解、策略、计划、解释和重规划。
3. **运行时层**：`Research Run`、`Research Action`、事件、队列、并发、重试、暂停与恢复。
4. **方法与能力层**：`Protocol`、`Workflow`、Tool Connector 和 Executor Binding。
5. **科研资产层**：Paper、Record、DataAsset、Evidence、Claim、Knowledge 和 Report。
6. **运营资源层**：People、Equipment、Inventory、Sample、Budget、Compute 和 External Service。
7. **治理层**：Permission、Approval、Policy、Risk 和 Audit。

## 核心对象

### Research Task

`Research Task` 是用户面向的顶层对象，表示一个有边界的科研目标。它至少包含：

- 目标、成功标准和停止条件；
- Lab/Project 范围、负责人和参与者；
- 自主等级、资金/时间限额和适用策略；
- 一个或多个 `Research Run`；
- 最终科学结果，而不只是运行成败。

Aira 意图入口是从目标到 Task 的转换器，不是特权写入通道。Platform 会先根据所选 Project、当前用户和自主级别解析最小权限目录。模型只能看到当前可读的已审核 Knowledge，以及具有可执行且非禁止 Binding 的 Capability；返回值只能包含目录中的准确标识符、有边界的 Task 字段、假设和风险提示。模型调用期间不保持数据库事务。生成后 Platform 会重新解析每个已选对象和 Binding；权限、版本、可用性或策略的任何变化都会失败关闭。结果仍是可编辑的 `ResearchTaskDraft`，必须进入常规“预览→确认”流程；它不会创建 Task、审批、预留、订单、Compute Job 或仪器指令。关闭 AI 时，完整手工 Task 路径不受影响。

### Research Run

`Research Run` 是一次可恢复的执行，对应一个计划分支、复现、重试或延续研究。它固定当次 `Research Environment` 快照、Protocol 版本和每次计划修订，通过持久事件恢复，不依赖浏览器会话或一次性 AI 请求。

一次 Run 进入终态后，获授权用户可先预览，再以它为来源创建新 Run。Platform 会精确复制来源 Run 的 Research Environment，在 `run_origin` 中记录来源 Run、环境摘要和结果摘要，开启新的计划来源链，同时不改写任何既有 Action 或科研资产。因此重试和复现不会静默采用更新的 Protocol、Knowledge、Tool、执行策略或资源定义版本。当前运行时一个 Task 同时只允许一条非终态 Run，Task 级截止时间和预算账本会继续约束每次 Run。

### Research Action

`Research Action` 是编排层的统一包装，但不是一个吞掉全部业务语义的 JSON 表。共享状态、依赖、幂等键、预览摘要、执行人和时间轴，具体语义由类型化实现承担：

- Protocol Run
- Tool Job
- Human Work Item
- Instrument Job
- External Service Job
- Approval Request
- Resource Reservation
- Wait Event

Protocol Run、Human Work Item、Tool Job、Instrument Job、External Service Job、Resource Reservation 和 Wait Event 已使用这套生命周期。未来的独立审批请求类型会在对应 Executor 接入时沿用同一边界。

Tool、Instrument、External Service、Resource 和 Wait 的类型化结果会追加到 Run 持久 AIRA 状态中有上限的结果通道。下一 Action 规划器和旧 AIRA Method 都会将这些通道作为不可信的科研证据读取。这既保留执行输出、Record 与 Protocol 的语义边界，也避免后续规划和结论丢失真实运行结果。

### Protocol 与 Capability

`Protocol` 是可重复、有科学意义、可版本化的方法，应定义输入、输出、证据要求和验证规则。它可表示实验、文献综述、计算、数据处理、分析、评估或报告方法。

`Capability` 不取代 Protocol。Capability Registry 是根据 Protocol、工具、人员技能、设备、外部服务、资源、可用性和策略组合得到的当前能力视图，不是第二套方法来源。

Platform 的第一版 Registry 由 Project 当前 Protocol 版本、实例白名单数字工具和 Lab 当前 Resource Type 修订派生。创建 Research Task 时必须明确选择 Protocol 和 Tool 能力，并在 `airalogy.research-environment.v2` 中固定来源版本及初始人员或 Platform Worker 执行绑定。Aira 和手工控件都不能执行快照之外的 Tool，版本已不可用时也必须失败关闭。Resource Type 只作为可发现的执行需求，不被伪装成可执行方法；具体预约和消耗在 Action 执行时解析。

Lab Owner 和 Manager 可以在 Project Research 中增加指定版本的 Executor Binding 覆盖策略。Protocol Binding 可解析为未来的 Task 负责人，也可直接指定当前 Lab 中对该 Project 拥有科研执行权的成员，或使用受治理的技能池。人工 Executor 档案是保留修订的 Lab 记录，包含可用时段、最大并行工作量，以及带等级、管理验证和可选到期时间的技能声明。技能池只接受具备全部必需技能、已验证且未过期、当前可用，并拥有 `research.run` 权限的人员；再依次按归一化活跃工作量、活跃项数和稳定用户 ID 选择。选定的人员、档案修订、匹配技能证据、工作量、容量和摘要都会固定到 Research Environment。

每次 Binding 和档案变更都需先预览再确认，并追加不可变审计快照。Binding 可要求审批、禁止使用，或仅放行 Platform 内部只读 Tool；也可限制 Project、自主等级、每次 Run 的 Action 数和人员最低技能等级。之后的策略或档案修改不会改写正在运行的 Run。正式派发人工工作前，Platform 会加锁并复核固定人员的当前 Lab 成员身份、`research.run` 权限、可用性、已验证资质和剩余容量；权限撤销、资质过期或容量耗尽时均失败关闭。不使用 AI 时，仍可手工选择 Task 负责人或具体成员。

需要处理的交接会由仅追加的 `work_item.assigned` 与 `approval.requested` 事件在同一数据库事务中投影到私有 Research 待处理通知。开始或完成工作、作出审批决定、取消任务或重新指派时，会在同一事务中关闭对应的过期待办。站内通知是权威提醒路径，读取时仍会按当前 Research 权限过滤，已经离开的成员不能通过旧通知查看任务上下文。可选 SMTP 通道使用独立的持久投递记录和可重试后台任务；真正发送前会再次检查待办仍未解决、当前 Research 权限和用户现用邮箱，工作已处理、权限或身份已变化时均跳过旧投递。API 对收件地址脱敏，确定性 Message-ID 可降低重复邮件的展示概率，最终投递失败会明确显示，但不会改变或阻塞原工作项。邮件默认关闭，也不承载任何权限或执行授权。

下列内容不应被强制建模为 Protocol：

- Paper、Record、DataAsset、Knowledge、Claim、Report 等资产；
- 任务、通知、审批、预约、等待、审计和支付；
- 人员、设备、库存、样品、预算和计算资源。

系统支持渐进式形式化：`Ad-hoc Action → Saved Preset → Protocol Draft → Reviewed Protocol → Validated SOP`。

## 科研状态与运行状态

规划同时读取两类状态：

- **Epistemic State**：科学问题、假设、文献、Record、Evidence、Claim、Knowledge 和不确定性。
- **Operational State**：Protocol、人员、设备、库存、样品、预算、计算、权限、审批和可用时间。

`Research Environment` 是一个版本化快照，描述某次 Run 允许使用的方法、执行绑定、数据/知识、资源和策略。环境变化通过事件使 Run 恢复或重规划，不允许 Aira 假设某个资源存在或当前可用。

## 执行循环

```text
Research Task
  → 解析目标与成功标准
  → 生成 Research Plan Version
  → 解析可用 Research Environment
  → 提出下一个 Research Action
  → 权限/策略/资源/预算门禁
  → 自动执行、等待审批、等待人员或等待外部事件
  → 产生 Record/DataAsset/Evidence
  → 确定性验证
  → 更新科研状态与运行状态
  → 重规划或结束
```

目标计划是可版本化的自适应 DAG，而不是只能向前的页面步骤。当前运行时先交付有边界的并行前沿：Aira 可同时提出 2–4 个相互独立的只读 Tool Action，每个分支独立固定版本并接受治理，Run 会停留在一个持久屏障上，直到全部分支结束。通用依赖执行、并行物理工作和任意多 Agent 图仍是受控的后续能力，不能仅因数据库中存在依赖表就宣称已实现。修改目标、成功标准、预算或高风险路径必须产生新的计划版本并重新确认。

## 人机协作

物理实验是一个异步执行器，不是 AI 流程中的特例：

1. Aira 选择已发布的 Protocol 版本并生成参数草稿。
2. Platform 解析具体执行人、资源和审批要求。
3. Platform 创建 Human Work Item，持久化指令和提交契约，然后将 Run 转为等待。
4. 人员在确定性 Protocol/Record 界面执行并提交 Record/DataAsset。
5. API 验证权限、Protocol 版本、Schema、资源消耗和提交完整性。
6. 成功事件唤醒 Run，AIRA 根据真实证据继续。

邮件、Slack 或其他渠道只是通知方式，Human Work Item 才是权威状态。

## 治理与自主等级

每类 Action 策略使用 `allow / ask / deny`：

- `allow`：在明确的能力和限额内自动执行；
- `ask`：生成影响预览，用户确认后执行；
- `deny`：在当前环境中不允许，任何“全自动”开关都不能覆盖。

面向用户的自主等级为 Assisted、Bounded Autopilot 和 Autonomous within Policy。自主权按 Lab + Capability + Executor 分别授予，必须经过回放、影子运行和评估，不存在一次打开的全局无限权限。

重要写入使用统一契约：

```text
表达目标 → 生成草稿 → 预览影响 → 用户确认
  → 确定性执行 → 返回结果、存放位置和下一步
```

审批必须绑定预览版本或摘要哈希；源数据变化后原审批失效。权限、资源和策略校验全部在 API 层执行，不以前端隐藏替代。

P0 采用有意的失败关闭策略：手工创建的 Protocol Action 只在确认确定性预览后记为 `allow`；Aira 提议的人工 Protocol Action 在所有自主级别下都是 `ask`。批准只激活当前摘要绑定的 Action，然后才创建 Human Work Item；拒绝会取消该提议、记录原因并请求重新规划。更广泛的自动 `allow` 规则必须等 Lab 策略、资源、风险和预算控制完成后才能开放。

## 科学可靠性

运行状态与科学结果必须分离。一个正确执行的实验可以否定假设或不确定；负结果不是执行失败。

- 执行状态：proposed、approved、queued、running、waiting、validating、completed、failed、cancelled。
- 科学结果：supports hypothesis、contradicts hypothesis、inconclusive、unexpected、not applicable。
- 任务终态：goal met、goal not met but conclusive、inconclusive、blocked by missing capability、stopped by budget/time/safety、cancelled、execution failed。

Aira 不能自行宣布成功。验证层必须记录 Schema/QC、Protocol 符合性、校准、对照、样本量、统计阈值、重复、偏差和失败尝试。

人员确认完成 Task 前，可选的独立 Reviewer Agent 会通过与执行 Agent 分离的深度模型提示，审查当前 Task、最新 Run、Action 账本、Result Package 和科研资产组成的准确上下文。模型调用期间不保持数据库事务；返回后 Platform 会重新检查 Task 修订和完整上下文摘要。引用上下文外 Evidence 的输出会被拒绝，不可变建议会分别保存支持证据、反证、不确定性、缺失检查和风险。Reviewer 只提供建议，不能审批、改写或完成 Task；Task Owner 或科研审批人必须主动把建议复制为可编辑审核草稿，可修改任何字段，并作为最终科学判断的记录责任人。AI 关闭时，普通人工审核路径不受影响。

Aira 也可以根据用户明确选择的 Task 已校验 Evidence，综合生成一条可编辑 Suggested Claim。严格输出必须把每一项 Evidence 恰好评估一次，标明为支持、反驳或上下文，解释关系，把判断边界限定在来源可支持的范围内，并保留重要不确定性。模型调用不持有数据库事务；返回后 Platform 锁定并重新校验 Evidence 及其引用的资产版本，上下文变化就拒绝结果，再签发同时绑定用户、Task、准确生成内容和来源摘要的一小时凭据。预览和确认会再次校验同一上下文，生成 ID 唯一约束防止重放。用户可在确认前编辑判断、置信度、不确定性和 Evidence 关系，原始生成内容仍保留在不可变来源中。最终仍是普通 Suggested Claim，只能由另行授权的人员审核。AI 关闭时，手工创建和审核 Claim 仍可完整使用。

## 证据与结果包

AIRA 的阶段性和最终结论不只保存为 Markdown。结构化状态至少包含：

- Claim 及其置信度；
- 支持、反驳和不充分的 Evidence；
- Record、DataAsset、Protocol 版本和执行人的 provenance；
- 异常、偏差、不确定性和未解决问题；
- 成功标准评估与建议的下一步。

最终交付是 `Research Result Package`，包含摘要、目标状态、Claim/Evidence、固定的 Protocol 版本、Records、DataAssets、Knowledge 候选、Protocol 改进建议、失败尝试、验证报告、未解决问题、预算状态和可复现清单。Aira 自动执行与完全手工执行使用同一结果包构建器，不会因 AI 关闭而丢失完整交付物。

只有最终人工审核才会封存结果包。Platform 为每次 Run 保存一份仅追加快照，记录准确 Task 修订、审核人、定稿时间和规范 SHA-256 摘要；读取已封存快照时会重新校验摘要。引入封存机制之前产生的历史结果包仍可读取和导出，但会明确标记为“未封存”，不伪装成不可变快照。Task 工作台可查看完整快照，并导出可携带的 JSON 或双语 Markdown；两者都是同一结构化结果包的视图。

## Knowledge、Log 与三个循环

- `Research Log` 记录过程中发生了什么，合并不可变系统事件和有修订历史的人工日志。
- `Knowledge` 是经整理、可复用、可审核和可派生的认识，Paper Library 是 Knowledge 的文献视图。
- Record 仍是一次 Protocol 执行的结构化证据，不转换为普通日志。

Knowledge 到方法的流转必须显式并固定版本。获授权用户先预览准确的 Knowledge 修订和目标 Project，再进入 Aira Protocol 生成器；Knowledge 正文通过正常权限接口读取，不进入 URL。保存生成结果时，Platform 会重新检查来源可见性、范围、目标 Project 写权限和修订新鲜度，然后原子写入不可变的 `Knowledge revision → Protocol version` 关系与来源快照。Personal Knowledge 可用于用户有权写入的 Project；Lab 与 Project Knowledge 只能留在各自 Lab 或 Project。已归档、已被取代、过期或不可访问的来源一律失败关闭。Protocol 响应只向同时有权读取两侧资产的人展示来源，避免 provenance 泄露 Restricted Knowledge。

已完成的结构化 Action 输出有独立的晋升边界。获授权用户选择已完成 Action，预览准确输出摘要后确认创建待审核 Evidence。Platform 会锁定 Action，封存一份只可追加的快照，其中包含 Task、Run、Action 修订、类型、输出和规范 SHA-256 摘要；读取及结果包导出都会验证该摘要。在人员审核待定 Evidence 前，系统不会将该输出认定为科学上有效。这使 Tool、Instrument、Resource、Wait、External Service 和 Compute 结果可成为可审计的科研来源，同时不把它们伪装成 Record，也不静默视为事实。

反向流转必须经过 Evidence 门禁。具有 Knowledge 写权限的 Project 成员只能选择已校验、且指向准确 Record、DataAsset 版本或不可变 Action 输出快照的 Evidence；在预览保存位置和来源集合后，可创建 Project 范围的可编辑 Suggested Knowledge。确认时会锁定并重新校验每条 Evidence，将预览摘要与审核状态和不可变来源版本绑定，同时保存来源快照和准确的 `Evidence → Knowledge revision` 关系。该结果仍是候选认识，只有通过独立 Knowledge 审核权限才能成为组织已采纳的 Knowledge。待审核或已拒绝 Evidence、外部链接、Paper 及既有 Knowledge 都不能从该路径进入，且整个流程不依赖 AI。

Protocol 演进使用独立的方法改进门禁。获授权用户选择已固定到 Research Task 的 Protocol 版本，再选择已校验的 Record、DataAsset 或不可变 Action 输出 Evidence；系统会先预览准确版本、Evidence 快照、科学依据和建议改动，然后创建待审核的 `Protocol Improvement Proposal`。AI 可用时，Aira 可以基于同一固定上下文生成可编辑的标题、依据和修改建议。模型调用期间不保持数据库事务；模型返回后 Platform 会重新校验来源，并签发同时绑定用户、Task、Protocol、上下文和有效期的凭据。用户预览和确认时会再次验证签名凭据与准确生成快照，而且一个生成 ID 只能确认一次。用户仍可编辑内容，来源记录为 Aira 辅助，而不是 AI 审核。同时具备科研审批权和该 Protocol 更新权的人员采纳建议后，现有 Protocol Editor 才会进入可编辑的新版本草稿。最终保存时会重新锁定建议和 Protocol，确保已审核修订未变、未被使用，且 Protocol 没有超过所固定的基线版本。保存成功会生成普通的更高 Protocol 版本，将建议标记为已应用，并记录准确的 Evidence → 改进建议 → Protocol 新版本来源链。既有版本和正在运行的 Run 固定环境不会被改写。AI 关闭时，完整手工路径仍然可用。

系统保持三个独立但互相连接的循环：

1. 研究执行：Protocol/Action → Record/Evidence → 阶段状态 → 下一个 Action。
2. Protocol 演进：Records/DataAssets → 改进建议 → 专家审核改进意图 → 可编辑 Protocol Draft → 校验后的新版本/SOP。
3. Knowledge 演进：Runs/Evidence → Suggested Knowledge → 审核 → Project/Lab Knowledge。

Aira 只能提交改进草稿或 Suggested Knowledge，不得静默修改已发布 Protocol，也不得在正在运行的 Run 中自动切换版本。

## 资源、设备与外部服务

规划阶段预留资源，执行阶段确认消耗或释放。Task 会把选定 Lab 资源类型的具体修订固定为需求，但不会把不断变化的可用量误当成方法的一部分。手工 Action 由用户选择并预览确认具体资源；Aira 只能请求已固定的资源类型、准确库存数量与单位，或设备时段，再由 Platform 在请求人的权限范围内确定性选择具体候选并始终请求审批。批准时会在权威账本内重新校验资源修订、访问权、余额版本或设备时段，状态过期就拒绝执行。Resource Reservation 与 Research Action 一一关联，现有库存和设备预约账本仍是权威来源。余额版本变化、库存不足、Schema 漂移、预约冲突以及未获授权的 Restricted 资源都会失败关闭。设备策略可让 Action 再次等待资源管理员审批；状态同步会从权威预约结果恢复 Run。显式释放以及 Task 进入终态都会归还尚未使用的资源承诺，并留下审计事件。

Task 还可固定截止时间和单一币种的预算上限。预算变化必须通过绑定 Task 修订与预览摘要的“预览→确认”，追加不可变的预留、释放、支出或冲销记录；预留与实际支出分开计算，不能通过改写历史抹去原有承诺。Platform 会在确认写入时，以及创建每个新 Protocol、Tool、Wait、Resource、Instrument、External Service 或 Compute Action 前重新计算账本。预览过期、币种不符、余额为负或超预算都会失败关闭。预算写入使已承诺金额耗尽上限时，当前 Run 会立即暂停；从其他入口发现截止时间或预算已到边界时，会在下一个运行边界安全暂停，并明确记录 `stopped_time` 或 `stopped_budget`。具备权限的用户可通过同样绑定修订和摘要的流程整体替换当前运行边界；旧值、新值和原因会写入仅追加事件，账本产生记录后不能更换或移除预算币种。边界修订绝不会自动恢复已暂停 Run，继续执行仍是单独的显式状态迁移。

库存记录批次、失效期、位置、容器、数量和样品谱系；设备记录能力、排期、校准/维护状态、风险和输出格式。预算区分总额、预留和实际支出，超阈值必须审批。人员执行受技能/资质、可用时间、工作量、权限和审批职责限制。

Platform 不必取代完整 ERP/LIMS。小型 Lab 可使用内置最小模块，成熟组织可连接既有系统；Platform 统一保存资源引用、需求、预留、Action 关联、权限和审计。

外部科研服务同样区分版本化能力与受治理执行。Lab 服务管理员通过“预览→确认”登记服务商，再发布不可变的服务修订，固定仅本地引用的请求/结果 JSON Schema、版本、风险、报价策略、可选基础价与币种、SLA 目标、样本要求、物流规则和条款。创建 Task 时可将已批准服务的准确服务商与契约修订固定到 Research Environment。这只证明 Run 允许请求什么，不等于下单、授权付款、发送样本或收到结果。服务商编辑和后续服务修订都不会改写活动 Task 的快照。

External Service Job 是受治理的执行对象。Aira 规划器只能选择已固定到 Research Environment 的准确服务，并提交符合固定输入 Schema 的请求；这只会创建请求草稿，不会自动下单。Aira 与手工请求随后进入同一状态机。服务商报价或锁定的目录价会保存为不可变报价，并创建绑定摘要的下单审批。审批时会在锁内重新解析契约、检查报价有效期与 Task 币种/限额，然后预留准确金额；未通过审批就不会进入已下单或可交接样本状态。履约进度与失败使用明确状态变更。样本交接是针对有权访问的 Lab 资源及可选容器追加的不可变序列，不把交接误当成库存消耗。接收结果时按锁定结果 Schema 校验，关联准确的 Task DataAsset 版本，释放已批准预留、记录实际支出，并把类型化 Service 结果回传 Run。实际费用高于批准报价时失败关闭，必须建立新的审批边界。AI 关闭后，这条确定性流程仍可完整使用。

计算同样严格区分版本化能力契约与后续执行对象。Lab 计算管理员通过“预览→确认”创建或修订 `Compute Environment`。每个不可变修订都会固定 OCI 镜像 SHA-256 摘要、Runner 协议版本、Python/R 语言允许清单、CPU/内存/GPU/超时/输出硬上限、禁止网络或准确出站主机允许清单、本地输入/结果 JSON Schema、软件清单、风险和可选每小时成本。Research Task 可固定其中一个准确修订；后续修订不会改写已经捕获的环境。

执行平面使用独立鉴权的 `Compute Runner`。Lab 计算管理员通过“预览→确认”创建或轮换凭据、限制并发，并且只能把 Runner 绑定到已经审核的准确 Compute Environment 修订。绑定绝不会自动跟随可变环境谱系。Runner 状态契约会报告协议、执行后端、容量和四项强制隔离控制：非 root 执行、只读根文件系统、网络隔离、无宿主机挂载。任何一项缺失都会使 Runner 不具备执行资格，而不是放宽策略。

`Compute Job` 是带审批门禁的执行对象。人工请求与 Aira 提案会聚到这一对象，通过 SHA-256 绑定源码字节，并固定语言、经过 Schema 校验的 JSON 输入、Project 内准确的 DataAsset 文件版本、明确声明的输出文件、Task 已固定的环境修订、资源与网络限制，以及最大预估成本。规划器只能看到当前可用、已有授权 Runner 支持的固定修订与合资格 DataAsset 当前版本，不能指定任意镜像、资产、路径、密钥或网络目标。每项输出在审批前就会固定安全文件名、媒体类型、资产类型、字节上限、是否必须产生及目标元数据，Aira 生成的源码还会受响应字节上限约束。“预览→确认”或通过确定性校验的规划提案只会创建 Proposed Action 和独立审批；审批人可查看完整源码、摘要、准确输入、限制、成本和输出。审批时会在锁内重新解析不可变契约与 Runner 授权，并在 Task 配有预算时预留最大成本。选择环境或登记 Runner 本身从不等于授权执行。

只有已就绪 Runner 才能主动领取与其准确环境绑定匹配的排队作业。Platform 返回规范的 `airalogy.compute-job.v1` 信封、HMAC 签名和短时作业租约；只有该租约可以下载作业明确固定的输入 Blob，并且只能上传到已声明的准确输出 ID。开始、心跳和受限输出上传会续租；开始前租约过期可安全回到队列，开始后失联则因执行结果不确定而失败关闭并暂停 Task。暂停或取消 Task 会变成明确的 Runner 取消请求。完成时，Platform 会按硬上限校验申报用量、按固定 Schema 校验结构化结果，并将每项输出回执与已存储的字节数、媒体类型和 SHA-256 交叉校验。只有全部通过后，Platform 才会创建 Project 范围的 `ResearchFile`、草稿 `DataAsset` 和版本来源，精确关联 Job、Action、环境修订、源码摘要和声明输出。随后再把最大预留转换为确定性实际成本，追加不可变事件，并把类型化 Compute 结果交给后续重规划或人工继续。失败和取消确认如果携带部分用量，也会记录实际消耗并只释放未使用预留；已上传但未完成的文件永远不会获得带逻辑权限的资产身份。

Platform 永远不会在 API 进程中运行科研代码，也不会把容器运行时 Socket 挂载给 API。仓库在 `apps/compute-runner` 提供可独立监管的参考进程：它会再次验证签名信封与准确输入/输出路径，把通过字节数和摘要验证的输入流式写入 Docker/Podman 管理的作业专用、有容量上限的 tmpfs 卷，再以 UID/GID 65532、只读根文件系统、全部能力移除、资源硬限制且无宿主机绑定挂载的方式运行摘要固定镜像。禁止网络的作业使用隔离网络；允许出站的作业只有在准确主机集合已映射到由基础设施独立强制执行的预配置容器网络时才会运行。科研容器停止后，只由摘要固定且只读挂载的辅助镜像测量、计算摘要并流式上传已声明输出；Runner 无法指定任意宿主机或容器路径。仅属主可读的崩溃日志会在对账前停止结果不确定的容器，并幂等地补交上传与回调，期间不领取新作业。

设备集成从数据导入、引导执行、需设备端确认的辅助控制，再到策略内闭环自动化逐级升级。Aira 不直接向设备发送任意指令。在下一 Action 边界，它只能从 Platform 根据当前 Research Environment 与请求人本人已批准设备预约提供的列表中选择准确指令 ID，并提供符合输入 Schema 的参数。Platform 确定性选择最早可用预约，固定完整指令与资源状态，并始终请求人员批准。批准时会在锁定下重新解析指令、Gateway、设备、权限、预约、Schema 和竞争作业状态，仅当全部一致时 Action 才可入队。本地 Instrument Gateway 只接收签名、结构化且列入允许清单的作业，并提供状态校验、审计和受治理的停止请求。

首个 Gateway 安全边界和执行闭环已实现。Lab Owner 或 Manager 需先预览再确认注册 Gateway，高熵密钥只显示一次，Platform 仅保存摘要；密钥轮换会使旧值立即失效，且 Gateway 持有活动租约时禁止轮换。每条允许指令都绑定某个设备 Resource 的准确修订和带版本指令标识，并固定仅本地引用的输入/结果 JSON Schema、超时、风险级别；中高风险操作必须在物理设备端确认。所有配置变更均产生不可变审计快照，停用 Gateway 或指令会阻止之后的作业领取。

Instrument Job 必须同时引用 Research Environment 中已固定的资源类型、白名单指令的准确修订和一条已批准且未过期的设备预约。Gateway 独立鉴权，在单任务短租约下主动领取规范化签名信封；必须在预约时段内启动，上报必要的设备本地确认引用，持续心跳续租，并回传符合已固定输出 Schema 的结果。Platform 绝不自动重试物理操作。执行中租约过期、超时、预约结束、显式停止、Task 暂停、失败或取消都会暂停 Run，并要求 Gateway 确认和人工检查设备。这是受治理的远程停止协议，不等同于软件可保证物理急停；硬件联锁仍是最终安全边界。

运行时契约仅允许 Gateway 在 TLS 下主动领取。Gateway 使用 `X-Airalogy-Gateway-Token` 鉴权并调用 `POST /instrument-gateway/v1/jobs/lease`；成功响应包含规范化 `airalogy.instrument-job.v1` 信封、作业专用租约密钥和 HMAC-SHA256 签名。Gateway 以 `SHA256(Gateway 密钥)` 作为 HMAC 密钥验签，之后只通过 `X-Airalogy-Instrument-Lease` 传递租约密钥，调用 `start`、`heartbeat`、`complete`、`fail` 或 `stopped`。密钥不允许出现在查询参数或设备指令载荷中。心跳返回 `stop_requested: true` 时，适配器必须调用设备特定的安全停止程序，然后确认 `stopped`。

仓库在 `apps/instrument-gateway` 提供独立、仅依赖 Python 标准库的 Gateway 运行时和适配器 SDK。它拒绝跨源重定向、无效签名、过期信封，以及未被本地独立安装适配器按准确版本允许的指令。设备启动前，唯一活动租约会以仅属主可读权限原子记录；完成、失败和停止确认可在网络结果不确定时幂等重放。进程若在物理执行可能仍在进行时重启，必须先调用适配器的幂等安全停止，再与 Platform 对账。关机、控制链路中断、安全停止失败或执行线程无法停止时，进程都不得领取下一项作业。Platform 下发代码和任意 shell 执行不属于此边界。

## 责任边界

| 子系统                      | 权威职责                                                   |
| --------------------------- | ---------------------------------------------------------- |
| Platform                    | 任务、运行时、权限、策略、资源、审批、通知、审计和科研资产 |
| Masterbrain/AIRA            | 目标理解、策略、计划、Action 选择、结果解释和重规划        |
| Protocol/Engine             | 可执行科研方法、Schema、校验、确定性计算和 Record 生成     |
| Scholar/Literature Provider | 可选文献检索、DOI 解析和元数据候选，不直接写入正式资产     |
| Executor/Gateway            | 在明确契约和策略内执行人员、工具、设备或外部服务作业       |

## 交付阶段

### P0：端到端人机协作闭环

- Research Task/Run/Action/Event 和计划版本；
- 基于现有 AIRA Method 的持久化规划与重规划；
- Protocol Run + Human Work Item；
- 分配、站内待办和可选通知；
- 预填 Protocol，提交 Record/DataAsset，验证后通过事件自动恢复；
- 暂停、恢复、取消、幂等、重试、权限与审计；
- AI 关闭时的人工计划和执行路径；
- Research Result Package；
- 旧 Protocol Workflow 兼容。

验收基准是 CNT 类迭代实验：任务创建后 Aira 选择下一个 Protocol，人员提交真实 Record，Run 恢复、形成阶段结论并继续，直到结束。

### P1：Knowledge 与数字自动化

- 私有 Lab Paper Library、Knowledge、Evidence 和 Claim；
- Scholar 作为可选 Literature Provider；
- 文献调研、Python/R 计算和外部工具 Action；
- Paper → Knowledge → Protocol Draft，Record/DataAsset → Suggested Knowledge；
- 发酵类多源数据集成验收。

### P2：现实资源与治理

- 派生的 Capability Registry 与任务级版本固定（已交付）；
- Lab 可配置的 Protocol/Tool Executor Binding、合资格成员直接指派或已验证技能池匹配，以及派发时复核（已交付）；
- 固定修订的资源需求，以及库存/设备预约与释放 Action（已交付）；
- Aira 资源请求、确定性候选解析、审批与过期状态拒绝（已交付）；
- Task 截止时间、预算上限、不可变预算账本、执行停止门禁和可审计的显式限额修订（已交付）；
- 人员、设备和外部服务 Executor Binding 适配器；
- 保留修订的人员可用性、容量与已验证技能（已交付）；样品语义和自动成本采集；
- 不可变 Compute Environment 目录、范围权限、“预览→确认”修订、Research Environment 准确版本固定、受治理的 Runner 身份/就绪报告/环境绑定、人工与 Aira 规划共用的审批/预算/租约/结果 Compute Job、声明输出摄取、草稿 DataAsset 登记，以及可独立监管的参考 Runner（已交付）；
- 消耗完成、风险策略、审批阈值和资源感知的计划重排。

### P3：设备、RaaS 与自我改进

- Instrument Gateway 注册、受治理指令允许清单、签名作业领取、心跳、结果校验回传和需确认的远程停止（已交付）；硬件特定联锁和分级闭环控制待后续实现；
- 受治理服务商目录、不可变服务契约、范围权限和 Research Environment 准确版本固定（已交付）；
- Aira 规划与手工外部服务请求共用报价、下单审批、预算预留、物流、交接、履约和结果接收治理（已交付）；
- 由 Evidence 支持、经人审核的 Protocol 改进建议与准确新版本来源链（已交付，不依赖 AI）；
- 独立建议型 Reviewer Agent（已交付）、有界并行只读 Tool 前沿（已交付）、通用依赖/多 Agent 执行和复现评估；
- 蛋白纯化方法演进与 OT-2 设备治理验收。

## 交付完整性

“完整实现”指每个阶段的垂直切片都同时包含：数据库迁移、API 权限、后端校验、前端完整状态、中英文、AI 开/关路径、错误和恢复、版本/审计、迁移兼容、测试、生产构建、文档和更新日志。只有 Schema、只有对话、只有界面或只有 AI 演示都不算完整。
