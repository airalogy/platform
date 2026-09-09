# 仪器适配包

`airalogy.adapter-package.v1` ZIP 包含实际驱动 wheel、源码、测试、许可证及声明的全部依赖 wheel。它不同于 GUI 重放草稿，绝不通过 Instrument Job 下发代码。构建与检查只需 Python 3.11+，不依赖 AI 或平台凭据。

## 构建并检查合成示例

在仓库根目录选择一个新输出目录：

```bash
adapter_output_dir=$(mktemp -d)
pnpm gateway:package build \
  --manifest apps/instrument-gateway/examples/adapter-package/manifest.json \
  --factory synthetic_reader:create_adapter \
  --file source/synthetic_reader.py=apps/instrument-gateway/examples/adapter-package/source/synthetic_reader.py \
  --file tests/test_reader.py=apps/instrument-gateway/examples/adapter-package/tests/test_reader.py \
  --file licenses/LICENSE.txt=apps/instrument-gateway/examples/adapter-package/licenses/LICENSE.txt \
  --output "$adapter_output_dir/synthetic-reader.zip"
pnpm gateway:package inspect "$adapter_output_dir/synthetic-reader.zip"
```

工具只读取显式选择的文件，不探测工作站、不递归收集。参考构建器直接组装纯 Python wheel，不执行构建后端，不覆盖已有输出。同一输入会产生相同的归档和摘要。安装 SDK 后也可使用 `python -m airalogy_instrument_gateway.package_cli`。

示例只计算合成数值，不连接真实设备。预期结果及失败场景由测试明确给定，不从模型回答反推，更不代表任何真实读数仪已验收。

## 不可变契约

清单记录包 ID/SemVer、入口名、作者和来源声明、许可证、准确 Gateway/Python 兼容版本、设备/软件组合声明、已知限制和文件摘要。每个准确版本的命令需声明输入/输出 Schema、风险、单位、影响、超时、完成条件、停止方式、安全要求及有界输出文件。物理命令重试固定为 `never`。

检查会校验归档大小/数量、跨平台安全路径、大小写冲突、普通文件、准确声明的内容和 SHA-256，并独立检查 wheel 元数据、入口及每条 `RECORD` 摘要。拒绝链接、路径穿越、加密 ZIP、`.pth`、启动钩子及重定位脚本/数据；缺失/多余文件、替换 Gateway SDK 也会失败关闭。包清单不能自行授予安装或硬件权限。

摘要只能证明内容身份，**不能证明作者可信或实机安全**。来源标签、兼容性和包自带测试仍属于声明。依赖固定为随包 wheel 字节，在离线测试时校验兼容性与依赖完整性，不联网解析。原生/操作系统安装器不属于参考构建器，需另行审核安装路径。

## 隔离测试

在获授权的测试工作站使用及时维护的 Docker。独立获取并核验 Gateway SDK wheel 和 Python 镜像，预先安装镜像并固定摘要；不能由待测适配包决定这些信任输入。替换以下占位符：

```bash
pnpm gateway:package test /absolute/path/to/adapter.zip \
  --sdk-wheel /absolute/path/to/airalogy_instrument_gateway-0.1.0-py3-none-any.whl \
  --trusted-sdk-sha256 <独立核验的SDK-SHA256> \
  --image <可信镜像仓库>@sha256:<镜像SHA256> \
  --timeout 60
```

工具不拉取镜像，也不降级为主机执行。容器无网络、主机挂载、设备、Docker socket 或网关凭据；使用非 root 用户、只读根文件系统、移除能力、禁止提权，并限制进程、内存、CPU 与临时空间。wheel 仅在一次性容器中离线安装，依赖检查和非空测试套件均需通过。容器隔离不能防御未修补的内核/运行时漏洞；不可信包应使用独立、及时维护的测试主机。

主机强制 1–300 秒时限并确认容器清理；无法确定终止时报告错误，不伪称安全停止，重试前须处理该容器。诊断输出有长度上限并明确为不可信文本，不能据此执行指令。退出码：0 构建/检查成功或测试通过，1 测试失败，2 输入或沙箱错误。

报告绑定归档、清单、SDK 与镜像摘要，始终标记 `simulation_only: true`、`hardware_authorized: false`。**包自带测试不是独立验收**，可能不完整或不诚实。通过后不会自动上传、安装、启用网关、注册指令或操作设备。

## 未启用的离线安装

