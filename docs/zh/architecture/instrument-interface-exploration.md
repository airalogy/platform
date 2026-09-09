# 有界 Aira 界面探索

本功能在[浏览器界面后端](./instrument-browser-interface.md)上增加**在预先审核的动作中动态选择下一步**。本地人员先选择应用、语义控件、可观察状态、固定动作和成功条件；Aira 根据选定的文字读回选择动作序号、提出缺失信息或建议结束。本地执行器独立校验每次选择及结果，不允许模型发明控件、参数值、网址或代码，也不自动发现任意软件。

这是开发证据，**不是生产设备控制或设备验收**。填写/点击仅支持隔离、审核过的模拟 HTML；真实 URL 仍然只能观察。加载页面或 GET 也可能初始化设备，仍须独立取得本地授权。尚未完成已有登录浏览器、原生桌面、截图理解或真实仪器验收；私有文件运行环境支持 Linux/macOS，Windows ACL 支持仍待实现。

## 准备本地动作策略

按浏览器指南安装固定版本的 Node/Chromium。`pnpm gateway:interface-example` 生成私有临时 `definition`、`plan`、`policy`、`evidence` 路径，不启动浏览器。策略是有限的动作菜单，不是预定执行顺序：

```json
{
  "goal": "读取两个模拟样本",
  "actions": [
    {
      "operation": "fill",
      "control_id": "sample.count",
      "value": "2",
      "before": "ready",
      "after": "ready"
    },
    {
      "operation": "click",
      "control_id": "measurement.start",
      "before": "ready",
      "after": "completed"
    }
  ],
  "success": [{ "control_id": "result.value", "equals": "0.84" }]
}
```

使用生成的策略及其匹配的界面定义，控件/状态 ID 必须一致。审核 HTML 源码和每个动作，包括读取。模型可以在步数/调用限制内重复选择已审核动作；授权菜单不等于每个动作只能执行一次。不得把凭据或生产操作写入策略。

```bash
pnpm gateway:explore prepare \
  --definition /absolute/definition.json --policy /absolute/policy.json \
  --workspace /absolute/private/exploration \
  --platform-url https://lab.example.edu/api \
  --gateway-id <Gateway-UUID> --resource-id <equipment-Resource-UUID> \
  --max-iterations 5 --duration-seconds 600
```

准备阶段不发网络请求、不打开应用，创建仅所有者可读的新目录：

- `preview.json`：完整本地应用/动作策略、摘要和运行时版本。
- `authorization.json`：导入 Platform 的请求，不含 bearer 凭据、源码路径或 HTML，但包含固定参数等**实验室私有资料**，不是公开文档。
- `request.json`：本地凭据、界面定义/策略及 Platform 地址。**不得上传，也不得粘贴到聊天或 Issue。**

输出的 fingerprint 标识远端授权请求；`local_preview_digest` 标识精确的本地启动策略。两者均须审核，不能直接复制未经审查的摘要。API 地址拒绝相对地址、凭据和查询参数；非回环地址必须使用 HTTPS。

## 授权与运行

在**实验室 → 资源库 → 仪器网关 → 选择网关 → Aira 界面探索**导入 `authorization.json`。具有当前 `equipment.service` 权限的 Owner/Manager 须核对指纹、全部动作和成功条件，并同意所配置模型处理资料；填写原因、预览后确认。本地人员还需独立确认本地预览：

```bash
pnpm gateway:explore run /absolute/private/session/request.json --confirm <local-preview-digest>
pnpm gateway:explore sync /absolute/private/session/request.json
```

安装包提供同参数的 `airalogy-interface-exploration` 命令。授权限 1–5 次模型调用、30–900 秒；浏览器定义还有独立的时长、步数和观察次数限制，两者不能互相延长。单次模型响应最长 60 秒、16 KiB。这是调用/时间/输出上限，**不是保证的费用封顶**。

后端先持久化调用占位，再联系 Aira；重复轮次 ID 必须携带相同输入。授权固定网关/设备修订、授权人、模型和模型连接配置；生成结束后再次校验，取消、过期或配置改变后不接收迟到提案、不启动新调用。历史和回传仍受当前范围权限限制。源码开发 `aiauthor_`、界面开发 `aiinterface_` 与安装/网关凭据用途隔离，不能互换。

模型只接收选定控件标签、读回、已审核动作、先前提案及有界结果；所配置模型可能位于外部。不会自动发送原始截图、可访问性树、HTML 或本地路径。应先审核保密要求和模型处理权限；这不是自动秘密检测。软件文字及模型建议都是不可信资料，不能授权额外工具。

即使模型建议结束，本地也会重新观察并拒绝变化的状态。填写必须精确读回，点击必须符合目标状态；成功由独立配置的条件判断，不能只凭模型声称“完成”。观察、提案、动作回执保存在私有不可覆盖文件及 Platform 私有历史中；客户端回报不等于可信实机证明。

## 停止与恢复

取消会在下一次授权检查后阻止新调用/动作，不保证原子中断正在执行的操作，也不代表物理安全停机。未知状态、重复控件、过期观察、越界提案、网络错误或限额耗尽均停止开发。AI 不可用/关闭时，手工观察、固定计划、适配包制作及原有治理仍可使用。

保留的独占 `run.started` 标记禁止同一请求重新启动，即使 Platform 未收到结果也如此。动作意图与标记写入后，同时刷新文件内容和所在目录项；刷新失败则停止执行，这不代表存储硬件或断电认证。不得删除标记来重试不确定动作。`sync` 只重发已存在的不可变动作回执，不打开浏览器、不调用模型、不补造缺失回执。与本地人员核对未结束调用、证据和不确定操作；新的运行需要重新准备并授权。取消/过期后，当前权限和凭据仍有效时可同步已有回执。

结果区分 `client_reported_success`、`needs_information` 和 `budget_exhausted`，Platform 历史将授权标为已结束/取消。这些结果均不导入、审核、安装或激活适配器。经过审核的观察可显式转交独立的[源码开发流程](./instrument-source-authoring.md)，不会自动发布或共享文件。

## 部署与验收

迁移 `0056_instrument_exploration` 为开发表增加用途字段（已有会话默认 `source`）和不可变轮次输入。通过正常备份发布流程部署 API 和本地运行时。降级会先删除界面开发会话/轮次，再移除用途字段，避免旧的仅源码服务误用界面授权；保留源码会话，不撤销本地动作或文件。

`gateway:contract:check` 检查 Node 单一来源 JSON Schema 与 API 副本；固定样例验证两端摘要一致。`gateway:interface-test` 使用真实 Chromium 和合成模型选择。`research:integration` 进一步连接真实 API、一次性 PostgreSQL 与独立 Node/Chromium 进程，仅模型流为合成夹具。界面测试用明确标注的响应夹具验证预览确认、私有文件拒绝、输出转义、历史/取消和 AI 关闭。这些测试不证明付费模型质量、厂商软件或实机已验收。

未知原生软件发现、获授权的原生/视觉 Computer Use、受管理生产 GUI 适配器、各操作系统运维以及有明确型号和负责人的实机试点仍待完成，仍属于整体接入目标。
