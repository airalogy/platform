# 仪器 HTTP 只读接口

Gateway SDK 提供可复用的 `HttpReadClient`，供手写或 Aira 起草的适配器访问**明确选定、独立审核过的 GET/JSON 接口**，避免每个驱动重复实现网络通信。它不是设备发现、通用 HTTP 工具、网络沙箱或设备访问授权。GET 也可能产生物理效果，批准访问前必须确认接口语义。

## 配置与授权边界

审核过的适配器固定操作名称、路径、查询字段和响应限制；本地操作人员另行选择服务地址、数字 IP 和仪器专用凭证。任务参数不能指定 URL、路径或认证请求头。

配置只接受以下字段，示例地址不能直接用于真实仪器：

```json
{
  "schema": "airalogy.http-read-config.v1",
  "origin": "https://reader.example.test:443",
  "address": "192.0.2.20",
  "allow_plaintext": false,
  "headers": {}
}
```

真实配置必须保存为服务账号所有的绝对路径 `0600` 普通文件，位于无符号链接祖先的 `0700` 私有 POSIX 目录。不得将真实地址、令牌或配置放入模型资料、适配包、Issue 或任务参数。只允许明确的 `Authorization`、`X-API-Key` 请求头；使用仪器专用凭证，不能使用 Platform 网关、开发或安装令牌。会拒绝已知 Platform 令牌格式，但不能据此保证所有秘密都已排除。安装会固定配置摘要；修改配置必须重新走已有安装与启用审核。

连接固定到选定 IP，不通过 DNS 选择目标。origin 用于 Host 请求头、TLS SNI 和证书域名校验；若 origin 是 IP，其值必须与选定 IP 一致。TLS 使用 Python 默认受信 CA 配置并校验证书和域名，不提供跳过验证的选项；管理员可以在工作站维护私有 CA 信任库。包括回环地址在内，明文 HTTP 都需明确设置 `allow_plaintext: true`：它不保障凭证保密或服务身份，需要单独批准测试/网络策略。不使用环境代理、不跟随重定向、不保留 Cookie、不刷新凭证、不自动重试。底层机制参见 Python 官方的 [HTTP 客户端](https://docs.python.org/3/library/http.client.html)和 [TLS 上下文](https://docs.python.org/3/library/ssl.html#ssl.create_default_context)说明。

## 适配器调用方式

```python
from airalogy_instrument_gateway.http_read import HttpReadClient, HttpReadOperation

client = HttpReadClient.from_file(config_path, {
    "identity": HttpReadOperation("/v1/identity", max_response_bytes=4096),
    "result": HttpReadOperation("/v1/result", ("sample_id",), 4096),
})
# 构造时只校验私有配置，不建立连接。
# 以下调用只能发生于单独授权的身份检查或任务执行中：
response = client.get("result", {"sample_id": "sample-A"},
                      timeout_seconds=3, stop_event=stop_event)
```

上述路径仅属于合成参考程序，不是厂商 API。路径为固定 ASCII 路径段，不接受模板或编码后的目录穿越；查询字段必须与审核集合完全一致，值会限长并编码。同一客户端只允许一次调用。期限为 0.1–30 秒；取消监控会中断本地网络读写，包括卡住的响应头和正文。操作系统调度不是硬件实时性保证。

只接受 HTTP 200、未压缩的 UTF-8 JSON 对象，正文限制为 1 字节至 1 MiB，默认 64 KiB。重复键、非有限数、过深嵌套、含糊的消息长度、截断和超限均失败。适配器仍须独立校验输出 Schema、样本身份、单位和科研完成条件。`response.raw` 是收到的原始 JSON 字节，`sha256` 标识这些字节，`received_at` 是本地收件时间，**不是采集时间或科研成功证明**。该工具不会上传原始文件或创建 DataAsset，需要时使用已有的[显式文件回传契约](./instrument-adapter-packages.md#自动交付与恢复)。

`HttpReadError.code` 为脱敏错误码，不包含凭证、地址或响应正文。`request_may_have_been_sent` 采用保守判断：请求开始后，失败或取消不能证明服务没有执行操作，不能据此重试采集。关闭连接不等于物理安全停止；真实驱动必须实现并独立验收具体硬件的停止与联锁机制。这个工具也无法限制已审核 Python 代码使用其他网络库，不是代码执行沙箱。

## 可运行的合成参考

从仓库根目录启动仅监听回环地址的自建服务：

```bash
python3 apps/instrument-gateway/examples/http-reader/simulator.py
```

程序会输出实际选定的 origin，只提供固定合成身份和两条预存结果，不控制设备，按 Ctrl+C 停止。私有配置使用输出的 origin、`127.0.0.1`、`allow_plaintext: true` 和空 headers，不需要真实仪器凭证。

无需 AI 或联网，选择一个新输出文件即可构建含源码的参考包：

```bash
pnpm gateway:package build \
  --manifest apps/instrument-gateway/examples/http-reader/manifest.json \
  --factory http_reader:create_adapter \
  --file source/http_reader.py=apps/instrument-gateway/examples/http-reader/source/http_reader.py \
  --file tests/test_http_reader.py=apps/instrument-gateway/examples/http-reader/tests/test_http_reader.py \
  --file licenses/LICENSE.txt=LICENSE \
  --output /absolute/private/http-reader.zip
```

之后沿用[检查、离线测试和停用态安装流程](./instrument-adapter-packages.md)。应使用确实包含此工具的准确 SDK wheel 测试，不能只比较相同的开发版本号。参考 factory 只接受回环地址，公开 manifest 始终声明合成输出，不能作为真机验收依据，更不能通过改标签来启用物理仪器。

若需要单独测试 Aira 在固定合成 API 资料和测试下生成源码：

```bash
node scripts/instrument-authoring-example.mjs /absolute/private/http-reader-spec.json --http-reader
```

这只创建私有说明文件，不调用模型、不加载驱动、不访问设备，也不授予权限。后续使用单独确认的[源码开发流程](./instrument-source-authoring.md)。模型可以修改源码，不能修改接口访问权限、manifest 或固定测试；关闭 AI 后仍可使用仓库中的手写参考包。

## 验证与剩余范围

自动测试覆盖实际回环 HTTP/TLS、无效证书和域名不匹配、IP 固定、凭证隔离、取消、异常响应、含源码包的离线测试，以及同一包在两个独立安装目录的复用。可丢弃 PostgreSQL/API 验收由已安装驱动读取自建 HTTP 服务：Platform 保存结果后模拟完成回执不可用，本地保留待确认日志；重启仅补回执，不加载驱动、不再次读取服务、不领取新任务。普通 JSON 与文件型结果统一使用这一恢复边界；不合法的完成记录停下待核查，不初始化驱动。

仅隔离测试会构造合成验收策略记录以验证软件门禁，它不是公开参考包，也不是真机证据。本阶段没有验收厂商 API、真实仪器、物理停止、付费模型效果、第二台物理设备或 Windows 工作站。POST/写入指令、流式/二进制厂商 API、厂商 SDK 和服务发现需要单独审核的后端或适配器。RFC #5 仍保留完整接入产品及已授权真机试点工作。
