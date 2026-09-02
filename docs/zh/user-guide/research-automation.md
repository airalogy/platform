# 科研自动化

Airalogy 的科研自动化从有边界的 `Research Task` 开始，而不是从无约束对话开始。一个 Task 会把目标、成功与停止条件、Lab 和 Project、已锁定的 Research Environment、Runs、Actions、Evidence、Claims 及最终人工审核保存在同一条可追溯链路中。

## 开始 Research Task

1. 进入“科研”，在正确 Project 中创建 Task。
2. 填写可检验的目标、成功条件和停止条件。
3. 选择允许使用的 Protocol 版本和已审核 Knowledge。
4. 预览保存位置与将被捕获的环境，然后确认创建。
5. 开始 Task。Aira 可用时，它会持续推进，直到遇到人工、审批、工具、外部结果或最终审核边界；AI 不可用时，同一 Task 仍可通过明确的 Actions 执行。

之后修改 Protocol 或 Knowledge 不会静默改变已捕获的 Research Environment。只有新建计划或 Run 后，新版本才应进入执行。

## 选择正确的 Action

- **Protocol 工作**：把锁定版本的方法指派给人员。执行人使用正常 Record 表单完成实验，校验通过的 Record 会回传为 Evidence，而不是普通对话消息。
- **科研工具**：运行白名单中且锁定版本的数字能力，例如检索已审核 Knowledge 或可选的 Literature Provider。输入和输出都会经过 Schema 校验，执行有超时、重试和完整留痕。
- **等待外部结果**：在人员、设备或外部服务返回结果前，把 Run 暂停在类型化边界。选择并确认预期结果契约；系统生成的事件键是不可变的交付引用，当前版本由获授权用户在工作台登记已收到的结果。

检索候选项只是 Action 输出。Platform 不会将其静默采纳为 Knowledge、Evidence 或 Claim。

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

取消 Task 会保留已有 Records、Action 历史、工具来源与科研资产，同时防止未完成工作重新启动该 Task。

## 权限与安全

Research Action 使用当前 Project 权限，并由 API 强制执行。看到工具不代表可以绕过 Knowledge 可见性、Restricted 内容授权或 Project 访问权。外部结果必须由具备科研执行权限的已登录用户提交，事件键本身不构成授权。
