# 已安装适配包调用本地界面执行器

Gateway SDK 的 `InterfaceProcessClient` 将**独立审核并安装的 Python 适配包**接到现有固定浏览器流程后端。通过一次有界的本地标准输入/输出进程调用连接，不新增 HTTP 监听、远程桌面、Shell 接口或第二套 Platform 控制系统。任务不携带代码、URL、控件选择器或新参数值；执行权限仍来自 Platform 权限、预约、准确启用版本、本地检查、租约及持久任务日志。

这补齐了一段软件连接：已安装适配包可以执行选定的[固定流程](./instrument-interface-workflow.md)，把实际读数作为 Instrument Job 结果返回；完成回执丢失后，恢复时**不重新加载驱动、不再启动 Node/Chromium**。参考实现和验收均使用自建模拟 HTML，不代表厂商软件或真实仪器已经通过验收；原生/视觉控制仍待完成，独立的原生只读连接见下文。

## 独立准备运行环境

按独立审核的部署流程安装仓库准确的 Node/依赖版本及 Playwright Chromium。此准备命令不安装或下载任何内容，只选择该版本专用的**无头浏览器**，不使用个人浏览器或已有用户配置。缺失或不支持的 Playwright 目录结构会拒绝，不自动替换。选择已保存的固定流程及已存在、仅所有者可访问的证据目录：

```bash
pnpm gateway:interface-runtime preview \
  --workflow /absolute/private/workflow.json \
  --evidence /absolute/private/worker-evidence
pnpm gateway:interface-runtime prepare \
  --workflow /absolute/private/workflow.json \
  --evidence /absolute/private/worker-evidence \
  --workspace /absolute/private/runtime-descriptors \
  --confirm <已审核的预览摘要>
```

安装后命令为 `airalogy-interface-runtime`。确认前审核完整私有清单：Node 可执行文件、界面源码/包元数据、完整声明依赖目录及解析目标、Chromium 目录/内部链接、准确的流程字节/摘要与证据位置。只计算选定软件的哈希，不收集工作站文档。每个目录最多 20,000 个条目/2 GiB，单文件不超过 512 MiB，清单不超过 2 MiB。文件缺失、新增或变化、外部链接、组/其他用户可写的运行文件、依赖解析或流程变化都会阻止执行；浏览器内部链接不得越出选定目录，也不能跳过后来插入的 `node_modules` 代码。

准备后写入私有 `runtime.json`，以及包含其准确摘要的小型 `config.json`。将**这份配置**作为现有安装绑定的配置文件。流程、源码、依赖、可执行文件或浏览器变化后，须重新准备清单并走绑定/验收/启用审核，不能修改正在使用的清单。准备过程不安装、启用、注册或启动设备。本地源码/运行路径是私有且不可跨机器直接搬用的；另一台机器复用同一适配包，但独立准备并验收自己的运行环境和配置。

**每次**创建子进程前，已安装 SDK 都独立重新核验清单、全部运行文件、依赖解析和流程，哈希过程中也检查取消和时限。这会增加磁盘读取；慢机器可能达到原有身份检查时限而拒绝运行，不能省略校验。子进程重新核对流程字节，原后端继续检查应用身份、初始条件、状态、参数读回及最终成功标准。Node 只收到固定入口和 `probe`/`execute` 请求，执行关联准确 Job UUID；不继承 Gateway/模型凭据、`NODE_OPTIONS`、动态加载注入设置或共享浏览器配置。系统库、内核及同服务账户程序仍是信任边界：**这是完整性固定，不是沙箱，也不能防御同账户恶意代码**。

## 自建源码参考包

参考包仅提供 `interface.workflow.run@1.0.0`，参数为空，执行已选定的固定流程。读取实际身份和初始值，不虚构操作人员在场标记；返回 Job UUID、流程摘要、实际数值及明确的模拟单位/标记，不提交 Record 或升级科学证据。

```bash
adapter_output_dir=$(mktemp -d)
pnpm gateway:package build \
  --manifest apps/instrument-gateway/examples/interface-workflow/manifest.json \
  --factory interface_workflow:create_adapter \
  --file source/interface_workflow.py=apps/instrument-gateway/examples/interface-workflow/source/interface_workflow.py \
  --file tests/test_interface_workflow.py=apps/instrument-gateway/examples/interface-workflow/tests/test_interface_workflow.py \
  --file licenses/LICENSE.txt=LICENSE \
  --output "$adapter_output_dir/interface-workflow.zip"
```

使用独立准备的配置，继续走[包测试、源码审核、未启用安装和验收启用](./instrument-adapter-packages.md)。公开参考包**仅用于模拟，不能用于真实硬件启用**；不得修改模拟标记绕过验收。测试使用临时数据库中另外标明为合成的验收数据来覆盖正式 API 权限流程，这些测试行不是可部署的实机验收记录。

仅做自建软件检查时，可运行 `node scripts/instrument-interface-worker-example.mjs`：创建并操作仓库内置 HTML，准备匹配的私有运行清单；不接受目标/程序覆盖，不调用模型，不操作前台桌面。不要将这个测试命令的自动确认方式复制到厂商部署流程。

## 失败、恢复和验证

