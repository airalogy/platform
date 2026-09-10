# 本地适配器源码开发

本地助手可通过当前配置的 Aira 模型生成真实 Python 源码，构建包含源码的适配包，在已有 Docker 隔离环境中运行**固定测试**，再根据有限长度的失败诊断修正源码。模型代码不会在 Platform 或宿主机上执行。这个流程不会打开仪器软件、扫描工作站、安装或批准驱动、验收设备或启用指令。

这只是 RFC #5 的一个实现阶段，不代表自主设备接入全部完成。已提供独立授权的[有界浏览器探索](./instrument-interface-exploration.md)、[限定范围的 macOS 发现/观察与自建模拟器动作](./instrument-native-interface.md)，以及[正式 HTTP 接口读取](./instrument-http-interface.md)。厂商原生/视觉控制、跨平台运维和真实试点仍待完成。源码开发支持固定的只读及低/中/高风险指令契约，非只读源码须单独明确批准开发。仍只允许纯 Python、可信 SDK 和标准库，不向模型开放依赖下载、原生编译、任意工具或物理实验；资料、指令契约和独立测试仍须人工审核。

## 本地浏览器开发向导

已安装 SDK 提供本机浏览器向导，完成准备、授权交接、有界运行、协作式暂停及草稿下载：

```bash
airalogy-instrument-authoring serve --workspace /absolute/private/development
```