独立审核源码和依赖后，本地操作人员可以准备一份**未启用**的安装快照：将已检查的 wheel 字节安装到独立 Python 环境，不调用 pip、不联网解析依赖、不运行构建脚本、不导入驱动，也不操作设备。虚拟环境只隔离依赖，**不是安全沙箱**；这项本地操作不代表平台安装授权、设备绑定或实机验收。

首版仅支持 POSIX 私有目录、纯 Python `py3-none-any` wheel 和无条件精确版本依赖。不支持的标签、依赖表达式、Python 版本或缺失依赖直接拒绝，不自动下载。厂商原生安装程序及 Windows ACL/服务安装仍需独立支持。

选择已存在且权限为 `0700` 的真实绝对目录（包括祖先目录均不经过符号链接）、独立验证过的 SDK wheel，以及明确选择的本地 JSON 配置文件。配置正文不会输出，只在预览和回执中记录摘要。合成示例配置内容为 `{}`。替换以下占位值：

```bash
pnpm gateway:install preview /absolute/path/to/adapter.zip \
  --root /absolute/private/gateway \
  --sdk-wheel /absolute/path/to/airalogy_instrument_gateway-0.1.0-py3-none-any.whl \
  --trusted-sdk-sha256 <独立验证的SDK-SHA256> \
  --config /absolute/private/adapter.json
```

核对目标目录、配置/SDK/包摘要、Python 版本及文件数量和大小。将同一命令中的 `preview` 改为 `install`，追加 `--source-reviewed --confirm-digest <预览摘要>` 后执行。这记录的是**本地操作人员**的审核声明，不冒充平台中的实验室来源批准，也不代替其他管理员授予安装权限。

安装器与已有网关必须使用**同一个** `<root>/state.json` 日志。安装器取得独占进程锁，任何未核对任务（包括未确认停止和待重传回执）都会阻止安装。另设一个日志目录不能保护已经运行的网关；应使用服务实际配置的目录，不能通过换目录绕过正在运行的进程。

每组包/SDK/配置/Python 身份生成独立快照，发布前核对 wheel 内容与回执。重试会再次与独立提供的原始 wheel 字节比对，篡改回执中的哈希也不能绕过。不会覆盖已有快照，**不会更改活动版本、系统服务、命令白名单或网关状态**。中断可能留下私有 `.pending-install-*` 目录，它不是已安装或已启用版本；重试使用新的暂存目录。不要从准备好的环境中手工启动未经验收的厂商代码。

回执明确标记 `platform_authorized: false`、`hardware_authorized: false`、`activation_performed: false`。仅检查本地回执可发现相对于本地元数据的变化，不证明来源可信或远程签名。软件测试在 macOS 及无网络 Linux 容器中明确加载仓库自带合成适配器；不代表任何真实仪器软件或硬件通过验收。

## 后续生命周期

### 私有导入与来源审核

在**实验室 → 资源库 → 仪器网关 → 实验室适配包**中，Owner/Manager 可以选择已在本地测试的 ZIP，预览指令、来源及文件摘要，确认准确内容和实验室保存位置。API 不导入、不构建、不执行驱动代码。文件对实验室成员可读，不公开；不得打包凭据、工作站配置密钥或未经许可的客户资料。

预览绑定当前用户、实验室、导入身份、归档与清单摘要，确认时重新检查内容和权限。同一实验室/包/版本的并发导入只保留一个不可变版本与逻辑 ResearchFile；不同内容必须使用新版本。响应丢失后重试不重复占用配额，也不能恢复已撤销版本。列表支持分页。

下载准确归档，独立检查源码、来源、许可证及依赖。下载复用 ResearchFile 短时令牌、即时鉴权和访问审计。来源批准必须明确勾选确认、填写原因、预览后确认；并发或过期审核会拒绝。仅追加的审核历史保留每次决定。来源批准是组织判断，不是密码学签名，也不能证明包内测试诚实。该版本撤销后不能恢复，但不会卸载本地软件或停止运行中的仪器；相关操作须另行协调。本部分不提供公共目录，也不允许运行时网关凭据访问管理接口。

迁移 `0050_instrument_adapter_packages` 新增版本和审核表。按正常备份部署流程升级，软件验收仅使用可销毁数据库。降级删除目录及审核记录，不删除已有 ResearchFile 归档，更不卸载任何本地软件。

### 平台安装授权与回执同步

