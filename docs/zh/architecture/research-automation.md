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

### Research Run

`Research Run` 是一次可恢复的执行，对应一个计划分支、复现或重试。它固定当次 `Research Environment` 快照、Protocol 版本和每次计划修订，通过持久事件恢复，不依赖浏览器会话或一次性 AI 请求。

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

Protocol Run、Human Work Item、Tool Job 和 Wait Event 已使用这套生命周期。Instrument、外部服务、审批请求和资源预留类型会在对应 Executor 接入时沿用同一边界。

### Protocol 与 Capability

`Protocol` 是可重复、有科学意义、可版本化的方法，应定义输入、输出、证据要求和验证规则。它可表示实验、文献综述、计算、数据处理、分析、评估或报告方法。

`Capability` 不取代 Protocol。Capability Registry 是根据 Protocol、工具、人员技能、设备、外部服务、资源、可用性和策略组合得到的当前能力视图，不是第二套方法来源。

Platform 的第一版 Registry 由 Project 当前 Protocol 版本、实例白名单数字工具和 Lab 当前 Resource Type 修订派生。创建 Research Task 时必须明确选择 Protocol 和 Tool 能力，并在 `airalogy.research-environment.v2` 中固定来源版本及初始人员或 Platform Worker 执行绑定。Aira 和手工控件都不能执行快照之外的 Tool，版本已不可用时也必须失败关闭。Resource Type 只作为可发现的执行需求，不被伪装成可执行方法；具体预约和消耗在 Action 执行时解析。

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

计划是可版本化的自适应 DAG，而不是只能向前的页面步骤。它允许条件分支、并行、循环、重试、资源等待和人员审批。修改目标、成功标准、预算或高风险路径必须产生新的计划版本并重新确认。

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

## 证据与结果包

AIRA 的阶段性和最终结论不只保存为 Markdown。结构化状态至少包含：

- Claim 及其置信度；
- 支持、反驳和不充分的 Evidence；
- Record、DataAsset、Protocol 版本和执行人的 provenance；
- 异常、偏差、不确定性和未解决问题；
- 成功标准评估与建议的下一步。

最终交付是 `Research Result Package`，包含摘要、目标状态、Claim/Evidence、Protocol 版本、Records、DataAssets、失败尝试、验证报告和可复现清单。可读报告是该结构化包的视图。

## Knowledge、Log 与三个循环

- `Research Log` 记录过程中发生了什么，合并不可变系统事件和有修订历史的人工日志。
- `Knowledge` 是经整理、可复用、可审核和可派生的认识，Paper Library 是 Knowledge 的文献视图。
- Record 仍是一次 Protocol 执行的结构化证据，不转换为普通日志。

系统保持三个独立但互相连接的循环：

1. 研究执行：Protocol/Action → Record/Evidence → 阶段状态 → 下一个 Action。
2. Protocol 演进：Records → 改进建议 → Protocol Draft → 专家审核 → 新版本/SOP。
3. Knowledge 演进：Runs/Evidence → Suggested Knowledge → 审核 → Project/Lab Knowledge。

Aira 只能提交改进草稿或 Suggested Knowledge，不得静默修改已发布 Protocol，也不得在正在运行的 Run 中自动切换版本。

## 资源、设备与外部服务

- 规划阶段预留资源，执行阶段确认消耗或释放。
- 库存记录批次、失效期、位置、容器、数量和样品谱系。
- 设备记录能力、排期、校准/维护状态、风险和输出格式。
- 预算区分总额、预留和实际支出，超阈值必须审批。
- 人员执行受技能/资质、可用时间、工作量、权限和审批职责限制。

Platform 不必取代完整 ERP/LIMS。小型 Lab 可使用内置最小模块，成熟组织可连接既有系统；Platform 统一保存资源引用、需求、预留、Action 关联、权限和审计。

设备集成从数据导入、引导执行、需设备端确认的辅助控制，再到策略内闭环自动化逐级升级。Aira 不直接向设备发送任意指令；本地 Instrument Gateway 只接收签名、结构化且列入允许清单的作业，并提供状态校验、审计和紧急停止。

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
- Lab 可配置的受治理 Executor Binding 与可用性解析；
- 人员技能、设备、库存/样品、预算和计算资源；
- 预留/消耗、风险策略、审批阈值和计划重排。

### P3：设备、RaaS 与自我改进

- Instrument Gateway 与分级设备控制；
- 外部研究服务的报价、SLA、物流、交接和结果接收；
- Protocol 演进、独立 Reviewer Agent、并行/多 Agent 执行和复现评估；
- 蛋白纯化方法演进与 OT-2 设备治理验收。

## 交付完整性

“完整实现”指每个阶段的垂直切片都同时包含：数据库迁移、API 权限、后端校验、前端完整状态、中英文、AI 开/关路径、错误和恢复、版本/审计、迁移兼容、测试、生产构建、文档和更新日志。只有 Schema、只有对话、只有界面或只有 AI 演示都不算完整。
