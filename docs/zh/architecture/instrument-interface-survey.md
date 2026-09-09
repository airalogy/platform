# 选定应用的界面勘察

在**明确选定**的浏览器应用中自动识别可见控件，不必先手写控件与状态表。这是有界本地开发证据，不是自动扫描已安装软件，也不授予设备操作权限。复用[浏览器后端](./instrument-browser-interface.md)的独立 Chromium、精确网络白名单、隐私遮挡与停止规则。目前只支持 Linux/macOS 私有文件环境；原生 Windows 与视觉 Computer Use 仍未认证。

## 准备并审核

按浏览器指南安装 Node 22+、仓库依赖及固定版本 Chromium。使用仓库自有合成读数软件时，替换以下绝对路径：

```bash
pnpm gateway:survey prepare \
  --file /absolute/platform/apps/instrument-gateway/examples/simulated-reader.html \
  --application 'Airalogy Simulated Reader' --version 1.0 \
  --title 'Airalogy Simulated Reader — no hardware' \
  --scope-role main --workspace /absolute/private/survey
```

准备阶段读取选定文件并固定摘要，在新的私有目录保存请求，返回 `request_file` 与 `local_preview_digest`；不启动应用、不调用模型、不请求网络。先审核旁边的 `preview.json`：源文件、人工声明的版本/标题、范围、运行时、网络、隐私与上限。本地 HTML 必须是独立审核过的模拟/训练内容，不能用于绕过厂商软件或生产控制要求。

对于选定网页，用 `--url` 替代 `--file`。首次精确 GET 会列入预览；其他同源 GET/HEAD 必须通过 `--network /absolute/rules.json` 明确指定。不会共享登录状态或浏览器配置，不允许任意地址、跳转、Socket、嵌入框架、下载、点击或填写。**打开软件、甚至 GET 都可能初始化设备**，观察也必须另获现场人员授权，不能试探未知生产接口。

默认不采集输入值、不截图。`--capture-values` 与 `--screenshot` 分别启用，并明确列在预览中。`--redact /absolute/locators.json` 接受精确语义定位器数组；用 `--scope-role`/`--scope-name` 或 `--scope-test-id` 选择唯一范围。高级用法 `--selection /absolute/selection.json` 完整采用已保存配置，不允许混入覆盖项。该工具不是自动敏感信息检测器：静态文字、标签、测试 ID 和获准字段值也可能包含私有科研内容，分享前须本地核对。

## 单次采集

```bash
pnpm gateway:survey run /absolute/session/request.json --confirm <审核后的本地摘要>
```

启动前先持久化 `run.started`，该标记一直保留。失败或回执丢失后重复同一请求也会拒绝；不要删除标记来重放不确定的启动。应与现场人员核对私有证据，新准备意味着一次新操作。关闭浏览器不代表设备已安全停止。

只检查选定可见范围内最多 200 个候选元素，输出最多 64 个控件提示。只有 Chromium 精确解析到同一唯一节点时，才保留测试 ID 或可访问角色/名称定位器。重名或不支持的语义仅作提示，不生成可执行定位器。密码/文件输入和私有遮挡内容会排除，涵盖 Shadow DOM 组合祖先、间接标签；未同意字段值采集时，外层文字容器也不能绕过限制。可选截图仅私有保存并遮挡，不上传截图、原始 HTML 或完整可访问性树。

结果包含 `survey.json`、摘要和手工分析模板。版本来自人工声明，单次客户端观察不证明状态转换、实验结果、设备身份或物理就绪。客户端拥有的文件及导出不是可信认证凭据。

## 审核并生成普通草稿

查看 `survey.json`，编辑生成的 `manual-analysis.json`，保留原 `capture_digest`。从唯一、可读取的**文字**控件中选择显示应用/版本身份的 `identity_control`；`read_controls` 只能选择 `locator` 和 `read` 非空的已观察控件 ID。`features` 区分 `observed`（观察）与 `inferred`（推断），记录 `read_only`/`state_change`/`unknown` 风险，不授予任何执行权。`route` 可建议 `browser`、`api_or_sdk`、`manual` 或 `unknown`，不能仅凭界面推断 API 必然存在。

