# macOS 原生界面观察

这是**只读开发后端**，不是生产仪器控制器。只附着到明确选定、已经运行的应用；不扫描已安装软件，不启动厂商软件，不点击、填写、切换焦点、猜坐标、执行脚本、截屏或改变系统权限。Windows/Linux 原生及视觉后端仍需单独实现。

## 准备、审核与采集

要求 macOS 13 及以上、Node 22+、工作区依赖和 Apple Swift 命令行工具。先在新的仅本人可访问目录中构建仓库提供的可信辅助程序：

```bash
pnpm gateway:native build --workspace /absolute/private/native-builds
pnpm gateway:native doctor --build /absolute/private/native-builds/interface-ID/native-build.json
```

使用构建返回的真实 `build_file`。构建同时产生只含合成数据的 AppKit 模拟读数软件，不会打开它。清单固定源码、辅助程序字节和架构；模拟器的 ad-hoc 签名仅检查完整性，不代表厂商信任、公证、可信分发、抵御恶意本机账户的沙箱或仪器验收。

`doctor` 只报告已有辅助功能授权，不弹出授权提示、不改设置。缺少授权时，应由操作者另行决定是否通过系统设置授予，没有绕过路径。实现使用 Apple 的[辅助功能授权接口](https://developer.apple.com/documentation/applicationservices/1459186-axisprocesstrustedwithoptions)和[有界 AX 消息接口](https://developer.apple.com/documentation/applicationservices/1459345-axuielementsetmessagingtimeout)；超时仅影响辅助程序自身，不改变全局权限。

明确选择经过 POSIX 规范化的绝对 `.app` 路径、当前同一用户的 PID 和准确窗口标题。打开厂商软件本身可能初始化设备，必须先获得现场授权；本工具不启动软件，也不授予初始化权限。如有私有区域，另存一份私有 JSON 字符串数组，列出准确的 AX 标识符：

```bash
pnpm gateway:native prepare --build /absolute/private/native-builds/interface-ID/native-build.json --bundle /Applications/SelectedInstrument.app --pid 12345 --title '准确窗口标题' --redact /absolute/private/masks.json --workspace /absolute/private/surveys
pnpm gateway:survey run /absolute/private/surveys/interface-ID/request.json --confirm 已审核的本地摘要
```

准备只读取应用元数据，不读取界面内容。执行前核对私有预览。采集固定应用标识、版本、代码目录完整性、可执行文件和 Info.plist 摘要，以及进程 UID 和启动时间，避免 PID 复用或软件替换后悄悄改变目标。可上传的报告只含应用说明和控件提示，不含本地路径、PID 或构建清单。

采集要求唯一、未最小化且角色与标题匹配的 AX 窗口。额外窗口、对话框、私有遮蔽标识缺失或不唯一、几何信息异常、身份变化、无法读取均停止。勘察请求在观察前保留 `run.started`，禁止重放；拒绝事件只记录固定错误码，不写入系统错误正文。遇到系统返回不一致或暂时不可用的可访问性树，应先核对状态，再决定是否准备新请求，不能改选其他窗口、放宽权限或删除标记当作恢复。

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

内置模拟器包含合成文字、密码字段、可选读取的样本数和普通模拟按钮；手工按钮按“样本数 × 0.42”计算，本后端不按按钮。测试只打开此自建模拟器并关闭自己的进程，验证私有排除、错误选择、过期进程/窗口、禁止重放、离线生成及独立 CLI 读取。在已由操作者授权的图形会话运行：

```bash
pnpm --filter @airalogy/instrument-interface test:native
```

托管 macOS CI 只编译并检查完整性和授权诊断，不打开应用、不授予 TCC；显式要求实际 GUI 测试时，缺少授权会失败，不伪装成通过。生产原生写操作仍需审核后的动作策略、独立安全检查、Gateway 预约/租约/停止集成及真实试点。此阶段接通原生观察，不代表自动化设备接入整体完成。