迁移 `0051_instrument_device_bindings` 新增设备/网关/版本/配置的精确绑定、短时安装授权及修订审计。按正常备份部署流程升级；降级删除授权记录，不卸载本地软件或逆转物理操作。

配对及源码审核后，在本地准备独立的**安装专用身份**。使用网关服务实际目录和 `<root>/state.json` 日志，不能另设日志绕过运行中的服务。私有请求的父目录须为 `0700`。替换以下占位值：

```bash
pnpm gateway:installation prepare \
  --platform-url https://lab.example.edu/api \
  --lab-id <实验室UUID> --gateway-id <网关UUID> \
  --package /absolute/path/to/adapter.zip \
  --sdk-wheel /absolute/path/to/airalogy_instrument_gateway-0.1.0-py3-none-any.whl \
  --trusted-sdk-digest <独立验证的SDK-SHA256> \
  --config /absolute/private/adapter.json --root /absolute/private/gateway \
  --destination /absolute/private/install-request.json
```

管理器先将新 `aiinstall_` 密钥独占写入 `0600` 私有文件，再输出公开 JSON；不读取网关运行凭据。仅将公开 JSON 粘贴到**仪器网关 → 选择网关 → 设备绑定与安装 → 授权安装**，不要上传私有请求文件。Owner/Manager 还须拥有 `equipment.service` 和适配包 ResearchFile 的读取权限。与本地操作人员比对完整指纹、选择准确设备和匹配的已审核版本，预览摘要与修订后确认。私有文件或额外字段会被拒绝。指纹用于核对请求，不证明物理设备身份或本地主机可信。

授权领取前十分钟有效，领取后开启十五分钟下载窗口。安装器只用安装专用凭据获取指定包，不能调用网关任务接口。API 重新检查当前成员资格、设备权限和修订、来源审核、文件权限及配对身份，并在存储读取后再次鉴权。待处理授权阻止网关启用、凭据轮换和重新配对；**尚未领取**的过期授权解除限制，已经领取的授权即使下载窗口过期，也须核对回执或显式撤销。

```bash
pnpm gateway:installation apply /absolute/private/install-request.json --source-reviewed
pnpm gateway:installation status /absolute/private/install-request.json
```

安装后的 SDK 提供 `airalogy-instrument-installation` 或 `python -m airalogy_instrument_gateway.installation_manager_cli` 同等入口。非回环地址必须使用 HTTPS，禁止重定向，响应有大小与时间限制。配置、SDK、适配包或解释器变更后需重新准备请求。领取、下载、非活动安装和回执发送全程持有运行时日志锁，不导入驱动、不启动服务。

本地快照和不可变回执先持久化，再发送到平台。响应丢失时重复同一 `apply`，核对原始字节后仅补交匹配回执，不重新下载或执行物理命令。下载窗口过期后仍可核对匹配回执，但来源或目标授权撤销后会拒绝。已安装快照缺失或被篡改不会自动修复。服务器仅保存身份摘要、文件数量/大小及完整本地回执的摘要，不保存路径、配置正文或文件清单。本地回执记录安装事实，不是授权证书；平台另外保留授权决定。

刷新页面可查看**已安装，执行状态另行确认**及审计历史。安装回执中的状态描述安装操作，不代表当前运行状态。撤销需预览并核对修订，来源撤销后仍能操作。撤销禁止后续安装访问，不清除已下载文件、不卸载、不停止设备，也不证明设备安全；已下载的本地副本需另行处理。仅安装不会更改活动版本、注册命令、创建预约或 Executor Binding，也不授予硬件权限。

### 安装后的执行边界

待处理安装阻止所属网关及设备的手工执行。**领取**授权后，这些目标进入受管验收路径：安装回执、撤销授权、轮换凭据或改用其他网关均不能恢复旧的手工命令路径。API 在手工启用网关/命令、可用指令查询、任务创建、控制步骤排队、领取和启动任务时执行检查；仍可准备停用的命令定义。停止、失败和结果回执保留可用，以便安全核对；禁止新任务不代表设备已经安全停止。

**领取前**取消或到期的授权不会留下永久执行限制，前提是目标没有其他待处理或已领取的安装。已经领取的历史必须保留，不能删除绑定或通过降级移除检查来绕过。没有进入受管安装的既有设备保留手工路径。

