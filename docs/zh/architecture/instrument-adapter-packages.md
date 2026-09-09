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

### 尚未交付

平台授权的安装计划与回执同步、准确设备/网关/包/配置绑定、独立验收、活动版本切换/回滚/撤销及仪器文件回传仍需受治理流程；本地未启用安装回执不能代替这些门槛。真实软件探索及实机验收需要获授权试点。参见[接入状态矩阵](./instrument-integration.md#状态矩阵)。

标准库契约以 `apps/instrument-gateway/src/airalogy_instrument_gateway/package_contract.py` 为唯一源，生成 API 副本，使用 `pnpm gateway:contract:check` 检查一致性。CI 构建 SDK，并在固定镜像中测试合成驱动、对抗性隔离及超时清理，不将其视为设备认证。