```bash
pnpm gateway:survey assemble /absolute/session/request.json \
  --analysis /absolute/session/manual-analysis.json --workspace /absolute/private/drafts
```

生成前核对选定范围/运行时/源文件、保留回执、采集摘要及控件引用；只写入**新**私有目录，不启动软件、不调用模型、不覆盖已有草稿。输出普通可编辑的 `definition.json`、空 `plan.json`、分析/报告副本和来源记录。生成控件全部**只读**。唯一的 `observed` 状态只是初始身份锚点，不能作为经实验验证的成功条件。再次打开该定义，需要独立的浏览器预览确认，并视为一次新操作。

不会安装、启用或认证适配器。进入 [Aira 动作选择](./instrument-interface-exploration.md)前，须独立审核新增控件、固定动作、状态转换及成功条件。向[源码开发](./instrument-source-authoring.md)转移选定报告文字也必须显式进行。关闭 AI 后，本地/手工流程完整可用。

## 可选的 Platform Aira 分析

进入**实验室 → 资源库 → 仪器网关 → 选择网关 → 应用界面勘察**，选择设备，仅导入本地审核过的 `survey.json`。填写目标与理由，确认准确快照和模型处理范围，再预览并与本地结果核对**采集摘要**。确认后保存有效期五分钟的私有分析授权；点击**开始单次分析**才发起唯一一次模型调用。确认本身不启动软件，也不调用模型。

用户鉴权的 `/instrument-surveys` API 独立执行当前实验室/设备服务权限、用途隔离和准确预览核对。只有确认授权的用户能启动计费调用。固定网关/设备修订、用户、模型及处理通道配置，模型返回后再次核对。最多一次调用，响应上限 60 秒、32 KiB，不保证货币支出上限；联系现有 Aira 服务前先持久化调用占位。相同轮次重试只返回已保存状态，第二轮次会被拒绝。浏览器请求覆盖该响应时间窗且不自动重试。发生不确定情况后刷新历史，不重新发起调用。

模型只收到选定报告文字与用户目标，不收到本地源码路径、HTML、截图或已登录浏览器。所有内容都作为不可信数据；校验拒绝虚构控件、额外操作、未授权读回和无效身份锚点。解释区分观察/推断与只读/改变状态/未知风险，始终只是建议，不是设备验收；不能仅凭按钮名称断言 API/SDK 存在。

审阅结果后点击**导出已审阅分析**。将导出 JSON 保存到仅本人可读写的本地目录/文件，再替代 `manual-analysis.json` 传给 `assemble`。采集摘要必须与保留的原始回执一致。来源记录明确标为客户端提供的 Aira 导出，不是密码学认证；原始分析仍保存在 Platform 私有历史中。生成结果仍是同一种普通只读草稿，不继承点击/填写、来源批准、安装或启用权。

取消后不接受迟到建议，但不能撤回已传输数据，也不保证取消服务商计费。AI 关闭或授权过期后，历史及已完成结果导出仍受范围权限保护且可用。服务重启丢失的调用超过期限后显示中断，不会自动续跑。

迁移 `0057_instrument_survey` 为现有开发历史增加独立 `survey` 用途。降级会先删除勘察会话/轮次，再恢复原有源码/界面用途约束；保留 source/interface 历史，不修改本地文件，也不撤销已发生处理。请按正常发布流程备份后部署。真实 API/数据库/Chromium 验收仅替换模型流为合成结果，不代表付费模型效果评估或实机验证。

安装后的命令为 `airalogy-interface-survey`。`gateway:interface-test` 验证真实合成 Chromium、隐私、重名定位、独立 CLI 防重放与只读草稿重新打开；`gateway:contract:check` 核对共享 Node/API 契约。这些测试不代表厂商软件、原生/视觉操作或真实仪器验收。