下文的受管活动版本提供独立执行路径。仅安装仍然只准备非活动副本；来源审核、独立验收、平台启用授权和本地启动分别确认。软件测试使用合成夹具，不是已认证的真实仪器试点。

### 独立验收记录

迁移 `0052_instrument_qualifications` 新增人工验收记录。进入安装的“检查与审核 → 设备验收”，填写已核实的设备身份、固件/软件/驱动/操作系统版本、验收时间和一年以内的有效期，从已安装包中选择准确命令。逐条记录设备身份、输出与单位、完成判据的独立检查方式、预期与实际观察；有状态变化的受控命令还须检查参数读回、安全停止、人工接管与联锁。各检查明确标记通过或失败，失败观察仍可保存，但不视为验收通过。

默认仅模拟验证。包自带测试及声明 `simulation_only: true` 的命令不能产生实机资格；实机报告须明确确认测试已另行授权、已完成且经过独立人工审核。这是可追责的组织验收声明，不是自动验证、职业认证或发起新测试的授权。API 不接触设备；受管运行时将驱动的新观察与验收者记录的目标比对，依赖已审核驱动的诚实实现，不是密码学硬件认证。

接口前缀为 `/instrument-installations/{binding_id}`：`GET /qualification-context`、`GET /qualifications`、`POST /qualifications/preview`、`POST /qualifications`，以及 `POST /qualifications/{id}/revoke/preview` / `/revoke`。范围为 `simulation`、`read_only` 或 `controlled`；证据来源为 `manual_observation`、`independent_test` 或 `package_self_test`。在现有 Owner/Manager 及设备管理权限之外，单独要求 `equipment.qualify` 能力；保管或预约权限不自动获得验收权。全流程不依赖 AI。

确认固定操作者、报告、设备修订、已批准包、准确包/SDK/配置/解释器描述、安装回执、所选命令契约及可选的 Lab ResearchFile 证据摘要，并重新检查权限与来源状态。证据引用不会扩大访问权；权限丢失后隐藏私有明细，仍保留可撤销的历史条目。表单直接保存独立观察，API 也支持关联已有私有 ResearchFile，不必虚构 Paper 或 Protocol。

报告不能编辑或静默覆盖，相同确认重试返回原记录，纠正须新增报告。撤销保留原始观察和操作者/时间/原因，不可恢复，并支持相同回执重试。到期、安装撤销、Resource/Gateway/来源变化、安装元数据变化或证据缺失都会影响当前有效状态。安装、验收、活动版本授权和真实运行是不同状态；有效验收不会自行注册命令或启动驱动。

### 活动版本、本地启动与回退

迁移 `0053_instrument_activations` 新增不可改写的活动版本授权与任务固定关系。通过正常备份后的部署流程升级；降级删除授权及执行审计，不删除本地文件、不停止服务或物理操作。存在运行中/未核对任务时禁止降级，不能以降级绕过受管限制。

在“检查与审核 → 活动版本授权”中，选择当前安装的有效实机验收、已覆盖的准确命令、早于验收到期的授权有效期及原因。预览设备/软件身份、来源/配置/SDK 摘要、命令修订和原授权后确认。要求当前 Owner/Manager 身份以及 `equipment.service`、`equipment.qualify`、`equipment.activate`；持续检查 Restricted 来源/证据访问权及批准者账户与权限。每个网关和设备至多有一个未撤销授权，仅模拟验收不能启用设备。

确认仅启用已批准的命令契约及网关，每次选择均递增命令修订，包括回退到相同字节。已领取、运行中或停止未确认的任务阻止版本切换；旧排队任务会拒绝执行，不能继承新授权。相同确认重试只返回原结果，不重新启用已撤销或已替代版本。回退时在安装历史中选择旧绑定，在来源与验收仍有效的前提下重新预览确认，绝不恢复旧令牌。

本地操作者还需独立预览启动影响。保留原始包、SDK、配置、私有安装请求与已配对运行凭证；从独立可信的 SDK 启动，替换下列占位内容：

```bash
pnpm gateway:activation preview \
  --request /absolute/private/install-request.json \
  --credentials /absolute/private/gateway.json --activation <Activation-UUID>
pnpm gateway:activation run \
  --request /absolute/private/install-request.json \
  --credentials /absolute/private/gateway.json --activation <Activation-UUID> \
  --confirm-digest <local-startup-preview-digest> --startup-authorized
```

