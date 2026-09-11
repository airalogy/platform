# 复用已审核的界面流程

成功的[有界探索](./instrument-interface-exploration.md)现在可以保存为**本地私有的固定流程**：保留实际执行步骤、准确的初始控件值/可用状态、探索**之前**设定的成功标准，以及来源证据摘要。后续复用同一确定性浏览器/原生后端，不再调用 Aira。这是中间开发成果，**不是 Adapter Package、Platform Workflow、Instrument Job 或实机验收结果**。

## 记录人员的浏览器示范 {#browser-demonstration}

`gateway:demonstrate`（安装后为 `airalogy-interface-demonstration`）记录人员在明确选定、离线的**自建模拟 HTML 软件**中的真实浏览器输入事件，不替人员执行动作菜单。使用与探索相同的已审核定义、有限固定动作及成功策略；`gateway:interface-example` 可准备自建示例而不打开页面。未知控件、参数泛化、原生软件、真实 URL 和视觉桌面录制不在此录制器范围内。

```bash
pnpm gateway:demonstrate preview --definition /absolute/private/definition.json --policy /absolute/private/policy.json
pnpm gateway:demonstrate record \
  --definition /absolute/private/definition.json --policy /absolute/private/policy.json \
  --confirm <已审核的示范预览摘要> \
  --evidence /absolute/private/demonstrations --ack-visible-owned-simulation
```

预览不打开软件，固定准确源码字节、控件、允许的固定动作、隐私/成功策略和**可见窗口**选择。`record` 另要求交互式终端与明确确认，再打开独立的可见 Chromium 窗口，不附着已有登录浏览器或桌面。仍执行原有网络、下载、弹窗和框架限制；不要提供厂商设备控制 HTML，也不能把开发录制器当作物理安全边界。

在该窗口中示范审核过的操作。编辑字段后按 **Tab** 提交，等待终端显示已记录，再做下一步。记录回执未完成期间，后续输入被忽略而不是排队执行；紧接输入发生的点击可能需要在记录完成后再主动点击一次。达到原定成功标准后，在终端输入 **`finish`**。其他输入、EOF、Ctrl-C、窗口关闭或会话到期会结束录制而不提升成果状态。未提交输入、目标歧义、越界参数、未记录状态变化、无效事件或最终结果改变，都会阻止成功导出；失败后不自动操作、复位或重新启动。

保存的是所选控件读回值和语义点击/填写步骤，不保存原始按键、指针坐标、剪贴板内容或桌面录像。仍遵守已有明确范围、遮盖区域及可选范围截图设置。单个事件最多 256 KiB，并沿用定义中的步骤/时间限制。录制器核对先前观察，并独立重新检查当前目标、隐私、唯一控件及操作后状态。首版要求可观察的同步状态变化和字段提交，不推断厂商异步完成条件或任意键盘/菜单交互。应用文本/事件仍是不可信数据，浏览器可信输入事件也不能证明人员身份。

人员操作在**观察后记录**，使用独立的 `demonstration_action` / `demonstration_readback` 事件，不能伪装成动作执行前已落盘的 Agent 意图。成功导出保留 `source.kind: human_browser_events`，不匹配或混合来源的事件会被拒绝。这些所有者可控制的文件不是签名证明、事前实机授权，也不保证已观察到软件的全部副作用；应按界面资料同等规则私有保存与留存。

将返回的 `evidence` 用于下方导出，无需模型、Platform 开发凭据或付费服务。无头验收产生实际浏览器输入事件，验证导出和独立固定重放，再用同一适配包验证两次独立安装及真实 Instrument Job 的仅回执恢复。这是自动化合成证据，**不是真人易用性、可见终端验收或厂商实机测试**；这些仍需单独获授权的会话和目标。

## 预览并保存

使用成功的 `gateway:explore run` 或 `gateway:demonstrate record` 返回的 `evidence` 目录，不是存有 `request.json` 的上级目录。准备阶段只读取历史证据，不打开软件、不访问 Platform、不调用模型；原软件已经不存在时仍可整理历史成果。

```bash
pnpm gateway:workflow prepare --evidence /absolute/private/completed-interface
pnpm gateway:workflow export \
  --evidence /absolute/private/completed-interface \
  --workspace /absolute/private/saved-workflows \
  --confirm <已审核的导出预览摘要>
```

