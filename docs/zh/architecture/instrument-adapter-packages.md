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

## 后续生命周期

实验室私有发布与来源审核、安装计划/回执、准确设备/网关/包/配置绑定、独立验收、回滚/撤销及仪器文件回传仍需受治理流程。真实软件探索及实机验收需要获授权试点。参见[接入状态矩阵](./instrument-integration.md#状态矩阵)。

标准库契约以 `apps/instrument-gateway/src/airalogy_instrument_gateway/package_contract.py` 为唯一源，生成 API 副本，使用 `pnpm gateway:contract:check` 检查一致性。CI 构建 SDK，并在固定镜像中测试合成驱动、对抗性隔离及超时清理，不将其视为设备认证。
