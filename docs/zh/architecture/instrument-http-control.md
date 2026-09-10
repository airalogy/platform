# 经审核的仪器 HTTP 控制

`HttpControlClient` 是面向独立文档明确的 JSON 操作的 SDK 通信后端，支持固定 GET、POST、PUT，复用[只读后端的固定地址 HTTP/TLS 通信](./instrument-http-interface.md)。它不等于设备适配器、源码批准、设备权限、发现服务或安全控制器。HTTP 方法不能证明物理副作用。

## 独立本地配置

只读配置不能启用这个客户端。本地人员必须另选私有配置并明确允许的操作名称：

```json
{
  "schema": "airalogy.http-control-config.v1",
  "origin": "https://reader.example.test:443",
  "address": "192.0.2.20",
  "allow_plaintext": false,
  "headers": {},
  "enabled_operations": ["state", "configure", "start", "stop"]
}
```

上述地址仅作说明，不是待连接仪器。沿用只读后端的 POSIX 所有者私有文件/父目录检查、固定 IP、校验证书和主机名的 TLS、显式明文确认和仪器专用认证规则。不使用环境代理、Cookie、重定向、认证刷新或自动重试。配置变化须重新审核安装与启用；真实配置、凭据和地址不得进入模型资料、包或公共 Issue。

审核源码固定每个操作的方法、路径、准确正文/查询字段名、字节限额与接受的状态码。本地配置只能选择其中一部分，作业参数不能为已审核包新增目标地址或方法。它不是针对同账号恶意 Python 的网络沙箱。

```python
from airalogy_instrument_gateway.http_control import HttpControlClient, HttpControlOperation

client = HttpControlClient.from_file(config_path, {
    "state": HttpControlOperation("GET", "/v1/state"),
    "configure": HttpControlOperation("PUT", "/v1/parameters", ("operation_id", "sample_count")),
    "start": HttpControlOperation("POST", "/v1/start", ("operation_id",), statuses=(202,)),
    "stop": HttpControlOperation("POST", "/v1/stop", ("operation_id",)),
})
# 构造不连接。只能在单独获授权的适配操作中，使用准确 SDK job.job_id
# 和已审核参数界限进行调用。
receipt = client.call("start", {"operation_id": job.job_id}, stop_event=stop_event)
```

这些路径来自下面的自建参考服务，不是厂商端点。正文为准确顶层字段的 JSON 对象，上限 64 KiB、深度 16，并限制集合大小；GET 不允许正文，查询字段沿用只读后端的准确字段与编码规则。适配器仍须校验厂商参数类型、范围、单位和操作关联，通信层不推测这些语义。可信源码可指定 200、201、202 状态，响应须为严格 JSON 对象，最大 1 MiB；当前不支持空 204 响应、流式/二进制协议或动态路径。

## 接受请求不等于完成实验

`receipt.status`、原始 `raw` 字节、`sha256`、解析后的 `data` 和本地 `received_at` 只描述 HTTP 回执，不是采集时间或科学完成证据。202 仅表示接受请求；必须独立读回准确操作编号、参数、完成状态和结果，并在关键观察前后检查控制权和冲突。多次 HTTP 读取并非原子联锁，仍需要厂商设备端的确定性检查。

`HttpControlError` 只携带固定错误码和保守的 `request_may_have_been_sent`，不输出私有地址、凭据或响应正文。写请求可能已发送后，超时、取消、回执丢失或无效 JSON 都不能触发重新启动。取消通信、关闭连接不代表设备停止；设备特定的停止和状态核对由审核后的适配器实现，不能复用已取消的采集事件阻止停止请求。此工具不保存物理作业日志；既有 Instrument Job、Gateway 日志、租约、本地确认、启动预检与停止不确定规则仍须执行。

## 可运行的自建参考

只启动仓库自带的本机回环模拟服务，不连接物理设备：

```bash
python3 apps/instrument-gateway/examples/http-controlled-reader/simulator.py
```

使用它打印的 origin、`127.0.0.1`、显式明文确认和空认证，`enabled_operations` 准确列出 `identity`、`state`、`configure`、`start`、`result`、`stop`。一个新服务实例代表一次采集，不提供隐式复位。公开参考包和输出始终固定为模拟，不能用于真实设备启用验收。

无 AI 时可手工构建：

```bash
pnpm gateway:package build \
  --manifest apps/instrument-gateway/examples/http-controlled-reader/manifest.json \
  --factory http_controlled_reader:create_adapter \
  --file source/http_controlled_reader.py=apps/instrument-gateway/examples/http-controlled-reader/source/http_controlled_reader.py \
  --file tests/test_http_controlled_reader.py=apps/instrument-gateway/examples/http-controlled-reader/tests/test_http_controlled_reader.py \
  --file licenses/LICENSE.txt=LICENSE \
  --output /absolute/private/http-controlled-reader.zip
```

如需独立授权的[源码草拟](./instrument-source-authoring.md)，运行 `node scripts/instrument-authoring-example.mjs /absolute/private/http-controlled-spec.json --http-controlled-reader` 生成固定独立开发规范。须使用包含 `http_control` 的准确可信 SDK wheel，同开发版本号的旧 wheel 不能替代。生成规范不调用模型或设备；非只读源码确认、源码审核、准确安装、受控验收和启用相互独立。

软件测试覆盖独立假客户端、实际回环 HTTP、隔离包测试和同一包字节的两次独立安装。可销毁 API/PostgreSQL 验收使用明确标识的合成资格策略记录及真实安装驱动，验证参数配置、仅启动一次、关联结果，以及 Platform 完成回执丢失后的仅日志恢复，不再次加载驱动或连接服务。未验证付费模型质量、厂商协议、物理安全停止、真实设备或第二台物理部署；RFC #5 的这些要求和 GUI/OS 路线继续开放。
