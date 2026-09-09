# 本地适配器源码开发

本地助手可通过当前配置的 Aira 模型生成真实 Python 源码，构建包含源码的适配包，在已有 Docker 隔离环境中运行**固定测试**，再根据有限长度的失败诊断修正源码。模型代码不会在 Platform 或宿主机上执行。这个流程不会打开仪器软件、扫描工作站、安装或批准驱动、验收设备或启用指令。

这只是 RFC #5 的一个实现阶段，不代表自主设备接入全部完成。原生/视觉 Computer Use、授权的软件探索、各操作系统运维和真实试点仍待完成。首版源码开发只接受只读指令草稿、纯 Python、可信 SDK 和标准库，不向模型开放依赖下载、原生编译、任意工具或物理实验。仍需人工确认资料、指令契约和独立测试。

## 本地准备选定资料

使用维护良好的 POSIX 测试工作站和已存在的真实私有目录（`0700`，祖先路径无符号链接）。按[适配包说明](./instrument-adapter-packages.md)独立获取并校验 Gateway SDK wheel 和预装的摘要固定 Python Docker 镜像。开发目录与 Gateway 运行凭证、运行日志分开；尚不支持 Windows 凭证与 ACL 配置。

若仅需**合成演示**，可从仓库唯一的参考样例生成说明文件，选择一个新的绝对路径：

```bash
node scripts/instrument-authoring-example.mjs /absolute/private/synthetic-spec.json
```

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

在**实验室 → 资源库 → 仪器网关 → 选择网关 → 本地适配器开发**中，有当前 `equipment.service` 权限的 Owner/Manager 导入 `authorization.json`。与本地操作人员比对完整指纹，检查目标设备、资料、源码、测试、许可、模型处理同意、SDK/镜像摘要及限制，填写理由后预览、确认。API 会重新检查成员身份、Restricted 设备访问权及范围；有权管理该设备的人员可查看私有开发历史。开发凭证不能替代运行或安装凭证。

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
