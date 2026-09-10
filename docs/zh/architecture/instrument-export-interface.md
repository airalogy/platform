# 采集仪器已完成的导出文件

可复用的 `ExportReadClient` 支持仅能导出本地文件的设备流程。它读取**明确选定且已完成的导出批次**，保留原始字节和来源信息，返回已有 `InstrumentResult` 文件契约，再由受治理的 Gateway 将文件接入授权范围内的草稿 DataAsset。这不是设备发现、文件夹同步、CSV 解析器，也不授予仪器操作权限。

## 导出生产方与完成契约

经过独立审核的导出桥接程序或有权操作者，须先明确厂商软件如何确认导出完成。关闭数据文件，为批次指定准确 UUID 和样品引用，计算原始字节数和哈希，再在同一 UUID 目录内**最后原子发布 `export.json`**。临时文件须位于同一文件系统，并采用生产方适用的持久化方式。不能仅凭文件夹安静或出现 CSV 就推断完成，已经使用的 UUID 不得覆盖。

```text
<明确选定的本地导出根目录>/
  <导出批次 UUID>/
    result.csv
    export.json
```

完成清单是有大小上限的 UTF-8 JSON，且只能包含以下字段。这是模板：须用实际观察替换 UUID、样品、时间、字节数、哈希、单位和完成依据，哈希占位符不是有效输入。

```json
{
  "schema": "airalogy.export-completion.v1",
  "export_id": "00000000-0000-4000-8000-000000000001",
  "sample_reference": "sample-A",
  "export_complete": true,
  "completed_at": "2026-09-11T12:30:00+08:00",
  "files": [
    {
      "name": "result.csv",
      "byte_size": 26,
      "sha256": "<原始文件字节对应的 64 位小写十六进制 SHA-256>",
      "captured_at": "2026-09-11T12:29:00+08:00",
      "original_units": ["signal: 仪器原始单位"],
      "conversion_rules": [],
      "completion_reference": "经过审核的生产方导出完成依据"
    }
  ]
}
```

每个文件条目只允许上述字段。名称必须匹配适配包审核过的可移植文件名，不接受路径、网址、通配符、保留名称或重复条目，所有必需输出均须存在。`export.json` 是保留名称，由读取器作为原始输出补入，不在自身 `files` 中列出。时间保留原时区，单位和转换依据原样保留，不执行转换。样品引用是生产方/操作者的明确声明，不自动解析成 Platform Sample。这里的完成仅表示**导出字节已就绪**，不表示实验或科学假设成功。

## 私有本地配置

配置只包含 `schema`、`root` 和 `root_identity`：

```python
from airalogy_instrument_gateway.output_capture import source_root_identity

root = "/absolute/private/export-inbox"  # 操作者明确选定
configuration = {
    "schema": "airalogy.export-read-config.v1",
    "root": root,
    "root_identity": source_root_identity(root),
}
```

将 JSON 保存到服务账号所有的 `0600` 普通文件，父目录为私有 `0700` 目录。导出根目录须是非文件系统根的 POSIX 绝对路径，不能有符号链接祖先，并保持固定设备号/inode。源目录和文件须属于服务账号且不可被其他用户写入，建议使用 `0700`/`0600` 保护隐私。符号链接、文件硬链接、特殊文件及根目录下的跨文件系统路径均拒绝读取。若厂商软件使用另一个账号，应审核独立交接方式，不要放宽他人的文件权限。配置改变须重新审核安装/激活；真实路径和导出内容不得进入包载荷、公开 Issue 或模型资料。

构造读取器只检查选定根目录身份，不枚举内容。执行期间只等待 `<root>/<export_id>/export.json`；清单一旦存在但格式错误或未完整写入，就立即失败。批次/样品不符、超限、字节变化或哈希不符也会失败，返回前还会复查文件身份和清单。源文件不会被修改或删除。

最多 16 个输出，包含必需且不超过 128 KiB 的 JSON 清单。每个包固定文件配额，SDK 默认总配额为 64 MiB。同一客户端同时只允许一个读取；等待/读取期限为 0.01–120 秒，在文件系统操作之间检查取消。**它不能强制打断阻塞的操作系统文件调用**，仅使用审核过的本地存储，不使用网络挂载目录。Gateway 仍须等待工作线程退出后才能确认停止；取消采集不会停止独立运行的厂商软件或物理实验。

## 含源码采集包与 Aira 开发

手写的 `examples/export-reader` 无需 AI。唯一命令 `export.files.collect@1.0.0` 只接收 `export_id` 和 `sample_reference`，读取必需的 `result.csv`（1 MiB）及 `export.json`（128 KiB）；读取期限 20 秒，命令上限 30 秒。结果包含批次/样品、清单哈希、文件数量/大小和 `scientific_validation: false`，不生成虚构测量值。

在仓库根目录构建到一个新的私有文件：

```bash
pnpm gateway:package build \
  --manifest apps/instrument-gateway/examples/export-reader/manifest.json \
  --factory export_reader:create_adapter \
  --file source/export_reader.py=apps/instrument-gateway/examples/export-reader/source/export_reader.py \
  --file tests/test_export_reader.py=apps/instrument-gateway/examples/export-reader/tests/test_export_reader.py \
  --file licenses/LICENSE.txt=LICENSE \
  --output /absolute/private/export-reader.zip
```

继续已有的[包检查、隔离测试、安装、验收和激活流程](./instrument-adapter-packages.md)，须选择包含 `export_read` 的准确可信 SDK wheel，而不只是相同开发版本号。观察到的目标是本地导出目录/读取器；`firmware: "not-observed"` 明确不证明厂商硬件身份。应独立验收其数据采集范围，不能用此包验收物理仪器控制命令。

已安装激活启动器的显式 `--output-root` 须使用同一导出根目录，并与私有运行日志/outbox 分离。成功命令会按真实签名任务的输出计划保存持久原始副本，仅上传到授权 Project；本地捕获成功前须保留生产方文件。已有[传输和恢复流程](./instrument-adapter-packages.md#自动交付与恢复)保留原文件/outbox，回执丢失后只核对结果，不初始化驱动或重新读取源目录。关联 Record 仍须独立预览确认，不自动提交 Record。

可选 Aira 开发使用公开采集契约和独立固定测试：

```bash
node scripts/instrument-authoring-example.mjs /absolute/private/export-spec.json --export-reader
```

这里只生成包含合成测试数据的私有输入文件，不调用模型、不读取真实导出。继续独立授权的[源码开发流程](./instrument-source-authoring.md)。模型只能改变源码，不能修改固定测试、命令/文件权限或清单；AI 关闭时仍可手工构建和采集。

## 验证与剩余范围

测试覆盖准确 ID 等待且不枚举目录、延迟原子发布、部分/变化文件、哈希/配额、身份/样品不符、越界/链接/权限及取消。含源码包在无网络、无主机挂载的容器内通过独立固定测试。临时 API/PostgreSQL/对象存储验收运行真正安装后的包，对比保存后下载的原始字节和来源信息，再仅移除自建源文件测试目录，验证只恢复回执的流程。这证明软件链路，不证明厂商语义或实机安全。

自动厂商完成桥接、任意目录导入、文件名猜测、跨任务批次消费台账、Windows 权限/后端及真实仪器均未验收。同一任务的传输具有幂等性，但另行确认的新任务可能有意从同一批次创建新的草稿资产。真实试点仍需明确设备/软件授权和独立的生产方完成验证，RFC #5 保持开放。
