# 科研自动化

Airalogy 的科研自动化从有边界的 `Research Task` 开始，而不是从无约束对话开始。一个 Task 会把目标、成功与停止条件、Lab 和 Project、已锁定的 Research Environment、Runs、Actions、Evidence、Claims 及最终人工审核保存在同一条可追溯链路中。

## 开始 Research Task

1. 进入“科研”，在正确 Project 中创建 Task。
2. 填写可检验的目标、成功条件和停止条件；如果 Task 必须在硬性的时间或费用边界内运行，同时设置截止时间和单一币种的预算上限。
3. 选择可能指导或约束研究的 Protocol 版本、数字工具、已审核 Knowledge 和 Lab 资源类型。若研究路径只需受治理的数字工具或外部结果，可以不预先选择 Protocol。
4. 预览保存位置与将被捕获的环境，然后确认创建。
5. 开始 Task。Aira 可用时，它会持续推进，直到遇到人工、审批、工具、外部结果或最终审核边界；AI 不可用时，同一 Task 仍可通过明确的 Actions 执行。

之后修改 Protocol 或 Knowledge 不会静默改变已捕获的 Research Environment。只有新建计划或 Run 后，新版本才应进入执行。

## 从 Knowledge 生成 Protocol 草稿

进入“Knowledge”，切换到“Knowledge 笔记”，在有效条目上选择“生成 Protocol 草稿”。先核对固定的来源修订，选择符合范围的目标 Project，再进入 Aira 草拟。Platform 会通过受保护接口把 Knowledge 内容载入可编辑生成器，不会把正文放进 URL。检查并修改生成的 AIMD 后，选择“保存 Protocol”，再次确认目标 Project。

只有完成最后确认，Protocol 才会成为正式资产。保存时 Platform 会重新检查你是否仍可读取 Knowledge、是否能在 Project 创建 Protocol，以及来源是否仍是同一修订。来源发生变化、归档、被取代、跨范围或不可访问时都会拒绝保存，不会静默生成失去来源的资产。保存成功的 Protocol 版本保留不可变 Knowledge provenance。AI 关闭时不显示这个入口，但模板、复用、导入和手工创建 Protocol 仍完整可用。

## 将已校验结果整理为候选 Knowledge

在 Research Task 中，先把 Record 或准确 DataAsset 版本登记为 Evidence，并由有权人员完成校验。在“科研结果资产”中选择“提议为 Knowledge”，写下可复用的发现、方法、决策或笔记，并选择一条或多条已校验 Evidence。检查 Project 保存位置和准确来源集合后再确认。

Platform 会创建 Project 范围的可编辑 Suggested Knowledge，并保留不可变 Evidence 快照和版本关系；它不会宣布该候选已经成立或被组织采纳。进入 Project Knowledge 可继续修订，Knowledge Reviewer 评估证据后再使用独立的“审核并采纳”操作。待审核、已拒绝或非 Record/DataAsset 的 Evidence 不会出现在可选列表中。该确定性路径在 AI 关闭时仍可完整使用。

## 重试、复现或延续 Run

当前 Run 和 Task 完成、失败或取消后，在 Task 页面选择“新建 Run”。已形成的科学结果必须先经人工审核，才能开启下一次 Run。可选择任意已结束的来源 Run，标记为重试、复现或延续研究，并说明这次执行预期产生的差异。确认前的预览会展示新 Run 序号、来源、保存位置和准确的 Research Environment 摘要。

新 Run 会保留之前每次执行和科研资产，并精确继承来源环境。它不会自动采用之后更新的 Protocol、Knowledge、Tool、执行策略或资源定义。Task 会回到草稿状态，由用户明确启动下一次执行；原截止时间和共享预算账本继续生效。Run 来源链会保留每次结果和人工审核结论，便于对比。

## 选择正确的 Action