已安装 SDK 提供 `airalogy-instrument-activation`。预览仅读取明确选定文件及签名授权，不导入驱动；**驱动启动可能初始化设备**，因此首次领取任务前也必须取得现场确认。本地启动器在日志锁内重新核对原始 wheel、解释器、配置、目的地、平台/实验室/网关身份与回执；通过 `-I -S -B` 启动干净解释器，在可信标准库之外只加入已核验安装目录，避免误用宿主同名插件或启动钩子。这**不是不可信代码沙箱**：已审核驱动拥有进程账户、设备权限、网络及配置的密钥访问能力。使用最小权限服务账户并另行审核操作系统权限，平台不安装或远程启动系统服务。

受管驱动必须实现 `identity()`，即时读取 `identity_reference`、`firmware`、`application`、`application_version`、`driver_version`、`os_version`，与验收目标逐项精确相同。观察限时五秒，超时停止运行器而不是重试未知控制器状态。在确认、预检与执行前检查身份，同时保留已有联锁预检；身份或权限变化后仍须允许停止与回执恢复。此接口不意味着已实现通用厂商设备身份发现。

手工任务、Aira 批准任务和控制会话步骤均固定活动授权、命令及 Resource 修订，并签入任务包。领取和启动必须提交本地选定的授权固定值；已有进程不跟随新活动指针，也不热加载驱动。授权到期、来源/证据撤回、验收撤销及批准者权限变化阻止新执行，并在运行中任务的下一次心跳请求停止。这不是急停或实时联锁；离线设备仍依赖本地心跳丢失处理与设备专用安全机制。

保留签名 `activation-<UUID>.json`、原安装及私有任务日志。未完成任务恢复使用相同 preview/run 命令，加 `--recover` 并指定原授权 ID；此模式不获取新授权、不领取任务，只执行已有的幂等安全停止/结果核对。撤销不封锁经过鉴权的停止与结果回执。凭证已轮换/不可用或原文件缺失时必须由操作者核对，不能删除日志；原进程尚在停止时不能卸载或更换设备。

管理接口为 `GET/POST /instrument-installations/{binding_id}/activations`、`POST .../activations/preview`、`POST .../activations/{id}/revoke/preview` / `/revoke`；本地运行时读取 `GET /instrument-gateway/v1/activation`，领取/启动携带准确的 `activation` 固定值。共享 `activation_contract.py` 通过现有同步命令生成 API 副本。

### 尚未交付