审核完整私有预览中的目标身份/路径、控件、固定步骤、初始条件、成功标准和来源。导出时重新检查证据，摘要过期会在创建输出前拒绝；通过后新建仅所有者可访问的目录，写入 `preview.json` 和 `workflow.json`，不修改原证据。安装后命令为 `airalogy-interface-workflow`，参数相同。

仅接受完整、已关闭且成功的记录。检查连续事件摘要、会话/预览身份、动作是否属于批准策略、观察到的前置条件、准确配对的操作意图/结果（或独立的人员操作/读回对）、参数读回和预设成功标准。结果缺失、中止、预算耗尽、未知事件或未记录操作导致的状态/数值变化，都不能转成可复用步骤。模型或人员声称完成并不足够。导出器不会补写缺失动作，也不会自动把固定值泛化为未经审核的参数或分支。

成果包含本地路径、批准的固定值及选定初始读数，**仍须保密**。不复制凭据、模型对话、截图、可访问性树或 HTML 源文件。只读取预览和编号事件：最多枚举 1,024 个目录项、读取 256 个事件，单文件不超过 512 KiB，总读取不超过 16 MiB。要求 POSIX 所有者私有目录/文件，拒绝选定的符号链接和多重硬链接文件。摘要用于检查一致性，不能防止拥有文件权限的人重写全部内容，也不是签名实机证明。

## 预览一次新的固定执行

```bash
pnpm gateway:workflow preview --workflow /absolute/private/saved/workflow.json
pnpm gateway:workflow run \
  --workflow /absolute/private/saved/workflow.json \
  --confirm <已审核的执行预览摘要> \
  --evidence /absolute/private/new-run-evidence \
  --ack-new-run
```

执行预览通过原后端重新核验当前运行环境和目标文件/构建，摘要**不同于导出确认摘要**。审核后明确确认这是一次**新操作**，不能用来恢复或重试结果不确定的旧操作。每次执行独立记录流程摘要、来源以及操作前后观察。固定开发重放无需模型或 Platform 凭据，AI 关闭或模型断连不影响这条路径。

打开/观察目标后，所有初始值、可用标记和状态都必须匹配；逐步执行仍检查新鲜观察、唯一控件、状态变化和参数读回。最后再观察一次，核对保存的成功标准。失败即停止，不自动重试、重置、重新启动，也不宣称物理安全停止。关闭浏览器不是停止仪器；加载页面本身也可能初始化设备，每次新执行仍需独立审核原有启动风险。

浏览器动作仍只适用于按哈希固定的模拟 HTML，真实 URL 仍只能观察。原生成果保留准确的应用、进程和构建身份，重放仍要求原本由本地模拟器封印核验的目标及初始状态，不打开、重置或替换原生应用。软件重启会改变进程身份，需要重新选择和审核。导出不将只读勘察升级为操作权限，不解除自建模拟器限制，不提供 Windows 或视觉控制。

## 验证及下一步集成边界

[固定运行环境的本地进程连接](./instrument-interface-worker.md)现已将已审核、已安装的 Python 适配包接到浏览器流程后端，复用 Instrument Job 执行及回执恢复。不会把流程成果自动升级为硬件权限；内置参考仍仅用于模拟，原生/视觉生产执行仍需独立验收的后端。

测试覆盖离线导出、证据链/语义错误、私有文件限制、过期确认、原生身份保留、真实无头重放、初始值变化，以及状态名正确但最终结果错误。真实 API/临时数据库验收完成“授权 → 探索 → 保存固定流程 → 独立命令重放”，使用合成模型输出和自建 HTML；重放**不增加模型调用**。原生历史导出无需占用前台即可测试，不代表已通过厂商软件或实机执行验收。

此功能不安装或启用适配包、不提交 Record、不发布 Knowledge，也不会把流程公开。编辑定义、步骤、初始条件或成功标准会形成不同摘要，需要重新审核；重新计算摘要不是验收。生产复用仍须经过适配包版本审核、安装、目标准入及 Instrument Job 的权限、预约、本地确认、租约、停止/核对和数据回传规则。原生人员示范录制、自动参数泛化、厂商 GUI 的正式执行验收、支持系统验收和明确的真实试点仍待完成。