源码仓库使用 `pnpm gateway:author serve --workspace /absolute/private/development`。选择已存在、当前账户专用的 `0700` POSIX 目录，**与 Gateway 服务目录分开**；包含 `gateway.json` 或运行日志 `state.json` 的目录会被拒绝。这不隔离同一 OS 用户下的恶意程序，应使用专用最小权限账户及维护良好的隔离测试主机。复用[本地接入服务](./instrument-integration.md#本地浏览器接入向导)的一小时私有地址、Host/Origin 校验及无远程资源策略，不自动打开应用或运行任何工作。Windows 安装、原生依赖仍未支持。

1. 选择下文定义的已审核规范及独立可信 SDK wheel。仅复制到本地私有目录：规范 128 KiB、SDK 64 MiB、保留副本 64 个 / 256 MiB。填写准确平台/网关/设备、已安装且摘要固定的 Docker 镜像及调用/时限。预览展示固定资料、契约、测试和位置，不联网、不调模型、不创建凭据；五分钟单次确认重新检查字节，再保存独立开发凭据和请求。
2. 下载**私有授权文件**，在 Platform → 仪器网关 → 准备适配包 → 开发源码导入。它包含选定私有资料，不含 bearer 凭据。比对完整指纹，独立批准资料处理和限额；不要上传 `request.json`，模型可能在外部处理。向导不能批准自己的授权。
3. 回到**查询授权并预览运行**，核对当前准确请求后确认。复用的开发协调器在线程中生成源码、运行固定测试及恢复回执，与 CLI 共用独占开发锁。进度查询只读本地状态，不调用模型、不启动新运行。刷新恢复已保存会话，不执行工作；有历史时默认收起新建输入，优先恢复原工作。
4. **暂停本地开发**在有界步骤之间生效；当前模型/测试步骤及回执可能先完成，不撤销平台授权、不停止仪器。关浏览器标签不等于暂停。Ctrl-C 请求暂停并关闭向导，但进程退出可能留下中断测试或不确定网络回执。重启后，旧运行记录只是历史，不证明进程已停止。用原请求恢复，共享锁会阻止与原 CLI/向导同时运行，不删除日志绕过。
5. 中断测试需单独选择核对、预览明确容器身份并确认。只核对预览过的测试；新出现的不确定测试须重新预览。中断记录为失败，不当作通过，不影响物理仪器任务。
6. 查看保留输入、本地运行结果及候选报告。只有本地通过且摘要校验成功的草稿 ZIP 可下载，失败候选保留报告。下载再次比对候选/报告/包身份，不能选择任意文件或凭据。客户端报告不是真机资格或可信执行证明；审核源码、依赖、保密和许可证后，再导入平台，交给独立安装向导。

会话和结果保存在普通私有文件中，不依赖聊天或浏览器存储。会话枚举最多 100 个、目录最多 1,000 项；每会话产物/历史最多扫描 1,000 项。不自动删除副本或报告，清理前核对引用和保留要求。浏览器不暴露私有错误详情，高级诊断仍使用原 CLI。向导不编造设备语义、独立预期、说明书或操作许可，也不替代真实试点。

浏览器/API/数据库验收使用自建合成规范，仅注入外部模型响应及沙箱结果；另以真实隔离容器测试错误/修正源码和固定测试。这两类验证均不证明付费模型或真实仪器部署成功。

## 本地准备选定资料

使用维护良好的 POSIX 测试工作站和已存在的真实私有目录（`0700`，祖先路径无符号链接）。按[适配包说明](./instrument-adapter-packages.md)独立获取并校验 Gateway SDK wheel 和预装的摘要固定 Python Docker 镜像。开发目录与 Gateway 运行凭证、运行日志分开；尚不支持 Windows 凭证与 ACL 配置。

若仅需**合成演示**，可从仓库参考样例生成说明文件，选择一个新的绝对路径：

```bash
node scripts/instrument-authoring-example.mjs /absolute/private/synthetic-spec.json
```

添加 `--http-reader` 可选择正式 HTTP 参考接口及其独立固定的样本/Schema 测试。模型提示会说明可复用的 SDK 通信工具，但不授予联网权限；应选择确实包含 `HttpReadClient` 的准确 SDK wheel。两种示例生成器都不访问设备或模型。

也可添加 `--export-reader`，选择[已完成导出文件采集](./instrument-export-interface.md)的公开契约和独立合成文件测试。须使用包含 `ExportReadClient` 的准确 SDK wheel；这不会授权读取真实导出目录，也不会自动生成厂商完成桥接。AI 关闭时仍可使用手写含源码包。

### 受控指令源码草稿

同一源码流程可为低/中/高风险指令生成实现草稿，但不授予执行权限。固定的风险、本地确认、联锁、完成及停止要求继续由共享包校验器检查：中/高风险不得省略本地确认，高风险不得省略现场人员和急停要求。Aira 不能降低这些条件或修改独立测试。这些是输入中的要求声明，不是 AI 安全评级，也不证明生成实现已经满足要求。

授权前，Platform 直接展示准确指令/版本、声明风险、副作用、完成依据、停止和本地安全契约。任何非只读指令的预览与确认，都须独立于模型资料处理同意，携带严格布尔值 `controlled_source_consent: true`。改变输入会清除界面确认并使预览失效，服务端也独立执行校验；授权审计记录该确认及指令审阅内容。已有只读请求不需要新确认，不会扩大指令权限，原规范仍不可变。历史和本地准备/运行预览保持同样的“仅源码开发”边界，不增加数据库迁移或执行凭据。

可使用固定独立假通信接口测试自建有状态参考实现：

```bash
node scripts/instrument-authoring-example.mjs /absolute/private/controlled-spec.json --controlled-reader
```

须选择包含本支持的准确可信 SDK 构建，并配套更新 API/前端。参考包位于 `examples/controlled-reader`，工厂为 `controlled_reader:create_adapter`，AI 关闭时也可手工构建。它配置内存控制器、读回参数、启动一次、观察完成并核对单位/数量；独立测试提供不同结果，模拟控制权改变、取消、启动回执丢失及停止确认失败。控制器不接收生产配置、没有真实通信接口；一个新控制器代表一次模拟采集，不提供物理复位/重启指令。输出契约始终固定 `simulation_only: true`，不能用于真实设备的启用验收。

实际 Docker 验收会先拒绝故意重复启动的源码，再让修正源码通过不变的独立测试，并验证同一回执恢复不重跑候选代码。API/本地浏览器测试另外使用合成模型/测试响应，核对确认、审计、有界修正、取消及开发凭据不能访问执行指令。这些是软件测试，不是付费模型能力基准或厂商实机安全验收。

真实受控实现仍须有独立明确的参数读回、完成、接管和设备特定停止语义，以及独立测试。缺少信息须返回 `missing_information`，不能编造接口、空操作停止或把模拟改名为硬件。测试通过的草稿仍须源码审核、准确安装、覆盖受控指令的非模拟实机验收、启用授权、预约及本地启动/操作条件。此改动不授权模型或开发进程接触真实设备。

如需自建 HTTP 参考，可改用 `--http-controlled-reader`，使用[独立配置的 JSON 控制后端](./instrument-http-control.md)、准确 SDK `job.job_id` 关联、独立参数/完成读回和模拟停止确认。固定离线测试使用假客户端；源码开发不会连接服务或设备。

真实说明文件是 JSON，字段固定为 `goal`、`manifest`、`factory`、`materials`、`tests`、`licenses`、`initial_sources`。manifest 是尚未构建的适配包模板（`files: []`、`provenance.kind: "aira"`、无已测试真机声明）；factory 固定为 Python `module:function`。materials 是 1–16 项显式选定的 `{name, text}`，名称不含本地目录；测试、许可和初始源码分别是 `tests/*.py`、`licenses/*`、`source/*.py` 到文本的映射。初始源码可以为空，总上下文最多 128 KiB。这里不执行 PDF/OCR、目录采集或软件发现；需要时请在许可范围内提供明确审阅过的文本摘录。

准备前请检查机密、个人数据、分发许可及模型处理权限。已知 Platform 凭证格式会被拒绝，但没有任何此类扫描能够保证所有秘密都已清除。

可以先用独立确认的[浏览器界面后端](./instrument-browser-interface.md)取得文字观察，在本地审核后明确加入 `materials`。这是人工、显式的资料转移；源码助手不会因此获得浏览器控制权，界面内容也不会自动发送给模型。

```bash
pnpm gateway:author prepare \
  --workspace /absolute/private/development \
  --platform-url https://lab.example.edu/api \
  --gateway-id <Gateway-UUID> --resource-id <equipment-Resource-UUID> \
  --spec /absolute/private/selected-spec.json \
  --sdk-wheel /absolute/path/to/airalogy_instrument_gateway-0.1.0-py3-none-any.whl \
  --trusted-sdk-digest <independently-verified-SDK-SHA256> \
  --image <trusted-image-repository>@sha256:<image-SHA256> \
  --max-iterations 3 --duration-seconds 900 --timeout-seconds 60
```

准备命令不访问网络，会快照所选文本、生成独立的 `aiauthor_` 凭证，并创建新的会话目录和 `0600` 私有文件。`request.json` 包含本地凭证及 SDK 路径，**绝不能粘贴到 Platform、聊天或 Issue**。`authorization.json` 不含 bearer 凭证，但包含实验室私有资料，**不是公开文档**。命令只输出路径和指纹，不输出秘密或资料正文。安装后的 SDK 可使用 `airalogy-instrument-authoring` 或 `python -m airalogy_instrument_gateway.authoring_cli`。

## 先授权，再运行

在**实验室 → 资源库 → 仪器网关 → 选择网关 → 准备适配包 → 开发源码**中，有当前 `equipment.service` 权限的 Owner/Manager 导入 `authorization.json`。与本地操作人员比对完整指纹，检查目标设备、资料、源码、测试、许可、模型处理同意、SDK/镜像摘要及限制，填写理由后预览、确认。API 会重新检查成员身份、Restricted 设备访问权及范围；有权管理该设备的人员可查看私有开发历史。开发凭证不能替代运行或安装凭证。

每次授权允许 1–5 次模型调用，最长 30 分钟，固定模型及网关/设备版本。每次模型响应最多 60 秒、64 KiB，本地测试最多 1–120 秒；沿用现有模型用量上下文记录操作身份。这些是调用、时长和输出限制，**不是费用金额上限保证**。配置的模型可能由外部服务提供。AI 关闭或不可用时，手工适配包创建、测试、导入和治理流程仍可使用。

```bash
airalogy-instrument-authoring run /absolute/private/development/<session-UUID>/request.json
airalogy-instrument-authoring status /absolute/private/development/<session-UUID>/request.json
```

助手持有独占开发锁。API 在访问模型前持久化唯一轮次，响应丢失时不会重复发起该次付费调用。模型只能返回完整 `source/*.py` 源码映射、总结、假设和缺失信息问题；不能修改固定测试、manifest、factory、许可、指令契约和安全效果。调整说明需要重新准备请求并授权。不可信资料和测试诊断不能授予工具权限；结构校验也不意味着代码可信。

本地构建器不导入源码，生成实际、不可变的 ZIP/wheel，再在非 root、无网络、无宿主/设备挂载、资源受限的环境中执行固定测试。失败可在原授权限制内继续修正；缺少设备语义时提出问题，不编造驱动成功。SDK/镜像必须匹配固定摘要；API 通信在非回环地址要求 HTTPS，拒绝重定向并限制响应大小。

## 结果与恢复

每轮保留私有源码提案、可构建时的 ZIP 和测试回执。Platform 保存私有源码提案、模型操作 ID 和匹配的客户端诊断，中英文界面提供历史与取消。固定测试通过后返回 `draft_tested`、ZIP/报告路径和下一步。它**不是源码批准、可信执行证明或真机验收**：本地客户端可伪造报告，模型源码也可能不诚实或测试不足。必须独立审核，并继续现有的[导入、安装、验收与启用流程](./instrument-adapter-packages.md)。最终包是可编辑、可版本化的普通草稿，不仅存在于聊天中。

网络响应丢失后继续**同一份**请求，保存的产物只校验、不覆盖，已完成测试不会因重发回执而重复执行。若本地测试中断且无持久化报告，助手会停下并显示日志中记录的准确容器身份。核查后使用 `run ... --reconcile-test`，仅停止该会话记录的测试容器，并确认其已不存在；无法确认终止则停止流程。确认中断后记录为失败，绝不记为通过，再允许下一轮。这不是物理仪器急停。

取消会阻止新调用及迟到的模型输出，不会删除资料、结束已运行的本地测试或停止仪器。已保存的测试回执可在过期/取消后对账，但仍要求当前范围权限及准确凭证。过期或发生范围变化的授权不能发起新模型调用。本阶段不自动清理材料，请按实验室政策管理本地和服务端保留的数据。

迁移 `0055_instrument_authoring` 增加独立开发会话和轮次。请按正常备份部署流程升级；验收仅使用可丢弃数据。降级删除开发记录，不删除本地文件、卸载软件或撤销物理动作。合成 API/模型流测试验证事务与恢复；真实 Docker 测试使用一份故意错误的源码和修正后的源码，对同一套固定测试验证失败到通过。上述测试不代表付费模型能力或真实设备验收。
