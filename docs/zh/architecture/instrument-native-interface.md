# macOS 原生界面观察

这是**开发后端**，不是生产仪器控制器。勘察及生成的读取定义仍只读，面向明确选定、已运行的应用；另设操作定义，仅允许对**本次构建的自建模拟器**有界填写和按按钮，不允许操作厂商界面。启动软件须单独进行本地单次授权，勘察或 Aira 授权不包含启动权限。不自动发现应用、不猜坐标、不执行脚本、不截屏、不改变系统权限。Windows/Linux 原生及视觉后端仍需单独实现。

## 准备、审核与采集

要求 macOS 13 及以上、Node 22+、工作区依赖和 Apple Swift 命令行工具。先在新的仅本人可访问目录中构建仓库提供的可信辅助程序：

```bash
pnpm gateway:native build --workspace /absolute/private/native-builds
pnpm gateway:native doctor --build /absolute/private/native-builds/interface-ID/native-build.json
```

使用构建返回的真实 `build_file`。构建同时产生只含合成数据的 AppKit 模拟读数软件，不会打开它。清单固定源码、辅助程序字节和架构；模拟器的 ad-hoc 签名仅检查完整性，不代表厂商信任、公证、可信分发、抵御恶意本机账户的沙箱或仪器验收。

`doctor` 只报告已有辅助功能授权，不弹出授权提示、不改设置。缺少授权时，应由操作者另行决定是否通过系统设置授予，没有绕过路径。实现使用 Apple 的[辅助功能授权接口](https://developer.apple.com/documentation/applicationservices/1459186-axisprocesstrustedwithoptions)和[有界 AX 消息接口](https://developer.apple.com/documentation/applicationservices/1459345-axuielementsetmessagingtimeout)；超时仅影响辅助程序自身，不改变全局权限。

`doctor.interactive_session` 还报告控制台/登录、同用户及显示器活动标志，以及系统提供的锁屏标志，不输出用户名或用户 ID。非活动或系统报告锁屏时，启动和 AX 操作以 `interactive_session_required` 拒绝；元数据检查及离线回执恢复仍可使用。这不是身份认证或物理就绪证据：锁屏字段是可选的系统诊断，准确 AX 窗口/角色/焦点检查仍然执行。工具不解锁、不唤醒会话；实际 GUI 验收前应由操作者自行解锁并保持图形会话活动。

明确选择经过 POSIX 规范化的绝对 `.app` 路径、当前同一用户的 PID 和准确窗口标题。打开厂商软件本身可能初始化设备，必须先获得现场授权；勘察准备不启动软件，也不授予初始化权限。需要启动时，使用下述独立确认流程。如有私有区域，另存一份私有 JSON 字符串数组，列出准确的 AX 标识符：

```bash
pnpm gateway:native prepare --build /absolute/private/native-builds/interface-ID/native-build.json --bundle /Applications/SelectedInstrument.app --pid 12345 --title '准确窗口标题' --redact /absolute/private/masks.json --workspace /absolute/private/surveys
pnpm gateway:survey run /absolute/private/surveys/interface-ID/request.json --confirm 已审核的本地摘要
```

准备只读取应用元数据，不读取界面内容。执行前核对私有预览。采集固定应用标识、版本、代码目录完整性、可执行文件和 Info.plist 摘要，以及进程 UID 和启动时间，避免 PID 复用或软件替换后悄悄改变目标。可上传的报告只含应用说明和控件提示，不含本地路径、PID 或构建清单。

采集要求唯一、未最小化且角色与标题匹配的 AX 窗口。额外窗口、对话框、私有遮蔽标识缺失或不唯一、几何信息异常、身份变化、无法读取均停止。勘察请求在观察前保留 `run.started`，禁止重放；拒绝事件只记录固定错误码，不写入系统错误正文。遇到系统返回不一致或暂时不可用的可访问性树，应先核对状态，再决定是否准备新请求，不能改选其他窗口、放宽权限或删除标记当作恢复。

## 应用检查与独立确认启动

`inspect` 只读取明确选定 `.app` 的元数据及同用户匹配进程，不读取窗口内容；对于冲突副本或仍在启动的实例，只报告待核对数量，不附着。输出属于私有数据，其中核对过的 PID 可用于准备新的勘察：

```bash
pnpm gateway:native inspect --build /absolute/private/native-builds/interface-ID/native-build.json --bundle /Applications/SelectedInstrument.app
pnpm gateway:native prepare-launch --build /absolute/private/native-builds/interface-ID/native-build.json --bundle /Applications/SelectedInstrument.app --reason '已获得本地启动授权并审核初始化风险' --workspace /absolute/private/launches
```

得到已核对 PID 后，`gateway:native windows --build 构建清单 --bundle 应用路径 --pid PID` 可显式读取最多八个窗口的标题、角色、准确焦点匹配、最小化/几何标志及前台状态；要求已有辅助功能权限和活动会话，不读后代控件、不截屏、不授予动作权限。窗口标题可能含私有项目/文件名，应保密保存。这样可选择准确窗口而不猜标题。启动身份核对不等于界面就绪；缺失或非窗口 AX 对象必须先核对，不能当作可操作窗口。

准备不启动软件。完整阅读返回的私有 `preview_file`：准确应用/版本/签名、程序与 Info.plist 摘要、运行时、原因、有效期和潜在影响。默认五分钟有效，可配置 30–900 秒。完整性不代表厂商可信或初始化安全。必须另行确认设备启动、网络、资源占用等影响，并且有权运行该软件，才能确认：

```bash
pnpm gateway:native launch --request /absolute/private/launches/interface-ID/request.json --confirm 已审核的启动摘要 --ack-initialization
pnpm gateway:native launch-status --request /absolute/private/launches/interface-ID/request.json
```

辅助程序使用 [Apple 应用启动接口](<https://developer.apple.com/documentation/appkit/nsworkspace/openapplication(at:configuration:completionhandler:)>)；不接收自定义参数、环境、文档或脚本，不强制新实例，不替换成其他安装副本，不请求激活窗口或加入最近项目。这**不是沙箱**：软件/系统仍可能添加环境变量、显示自身界面、自行激活、初始化设备、联网或启动后台服务。不绕过 Gatekeeper；系统安全界面可能仍会出现，工具不会自动关闭或确认它。

执行前再次核对应用、构建、系统及有效期，先持久化 `launch.started` 和启动意图，再发出请求；同一用户跨工作目录的相同应用标识启动会串行保护。已有同标识实例（含另一副本）时拒绝启动。返回后核对程序、应用和进程启动时间，拒绝复用或并发歧义，保留应用运行。辅助程序最多等待 20 秒，父进程限制为 30 秒。超时或丢失回执属于不确定状态，不授权重启或杀掉应用；禁止删除标记来重试。

`launch-status` **离线**读取保留的回执，辅助程序升级或应用退出后仍可查看。`reported_identity_verified` 仅表示启动时核对过身份，不说明当前仍在运行、已就绪或物理安全；`uncertain` 表示已记录发出启动但没有核实回执。应使用当前可信构建的 `inspect` 并与操作者核对；状态查看不启动、切焦点、终止或重试软件。启动不授予界面操作或生产 Gateway 权限，后续勘察仍须单独确认目标、窗口及隐私规则。

## 隐私和语义边界

- 最多 200 个 AX 节点、16 层、64 个候选控件；超限或不支持的树拒绝。
- 默认不读输入框；`--capture-values` 是独立的整窗口输入值采集同意，记录于预览。密码和指定区域始终排除。
- 排除私有后代及可能聚合其值的祖先元数据；私有标识未找到时停止。软件自行提供的标签和静态文字仍可能含研究数据，发送模型前必须检查 `survey.json`。
- 仅受支持的角色及唯一 AX 标识符可成为可定位控件；无标识或歧义控件仅作提示。不猜角色/名称，不降级为序号或坐标。
- 不读取输入控件的标题和描述，避免软件把输入值镜像到其中。当前仅读静态文字和明确同意的文本框/文本区域值。
- 单次 AX 消息超时 2 秒，完整捕获由父进程限制为 30 秒、128 KiB。超时只终止辅助程序，不退出目标应用，也不表示物理设备安全停止。
- 几何信息、标签和读数来自应用自述，不代表像素可见性、原子快照、物理就绪或科学结果正确。

## 审核及复用

报告复用浏览器后端的[勘察与 Aira 审核](./instrument-interface-survey.md) API 和中英文界面。只导入 `survey.json`，不导入本地请求、路径或构建文件。Aira 可解释快照、建议原生辅助功能接入，但不能授予原生操作权限。关闭 AI 后仍可手工审核和生成定义。

```bash
pnpm gateway:survey assemble /absolute/private/surveys/interface-ID/request.json --analysis /absolute/private/reviewed-analysis.json --workspace /absolute/private/drafts
pnpm gateway:native preview --definition /absolute/private/drafts/interface-ID/definition.json
pnpm gateway:native read --definition /absolute/private/drafts/interface-ID/definition.json --confirm 已审核的读取摘要 --evidence /absolute/private/reads --ack-new-read
```

生成时核对保留的采集/分析摘要，写入新的可编辑 `airalogy.native-read-definition.v1`、证据副本和空计划；不要求原应用仍打开。执行则重新核对准确进程及身份文本，仅保存已审核的读数。应用重启或升级后，必须明确准备并审核新目标，再复用映射；旧 PID 不会自动改绑。定义不能新增点击/填写或输入值同意。

## 单独审核的自建模拟器操作

在获授权的图形会话中明确打开构建返回的 `simulator_app` 后，选择其真实 PID。下面的准备只读取元数据，生成可编辑定义、计划与策略文件，不打开或操作应用：

```bash
pnpm gateway:native simulation-template --build /absolute/private/native-builds/interface-ID/native-build.json --pid 12345 --workspace /absolute/private/native-actions
pnpm gateway:native preview --definition /absolute/private/native-actions/interface-ID/definition.json --plan /absolute/private/native-actions/interface-ID/plan.json
pnpm gateway:native run --definition /absolute/private/native-actions/interface-ID/definition.json --plan /absolute/private/native-actions/interface-ID/plan.json --confirm 已审核的操作摘要 --evidence /absolute/private/runs --ack-new-run
```

使用返回的实际路径，审核完整预览，并保持选定模拟器窗口处于焦点。`airalogy.native-interface.v1` 与勘察只读定义独立，声明控件、字面量操作、状态与限额。模板填写两个合成样本、按下模拟按钮，检查 `Complete` 和独立写定的结果 `0.84`，不根据运行读数反推预期值。

可信构建器把自建模拟器的程序与 Info.plist 摘要编入辅助程序；执行还要求准确的同目录应用路径及固定进程。标注“模拟”或使用相同应用标识不能授权其他软件。旧 v1 构建须重新构建；每次原生源码更新后，即使清单格式未变，也须重新构建并审核。清单包含封入的源码及模拟器身份。这仍是操作者拥有的开发工具，不抵御同一账户下的恶意本地代码。

每步先持久化意图，辅助程序重新核对最新快照并持有准确 AX 控件引用，检查窗口焦点及可用性，只执行固定 AXValue/AXPress，然后核对结果与参数。没有抢焦点、任意 AX 操作、脚本或坐标回退。尝试操作后结果缺失或不符合预期，标记不确定并禁止在本会话重试。新运行是明确确认的新操作，**不是恢复**；必须保留证据、先核对状态。关闭会话不退出操作者的应用，也不声明物理安全停止。

内置模拟器只含合成文字、密码字段和可选读取的样本数。测试只打开自建模拟器并关闭自己的进程，验证私有排除、错误选择、过期身份/观察、离线生成、独立 CLI 读取，以及实际填写、按按钮和结果核对。在已由操作者授权的图形会话运行：

```bash
pnpm --filter @airalogy/instrument-interface test:native
```

托管 macOS CI 只编译并检查完整性和授权诊断，不打开应用、不授予 TCC；显式要求实际 GUI 测试时，缺少授权会失败，不伪装成通过。共享的测试专用准备程序仅核对并前置一次准确、已运行的自建模拟器；它不进入安装包、不接受厂商目标，也不在操作被拒绝后重新获取焦点。验收期间请保持该测试窗口在前台。生产原生写操作仍需合格厂商适配器、独立安全检查、Gateway 预约/租约/停止集成及真实试点。自建模拟器操作路径不代表自动化设备接入整体完成，也不代表厂商控制已验收。