通信请求限制为 8 KiB，标准输出/错误各 64 KiB，非阻塞读取管道，拒绝并发和同一客户端内已尝试过的 Job ID；调用时限为 0.1–300 秒。参考包执行最多 20 秒，受管理的身份检查仍受原有外层时限约束。取消、超时、格式错误、跨任务响应或子进程失败均不重试。进程组终止有界，也处理主进程退出而子进程仍占用管道的情况。

终止 Node/Chromium **不代表物理安全停止**。参考包刻意让 `safe_stop` 报错：失败或不确定操作必须保留 Gateway 的停止/核对锁，不能把回执、进程退出或窗口关闭当作真实仪器安全证明。生产厂商适配包仍需独立验收停止和人工接管行为。

测试覆盖源码/依赖/浏览器变化、新增模块（包括原本不存在的更优先解析位置和可选依赖）、解析变化、主动注入的测试凭据/动态加载设置不被继承、非法响应、取消、输出限制、超时/子进程清理、两份独立安装复用、真实无网络容器中的固定测试，以及实际 API/数据库/已安装 Python/Node/无头浏览器执行。丢失完成回执的验收核对仅执行一次，恢复不新增界面进程调用。这些是软件测试，不是实机验证、付费模型质量评测、跨平台安装器、厂商原生控制或系统级沙箱。

## 已安装原生只读适配包

`NativeReadProcessClient` 将已安装适配包接到现有 [macOS 读取定义](./instrument-native-interface.md#审核及复用)后端，使用独立的 `airalogy.native-read-worker-config.v1` 配置、运行清单及请求/响应契约。浏览器流程配置不能选择它，读取定义不能包含动作计划。这是只读软件连接，不代表厂商验收或原生生产控制已完成。

先准备准确的本地助手构建和独立审核的 `airalogy.native-read-definition.v1`。仍需要 Node/依赖；原生执行器不使用 Chromium 或浏览器配置。证据和清单目录应在原生构建目录之外，且仅所有者可访问：

```bash
pnpm gateway:interface-runtime preview \
  --native-read-definition /absolute/private/definition.json \
  --evidence /absolute/private/native-read-evidence
pnpm gateway:interface-runtime prepare \
  --native-read-definition /absolute/private/definition.json \
  --evidence /absolute/private/native-read-evidence \
  --workspace /absolute/private/native-read-descriptors \
  --confirm <已审核的预览摘要>
```

准备阶段只核对源码/助手字节并记录完整构建清单，不执行助手、不枚举应用、不读取界面，也不证明所选进程当前存在。每次调用前，已安装 SDK 独立核对运行文件、助手、依赖解析和定义字节，再由执行器实施原有的准确应用/代码身份、进程生命周期、窗口、唯一控件、身份锚点、隐私和活动会话检查。应用重启后必须重新选择、审核配置并完成正常验收/启用，不能静默附着到新进程。没有 TCC 授权、启动、抢焦点、点击/填写、截图、任意助手操作、模型调用或重试；它仍是可信主机上的进程连接，不是系统沙箱。

`probe` 仅检查准确进程元数据及已有读取权限/会话诊断，不采集窗口内容。`execute` 关联 Job UUID，只返回选定字符串读数及零动作/仅观察标记。可访问性内容是软件报告的文本，**不证明实验完成、物理就绪、单位或科学正确性**。沿用 8 KiB 请求、64 KiB 响应和有界不重试约束；输出超限时失败，不截断。终止助手不会关闭操作者应用，也不证明物理安全停止；不确定任务保留原核对流程。

源码参考位于 `apps/instrument-gateway/examples/native-read`，工厂为 `native_read:create_adapter`，入口为 `synthetic.native-read`。使用同一包构建工具打包源码、固定测试和仓库许可证。它只提供参数为空的 `native.status.read@1.0.0`，读取准确构建内置模拟器的两个静态文本控件，始终返回 `observation_only: true`、`simulation_only: true`。即使通用读取后端能观察其他应用，此参考包也会拒绝。厂商适配包须独立说明映射、固定测试和具体设备资格，不能删除模拟标记来宣称支持。

无需前台的检查覆盖真实 Swift 构建、独立 Python 清单核验、过期预览、虚构进程拒绝、通信/契约/变更，以及真实隔离容器中的固定包测试。完整的已安装读取与 API/回执丢失验收需要**明确授权的图形会话**和已有的可访问性权限：

```bash
RUN_INSTRUMENT_NATIVE_JOB_TESTS=1 node apps/instrument-interface/tests/native-worker-fixture.mjs --installed
RUN_INSTRUMENT_NATIVE_JOB_TESTS=1 node apps/instrument-interface/tests/native-worker-fixture.mjs --api
```

这些测试命令只构建、打开自己的 AppKit 模拟器并在结束后关闭，不接受目标覆盖，不自动设置系统权限。`--installed` 使用两份独立安装的 Python 适配包读取；`--api` 使用临时数据库并检查恢复时不再调用界面进程。公开模拟包仍不能用于硬件启用；API 测试使用另外明确标注为合成的策略样例。未主动选择时跳过图形测试；不能把编译通过报告成原生读取通过。真实厂商/硬件、视觉控制、Windows/Linux 原生后端和系统安装验收仍待完成。
