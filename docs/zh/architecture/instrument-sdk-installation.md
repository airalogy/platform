# 安装本地 Instrument SDK

独立程序 `apps/instrument-gateway/bootstrap.py` 将无第三方依赖的官方 SDK 安装到**新的私有目录**，不使用 pip、不执行安装钩子、不提权、不修改全局 PATH、不注册服务。安装不导入 SDK/适配器代码，不配对网关、不打开仪器软件、不启动任务。这是由运维人员确认的 POSIX 安装引导，不是 Windows 安装器或无人值守服务管理器。

## 首先建立信任

准备维护中的 Python 3.11+ 和独立可信、支持所需 attestation 参数的 GitHub CLI。安装引导程序本身必须来自已审核的可信代码副本，或由人员在**执行之前**验证发布的 `airalogy-instrument-bootstrap.py`。程序不能自行证明自身可信。官方公开发布会附带 SDK wheel、安装引导程序和 `airalogy-instrument-attestations.jsonl`；示例版本及未签名本地构建不代表已有可用签名发布。

独立确定准确的稳定版本标签、40 位源码提交和 wheel SHA-256。不使用 `latest`、分支或可变下载地址；文件自己的校验和不是来源证明。该引导只接受 `airalogy/platform` 的 `.github/workflows/release.yml`，不接受任意镜像/fork 签名者或预发布版本；已审核的源码/手工安装路径仍独立保留。

例如，先替换以下示例版本、路径和提交：

```bash
gh attestation verify /absolute/downloads/airalogy-instrument-bootstrap.py \
  --hostname github.com --repo airalogy/platform \
  --source-ref refs/tags/v0.1.0 --source-digest <40-character-release-commit> \
  --signer-digest <40-character-release-commit> \
  --cert-identity https://github.com/airalogy/platform/.github/workflows/release.yml@refs/tags/v0.1.0 \
  --cert-oidc-issuer https://token.actions.githubusercontent.com \
  --predicate-type https://slsa.dev/provenance/v1 --deny-self-hosted-runners
```

引导使用 [GitHub 官方 CLI](https://cli.github.com/manual/gh_attestation_verify) 做密码学验证，固定仓库、工作流、证书身份/签发方、源码引用和提交、签名工作流提交、托管 runner 及 SLSA 来源类型。哈希标识字节，签名证明指定构建来源，不证明软件质量、当前仍获批准或物理安全。须独立核对撤回版本及安全公告，本工具没有自动撤销信息源。

精确的 `--cert-identity` 已经固定工作流和标签。不要同时传入 `--signer-workflow`、`--signer-repo` 或 `--cert-identity-regex`；这些身份选择参数在 CLI 中互斥。

## 预览与安装

选择现有、由当前专用账号持有、无符号链接祖先的 `0700` 父目录，以及一个**尚不存在**的子目录。SDK 版本、开发工作区、运行凭据/日志、原始数据分别存放。父目录含 `gateway.json` 或 `state.json` 时拒绝操作；这只是防误用检查，不证明其他账号/位置可安全修改。

```bash
python3 -I -S -B /absolute/downloads/airalogy-instrument-bootstrap.py preview \
  --wheel /absolute/downloads/airalogy_instrument_gateway-0.1.0-py3-none-any.whl \
  --wheel-sha256 <independently-verified-wheel-SHA256> \
  --release-tag v0.1.0 --commit <40-character-release-commit> \
  --destination /absolute/private/sdk-installs/sdk-0.1.0 \
  --online-verification
```

预览只读取选定文件和可执行文件身份，不建文件、不访问 GitHub、不声称已验证来源。核对位置、版本/提交、摘要、Python/验证器身份及联网选择后，保留**全部相同输入**，将 `preview` 改为 `install`，追加 `--install-authorized --confirm-digest <preview-confirm-digest>`。确认时重新检查输入，验证准确的 wheel 副本，然后独占创建目标目录。不下载依赖、不执行包安装脚本；拒绝 `.pth`、原生 wheel 和有外部依赖的 SDK。

在线验证由可信 CLI 联系 GitHub/Sigstore，不上传实验室资料、不联系 Platform 或设备。离线安装去掉 `--online-verification`，同时提供 `--bundle <selected-attestations.jsonl> --trusted-root <trusted-root.jsonl> --trusted-root-sha256 <independently-approved-root-SHA256>`。管理员可在可信联网主机使用 `gh attestation trusted-root` 获取信任根，再通过可信方式传送并独立批准。不能因为信任根与包一起提供，就自动信任它。在线/离线选项不能混用。缺失或无效证明、验证主体不符、验证器超时或参数不支持都会停止安装，没有未签名降级通道。

限额：wheel 64 MiB、展开 SDK 128 MiB、2,048 个包文件、证明/信任根/验证输出各 4 MiB、验证器 90 秒。保留原始 wheel、验证输出、准确展开文件、引导程序和带时间的最终 `receipt.json`，文件及目录写入同步后才报告成功。不复制本地凭据、不安装厂商适配器、不选择活动版本。

## 启动、检查与维护

明确启动时重新核对保留文件摘要，拒绝缺失/意外文件，要求 Python 与安装时固定的解释器一致。只能启动列出的 SDK 入口，使用独立标准库 + SDK 导入路径，不加载 site 钩子、不写入字节码：

```bash
python3 -I -S -B /absolute/private/sdk-installs/sdk-0.1.0/airalogy-instrument-bootstrap.py \
  launch --destination /absolute/private/sdk-installs/sdk-0.1.0 \
  -- setup --root /absolute/private/gateway-service

python3 -I -S -B /absolute/private/sdk-installs/sdk-0.1.0/airalogy-instrument-bootstrap.py \
  launch --destination /absolute/private/sdk-installs/sdk-0.1.0 \
  -- author serve --workspace /absolute/private/adapter-development
```

运行/开发目录须分别存在且为私有目录。之后继续[接入配对](./instrument-integration.md#本地浏览器接入向导)或[源码开发](./instrument-source-authoring.md#本地浏览器开发向导)。另有 `pair`、`package`、`installation`、`activation` 和 `gateway` 固定入口，原有授权和安全检查不变。启动执行入口是另一项明确运维操作，不会因安装或打开向导而发生。

`inspect --destination <installed-directory>` 重新核对本地文件。它读取本地回执，**不**重新建立密码学来源证明或确认进程活跃状态。成功后用原安装输入重试会核对保留字节并返回同一安装，不再次联网。没有最终回执或文件已改变时保持“不完整/无效”：保留检查，不覆盖、不静默修复。崩溃可能留下私有的不完整目标目录，工具不自动删除它或原始数据。

更新使用独立版本目录和新的来源核验，不变更活动指针、不原位替换；Python 更新同样要求新的审核安装。不删除仍被进程使用的 SDK，先确认实际进程、作业、物理停止状态与留存要求。服务托管、自动更新/卸载、OS ACL 安装器及恶意同账号程序的防护不在本引导范围内。哈希和私有文件权限不能防御可同时改写程序与回执的恶意管理员/同账号程序。

## 验证证据

普通 SDK CI 覆盖错误/篡改输入、固定验证参数、输出限额、中断、幂等，以及实际构建 SDK 的隔离启动和 HTTP 鉴权。正向本地测试注入验证器响应；另用真实 GitHub CLI 拒绝未签名离线样例。官方公开发布 CI 会进一步使用真实证书/源码策略核验刚签发的 wheel，并启动两个空白本地向导，通过后才附加发布产物。真实发布门禁须在对应版本实际通过，不能据此声称未运行的发布、真实设备电脑或仪器安全已验收。