有边界的自主驱动生成、经授权的原生/视觉 Computer Use、受支持操作系统的服务安装仍需实现。真实软件探索、设备安全验收及第二台复用验证需要获授权试点。当前受管执行仅完成 POSIX/纯 Python 软件验证，不等于通用厂商驱动或硬件认证。参见[接入状态矩阵](./instrument-integration.md#状态矩阵)。

标准库契约以 `apps/instrument-gateway/src/airalogy_instrument_gateway/package_contract.py` 为唯一源，生成 API 副本，使用 `pnpm gateway:contract:check` 检查一致性。CI 构建 SDK，并在固定镜像中测试合成驱动、对抗性隔离及超时清理，不将其视为设备认证。

### 本地原始文件接收基础

SDK 提供 `output_contract.py` 及 `output_capture.py` 中的 `CaptureStore`。本地接收库本身不发现适配器、不调用仪器方法、不请求网络、不提交 Record，也不创建 DataAsset；运行时现已将其私有快照接入下述接收契约。仅返回结构化结果的现有指令保留原流程，停止/结果核对入口仍保留。

调用方提供规范任务 UUID、获批上下文摘要，以及准确的输出文件名、类型、大小上限和必需标记，再显式选择绝对本地目录及其相对文件。每项必须包含带时区的实际采集时间、上报的原始单位、转换规则说明和经独立审核的文件写入完成依据。转换规则只作为来源说明，不执行代码。文件名采用跨平台安全格式，拒绝仅大小写不同的冲突，不允许静默遗漏必需文件。本地路径只写入私有日志，不进入可传输的接收清单。

`prepare` 固定源文件身份、大小和内容摘要；`capture` 等待静默窗口，限制复制字节数，对复制过程和第二次源文件读取分别计算摘要，再次比较最初内容摘要及文件/路径身份，不依赖文件系统时间戳的精度。每份文件先持久化摘要，再发布副本；`inspect` 和 `open_output` 会重新校验副本。复制中断、重命名前中断或最终清单写入中断后，只恢复原任务的文件操作，不重做实验。已持久化副本不依赖原文件继续存在，也不受下一次实验复用同名文件影响。尚未持久化的源文件若变化，会明确要求核对，不自动选择新字节或重复实验。

暂存区使用仅当前用户可访问的目录/文件、跨进程锁、字节/任务配额及原子持久化日志。同一时间只允许一个未完成接收，可保留多项已完成结果等待传输，不会自动淘汰或删除。拒绝符号链接、硬链接、特殊文件、其他用户可写入的文件/目录、路径越界、源目录与暂存区重叠及下级文件系统跨越。已完成接收的恢复不要求空余空间或源文件仍可读。必须明确选择真实本地路径；macOS 的 `/tmp` 等符号链接别名不会被跟随。

默认最多声明 16 份文件，单文件上限 2,147,483,647 字节，暂存区上限 4 GiB/100 项任务，静默窗口 1 秒，检查式接收期限 300 秒；元数据另有限额。当前仅针对支持的 POSIX **本地存储**，不覆盖 Windows ACL 或远程/挂载的厂商文件系统；无法用检查式期限抢占阻塞中的系统磁盘调用。运行账号及已审核适配器仍是可信边界：不能抵御同账号恶意代码，也不把“文件稳定”视作实验成功证明。

### Platform 限范围接收契约

迁移 `0054_instrument_outputs` 新增固定接收批次、文件回执与不可变关联历史。须按正常备份部署流程升级，不在验收时修改开发数据库。降级删除接收/关联记录，不删除已经保存的 ResearchFile、DataAsset 或本地副本；有未完成交付时不可降级。

手工/控制会话预览包含准确的 Project 保存位置、文件名与上限、项目成员可见性、草稿资产状态及待确认 Record 关联。Aira 提议必须确认。创建任务时固定获批指令、安装包、配置和设备来源；调用方不能把上传目标改到其他 Lab/Project。接收授权归属预约用户，须持续具备科研执行及 Knowledge 创建权限。

只有支持文件交付的 Gateway 才能在领取时声明 `file_delivery_version: airalogy.instrument-output-plan.v1`；签名任务随后携带 `file_outputs.plan` 与 `file_outputs.destination`。未声明能力时，在领取或开始物理执行前拒绝；不能给旧客户端简单加此字段绕过限制。新版运行时仅在明确配置输出目录后声明此能力。

物理完成后，`/complete` 返回 `files_pending: true`。Instrument Job 已完成，但 Action 保持等待，控制会话及依赖动作不前进。接收入口为 `/instrument-gateway/v1/jobs/{job_id}/outputs`：

1. `POST /capture` 固定共享采集清单；不同内容重试会冲突。
2. `PUT /{output_id}` 只接收已声明的准确文件，要求匹配的 `Content-Length`、声明的 `Content-Type` 与 `X-Airalogy-Content-SHA256`。流式接收和对象存储等待后再次鉴权；摘要不符、超限、撤权或逻辑文件配额不足时不登记资产。
3. 成功上传创建私有 Project ResearchFile 及草稿 DataAsset 版本，保存原始上报单位、时间/时区、服务器接收时间和安装版本来源。重试返回相同身份；底层去重不授予访问权限，也不绕过配额。即使共享文件块被其他文件标为可执行页面类型，仪器原始附件仍以禁止嗅探的二进制附件下载，不内联执行。
4. `POST /finalize` 要求原清单及所有实际采集文件已登记，此后才恢复正常 Action 流转；迟到交付不会重启已取消的 Task。重试不重复创建资产或执行仪器指令。

这些接口同时要求 Gateway 凭据与原任务租约令牌，不是通用文件/Project 权限。启用授权过期或撤销后仍可核对原结果，但 Gateway 凭据或接收用户权限撤销后不可继续。接收不证明科学有效性，不按文件名/时间推断样品，不提交 Record 或覆盖科研证据。

有权用户通过 `GET /research-instrument-jobs/{job_id}/outputs` 查看交付及关联状态。各文件的 `POST /{output_id}/associations/preview` 与确认接口 `/associations` 将预览摘要绑定同一 Project 中的准确 Record 版本/摘要、样品引用及上一关联身份。过期并发操作会冲突，重试不会恢复旧关联；读取时再次检查 Record 权限，受限关联不泄露内容。Record 数据保持原样。

### 审核文件并关联准确 Record

在科研任务的执行记录中，打开产出文件的仪器动作下的“仪器文件”，核对实际交付状态和保存的实验室/项目。采集完成不代表文件已经收齐；此时应恢复原 Gateway 交付日志，不应重做采集。文件保持为项目私有草稿 DataAsset。“下载原件”使用当前文件鉴权并记录审计，原件以附件形式下载，不作为可执行内联预览。

展开“原始文件与来源信息”，核对带上报时区的采集时间、服务端接收时间、上报单位/转换说明/完成依据、SHA-256 和不可变 DataAsset 版本 ID。这些声明及字节校验不代表科学有效性，不能根据文件名或时间推断样品身份。

选择“关联 Record”，再选择同项目中的协议，以 Record 编号或 UUID 搜索并选择准确版本。唯一可用选项会自动继承，大列表支持显式分页；可选样品引用仅保存操作者观察的文字。预览显示 Record ID/版本/内容摘要和原始 DataAsset 版本/摘要。确认只追加关联，不编辑或提交 Record、不将 DataAsset 升为已验证状态，也不删除原关联。“关联历史”区分当前和历史条目，点击 Record 链接进入该准确版本的报告。

读写权限由 API 执行，不依赖隐藏按钮。`GET /research-instrument-jobs/{job_id}/outputs/record-options` 接收 `protocol_id` 以及可选 `q`、`offset`、`limit`（1–100）；包括仅本人 Record 的限制在分页前生效。`GET .../outputs/{output_id}/associations` 按不可变修订分页，对无权访问的 Record/样品明细脱敏。关联要求当前科研执行和 Knowledge 创建权限；有权只读的成员可以查看和下载文件，不因此获得写权限。

确认回执丢失后，重试同一确认，或先“检查保存状态”再编辑。并发变化使旧预览失效，核对后按需重新选择并预览；刷新失败会清除之前显示的文件明细。整个流程不依赖 AI。模拟安装驱动、真实 API/存储及浏览器测试验证的是软件行为，不能代替真实设备和工作站安全验收，仍须完成获授权试点。

### 自动交付与恢复

经独立审核的文件输出适配器，在受管启动的**预览和运行两条命令**中同时增加 `--output-root /absolute/owned/instrument-exports`。真实目录及其本地身份进入确认摘要；不能与 `state.json` 旁的私有 `instrument-output-outbox` 重叠。已安装命令的文件声明必须与签名接收计划完全一致。通用运行时支持 `AIRALOGY_GATEWAY_OUTPUT_ROOT`，但不能借此绕过受管安装授权。

文件命令的 `execute` 返回 `InstrumentResult(result=<普通 JSON 对象>, files=[...])`。每个文件包含上述明确选择字段，以及经审核驱动在**采集过程中、返回前**对已关闭原件计算的小写 `sha256`。运行时不扫描目录猜测文件；可选文件须明确省略，必需文件不能省略。驱动仍负责确认真实完成及原始单位；摘要只证明字节身份，不证明科学有效性。不声明文件的命令仍可返回普通字典。

运行时先持久化结果、原始摘要和文件选择，保持租约并复制原件，再确认物理执行完成。只向固定、鉴权的接收接口传输已落盘且重新校验的快照，不跟随服务端提供的 URL。接收位置、声明、确定性输出 ID、字节/来源及 ResearchFile/DataAsset ID 全部核对后才接受回执。文件仍为草稿科研资产，不自动编辑或提交 Record。

完成、上传或最终确认回执丢失后，使用原活动版本、安装请求、凭证及相同 `--output-root`，通过 `--recover` 继续原交付。完整快照存在后不依赖原件；原目录消失或厂商软件复用同名文件也不会替换快照。该模式**不导入或初始化驱动**，不取得新授权、不领取新任务，仍核对原安装包/SDK/配置。接收权限撤销时保留本地待交付状态，只能在合法恢复权限后继续。无效完成元数据、未保存前原件变化、完成确认前授权已过期、接收快照期间收到停止请求，均须显式核对；删除恢复日志或重做实验不是恢复方法。

只有平台确认所有文件及最终交付后，运行时才清除活动日志。本地原始快照即使已成功交付也不会自动删除，保留策略须另行审核。验证使用临时文件、真实二进制 HTTP、安装后独立进程，以及实际范围权限 API/数据库/对象存储；没有操作厂商软件、仪器或实验室私有文件。