- **Protocol 工作**：把锁定版本的方法指派给人员。执行人使用正常 Record 表单完成实验，校验通过的 Record 会回传为 Evidence，而不是普通对话消息。
- **科研工具**：运行白名单中且锁定版本的数字能力，例如检索已审核 Knowledge 或可选的 Literature Provider。输入和输出都会经过 Schema 校验，执行有超时、重试和完整留痕。
- **等待外部结果**：在人员、设备或外部服务返回结果前，把 Run 暂停在类型化边界。选择并确认预期结果契约；系统生成的事件键是不可变的交付引用，当前版本由获授权用户在工作台登记已收到的结果。
- **预约资源**：从 Research Environment 已固定的资源类型中解析具体资源。库存预约需选择容器、准确数量、UCUM 单位与可选失效时间；设备预约需选择时段。Platform 会预览当前可用量与策略，拒绝过期或冲突的确认，并把权威库存预约或设备预约关联到 Action。

Aira 可以请求固定的资源类型、数量、单位或设备时段，但不能任意选择隐藏资源或直接完成预约。Platform 会确定性选择请求人有权使用的候选，并展示准确影响供用户审批。如果审批前库存、权限、资源修订或设备时段发生变化，旧提案会被拒绝并要求重新规划。

## 控制时间与预算

Task 页面会显示已固定的截止时间，以及预算的预留、实际支出、已承诺和剩余金额。具备科研审批能力的用户可以登记预留、释放、支出或冲销；每条记录都必须基于当前 Task 修订先预览再确认，保存后不能修改。释放不能超过已有预留，冲销不能超过已有实际支出；需要纠错时应追加抵消记录和正确记录，不能改写历史。

Platform 会在 API 层创建每个新的人工或 Aira Protocol、Tool、Wait、Resource Action 前检查限额，拒绝过期预览和超限写入。确认的预算记录耗尽上限时会立即暂停 Run；从其他入口发现截止时间或预算到达边界时，会在下一个运行边界安全暂停。当前版本不会推测模型、计算、库存或外部服务的货币成本；在接入权威费用提供方前，应在账本中显式登记实际支出。

检索候选项只是 Action 输出。Platform 不会将其静默采纳为 Knowledge、Evidence 或 Claim。

每次到达“下一步做什么”的边界时，Aira 会先在固定版本的 Protocol、可用 Tool、固定的资源需求、类型化外部 Wait 与结束当前路径之间选择。Action Planner 不会直接执行模型自由文本：Platform 会先校验 Action 类型、白名单、固定版本、输入参数、资源需求和结果契约，再创建正式 Action。在 Lab 尚未为对应风险级别配置明确策略前，Aira 提出的数字、资源与人工 Action 均需审批。

## 提交外部结果

打开正在等待的 Action，选择“提交结果”。填写固定事件契约定义的字段，预览准确载荷后再确认。Platform 会检查当前用户权限、事件类型、载荷 Schema 和事件修订号，过期、重复或不兼容信号会被拒绝。

AI 可用时，Run 随后恢复 Aira；AI 关闭时，它会回到普通手工控制，不阻断 Protocol、Record、Knowledge 或结果审核。

## 审核科学结果

执行成功不等于科学结论成立。完成 Task 前：

- 检查执行账本和失败尝试；
- 校验或拒绝待处理 Evidence；
- 根据关联 Evidence 和不确定性审核 Claims；
- 完成或取消尚未结束的 Actions 与审批；
- 记录目标评估、科学结果和审核后的结论。

取消 Task 会保留已有 Records、Action 历史、工具来源与科研资产，同时防止未完成工作重新启动该 Task。尚未释放的库存预约及待审批或已批准的设备预约会自动归还；提前手工释放同样采用“预览→确认”。

## 权限与安全

Research Action 同时使用当前 Project 与资源权限，并由 API 强制执行。看到工具或资源类型，不代表可以绕过 Knowledge 可见性、Restricted 内容授权、对象级资源访问、库存操作权、设备预约权或 Project 访问权。外部结果必须由具备科研执行权限的已登录用户提交，事件键本身不构成授权。拒绝 Aira 提案后，对应的类型化执行记录会被取消，拒绝原因会记录并传回下一轮规划。
