# 外部 Agent 接入

用户可以让 Codex 或其他 MCP 客户端访问自己获授权的一个 Project。Platform 统一执行权限、严格数据校验和 Record 修订留痕。这些确定性操作不依赖 Aira、Masterbrain 或模型服务是否开启。

本期对应 [Issue #11](https://github.com/airalogy/platform/issues/11)，提供限权令牌、HTTP/MCP 读取、CSV 导入和本人 Record 修订。不授予管理权限、文件下载权限或仪器控制权限。

## 开启与连接

1. Lab Owner 或 Manager 在**实验室设置 → 外部工具访问策略**开启访问，默认关闭。需先确认组织允许外部工具及其模型提供方处理返回的数据。
2. 可填写禁止外部读取的顶层 Record 变量 ID，每行一个，适用于整个 Lab，包括公共 Project。修改策略会使尚未执行的确认失效。
3. 用户在**账号设置 → 外部 AI 工具**选择 Project、授权名称、允许操作及 1–90 天有效期。用户必须仍是 Lab 成员并有权访问该 Project；令牌不会扩大本人权限。
4. 令牌只显示一次，请安全保存。服务端仅保存 SHA-256 摘要。不要使用网页登录令牌或旧 API Key 替代。
5. 在客户端私密配置令牌。同源部署的 MCP 地址为 `https://your-platform.example/api/mcp`，设置页面会生成当前实例的连接命令：

```sh
codex mcp add airalogy --url https://your-platform.example/api/mcp --bearer-token-env-var AIRALOGY_PLATFORM_TOKEN
```

通过客户端的安全环境配置设置 `AIRALOGY_PLATFORM_TOKEN`。不要把令牌粘贴进对话、代码仓库、共享文档或连接命令。桌面应用不一定继承已打开终端的环境变量，配置后需从正确环境重启。客户端配置详见 [Codex MCP 文档](https://developers.openai.com/codex/mcp/)。

撤销后，后续调用立即失效，未执行请求同时取消。服务端每次重新检查令牌到期、账号凭据失效、Lab/Project 成员关系和策略。撤销前已经提交的操作仍是普通 Record，历史保留。

## 完成一次导入

让已连接工具依次执行：

1. 调用 `access_context`、`list_protocols` 和 `get_protocol`，确认保存位置并取得标准 CSV 表头。
2. 按准确的 `var.<id>` 表头整理 CSV。显示名称、近似名称不能作为自动映射；不得猜测补值、缺失分数补零或放宽 Protocol 校验。
3. 调用 `preview_import`，传入 Protocol ID、CSV 文本和唯一 `request_key`。平台复用现有导入器逐行校验；失败时返回有限的错误行、字段及类型，**不创建任何 Record**。
4. 用户本人打开返回的确认链接，在 Platform 登录创建令牌的同一账号，核对保存位置、记录数、Protocol 版本和完整 CSV，然后确认或拒绝。**外部令牌不能自行确认写入。**
5. 回到外部工具，以操作 ID 调用 `execute_operation`。执行时不能替换输入；成功返回已保存的 Record ID 和页面链接。

确认请求从预览开始 15 分钟后失效，用户确认不延长有效期。这是临时操作请求，不是 Record 草稿。修改输入需重新预览并使用新请求键；相同请求键和相同输入返回同一请求，换输入会返回 `409`。重复执行已完成操作返回原结果，不会再次导入。遇到网络中断应先查状态，不要直接创建新的导入请求。

## 修订记录

`list_records` 仅返回本人有权读取的最新版本。调用 `preview_revision`，提供 `record_id`、`protocol_id`、`expected_version`、待修改变量 `changes`、有意义的修订原因 `reason` 和新 `request_key`。保持现有 Platform 规则：只有原记录者可以修订自己的记录。 若最新版本已删除，列表也会隐藏该 Record 保留的历史版本。

用户在网页核对修改前后值并确认，执行后生成修订版本，保留原版本和原因。如果期间产生了新修订，执行会失败，需读取最新状态重新预览。外部通道没有删除操作。

## 首期范围与限制

- 每个令牌只绑定一个 Project，必须包含 `protocols:read`；可选 `records:read`、`records:import`、`records:revise`。修订同时要求读取权限。
- API 同时检查 Lab 字段限制及现有 Protocol/Record 权限。公共可见性不能绕过 Lab 成员资格或外部访问策略。
- Protocol 读取只提供字段 ID、标题、必填状态、基本类型和支持的校验限制。不返回 AIMD、执行代码、环境变量、模型提示、默认值或示例值。CSV 模板仅含表头。
- Record 只开放基本类型变量及支持的日期时间字符串；不开放附件、签名下载地址、报告、对象或数组。含文件地址的字符串被省略，并在 `withheld_fields` 标明，不会改写成科学意义上的空值。工具不得推测被省略内容。
- Protocol 含受限或不支持的复杂变量时，必须回到正常网页导入或修订，首期不对这类 Protocol 做部分写入。外部导入不会向校验器注入用户的完整旧 API Key 或 Protocol 环境机密；依赖这些凭据的校验需使用正常网页路径。
- CSV 最大 1 MiB，完整请求体最大 2 MiB，流式上传同样受限。保留现有行数限制。列表每页 50 条，通过 `next_offset` 翻页。每个令牌最多 10 个待确认/已确认请求，每个用户最多 50 个有效授权；已认证工具调用按用户限制为每分钟 120 次已记录活动。
- 外部 API 日志不记录令牌或 CSV/Record 请求正文。审计记录包含用户、授权、操作及结果引用，不包含输入值。校验错误只公开有限的行/字段位置和类别，不透传自定义校验器可能包含机密的文本。
- 执行、拒绝、撤销后清除确认请求正文；过期正文在访问过期请求时延迟清除。修订摘要仍是私有数据，读取需重新鉴权，不属于公开活动流。

## 接口约定

公开反向代理在以下应用路径前加 `/api`：

| 接口 | 认证 | 用途 |
| --- | --- | --- |
| `GET /external-access/dashboard` | 网页 `Auth-Token` | 本人授权、确认状态与审计 |
| `GET/PUT /external-access/labs/{id}/policy` | 网页，Lab Owner/Manager | 读取策略、携带期望版本更新 |
| `POST /external-access/grants` | 网页 | 一次性签发限权令牌 |
| `DELETE /external-access/grants/{id}` | 网页，令牌所属用户 | 撤销及取消待执行写入 |
| `GET /external-access/operations/{id}` | 网页，令牌所属用户 | 查看完整预览 |
| `POST /external-access/operations/{id}/decision` | 网页，令牌所属用户 | 以准确 `digest` 和 `approve` 确认/拒绝 |
| `POST /external-access/tools/{name}` | 限权 Bearer 令牌 | JSON 参数调用确定性工具 |
| `POST /mcp` | 限权 Bearer 令牌 | 无状态 Streamable HTTP MCP |

MCP 工具有 `access_context`、`list_protocols`、`get_protocol`、`list_records`、`preview_import`、`preview_revision`、`operation_status`、`execute_operation`。客户端通过发现接口获取参数结构；额外参数会被拒绝，执行工具只能携带操作 ID。发现工具不等于获得相应权限。

MCP 使用 JSON 响应，客户端需接受 `application/json, text/event-stream`；Origin 必须与 `SITE_URL` 一致，协商支持的协议版本，支持的通知返回 `202`。不创建会话 ID，不提供旧 SSE 通道或主动服务端请求，GET/DELETE 返回 `405`。工具失败以 `isError: true` 返回；直接 HTTP 调用使用 `401`、`403`、`404`、`409`、`413`、`422`、`429` 等状态。执行器的非标准错误提示用户回到正常网页检查，避免透传机密异常文本。

写入、幂等结果和审计在同一事务提交。锁定顺序为用户调用门控 → Lab 策略共享锁 → 令牌 → 操作 → Protocol → Record；普通网页 Record 修订同样锁定稳定的 Protocol，并可传入 `expected_version`。不同 Lab 成员的调用不需竞争整个实验室的独占锁。外部工具不能发送 SQL、指定任意服务端请求地址、修改成员或权限、执行仪器。

## 部署与后续

上线需执行 `0078_external_agent_access` 迁移，并部署匹配的前后端构建，遵循现有发布、备份和验证流程。本文不代表已授权或已完成线上升级。既有 Lab 默认仍关闭外部访问。独立 `mcp` 客户端仅是开发/测试依赖，生产传输使用现有 FastAPI。

集成测试覆盖真实迁移往返、CSV 校验、失败回滚、并发重试、修订历史、权限变化、过期、数据限制及独立 MCP SDK。浏览器测试覆盖中英文、手机/桌面下创建授权、确认和撤销；无需生产或客户数据。

OAuth/PKCE、专用 CLI/SDK、Webhooks、更广的 Knowledge/Protocol 编辑及附件访问属于后续独立范围，需继续复用统一授权和写入边界。
