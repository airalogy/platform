# 文件存储桥接

Airalogy Protocol 应记录稳定的文件引用，而不是对象存储或中心文件服务器的物理 URL。`airalogy.id.file.<uuid>.<ext>` 这样的 `FileId` 是文件的逻辑身份。只有当具备权限的用户需要预览、下载或把文件交给 AI 处理时，后端才把这个逻辑身份解析为当前可访问的存储位置。

## 数据模型

`airalogy_files` 表是文件引用索引。它保存：

- 逻辑文件身份和文件名
- content type、文件大小和 checksum 等元数据
- project、protocol 和 owner 关联
- 托管对象存储使用的 storage backend、namespace 和 object key
- 已存在于外部数据中心时使用的 external URI 元数据

浏览器或客户端上传文件时，Platform 把文件写入当前配置的对象存储，并持久化这次实际使用的 backend、namespace 和 object key。对于已经在中心文件服务器、NAS、仪器数据中心里的大文件，可以只注册外部位置并生成 FileId，不复制文件本体。

## 解析流程

```text
Record FileId
  -> airalogy_files row
  -> 权限检查
  -> storage backend resolver
  -> 短期 URL 或后端文件流
```

因此，即使部署方从 MinIO 切换到 OSS，或接入中心文件服务器，Protocol 和 Record 中保存的 FileId 也不需要变化。物理存储布局只由 resolver 和 storage adapter 感知。

## 当前 backend

- `minio`：Community 默认的本地和自托管对象存储。
- `oss`：可选的阿里云 OSS backend，需要配置 `OSS_REGION`、`OSS_ENDPOINT`、`OSS_BUCKET` 和 OSS 凭据。
- `external` 或部署自定义名称：登记外部文件位置，由部署方补充 connector 解析。

## API

- `POST /airalogy_files`：上传文件并创建托管 FileId。
- `POST /airalogy_files/register`：登记已有外部文件并创建 FileId。
- `GET /airalogy_files/{id}`：解析文件元数据和访问 URL。
- `GET /airalogy_files/{id}/url`：解析短期访问 URL。
- `GET /airalogy_files/{id}/download`：通过权限检查后流式下载或跳转到外部文件。
