# 发布与部署身份

Airalogy Platform 将一次可部署产品标识为一个不可拆分的发布集合，而不是单独记录 Web 或 API 的版本号。

## 身份层级

| 层级 | 字段 | 用途 |
| --- | --- | --- |
| 产品版本 | `PLATFORM_VERSION` | 面向用户和发布说明的 SemVer |
| 源码身份 | Git Tag + 40 位 Git SHA | 精确回到可复现源码 |
| 发布身份 | `release-manifest.json` 的 SHA-256 | 绑定 API、Web、Protocol Executor、PostgreSQL 镜像及 Alembic revision |
| 部署身份 | `AIRALOGY_DEPLOYMENT_ID` | 标识一个安装实例，不携带客户语义 |

`AIRALOGY_DEPLOYMENT_ID` 是形如 `dep_<32 位随机十六进制数>` 的不透明标识。不要把客户名、Lab 名、域名、地址或合同号写进该字段。商业部署方可在自己的私有台账中建立“部署 ID → 客户与运维信息”的映射，该映射不属于本公开仓库。

Platform 不会默认将部署身份、客户信息或运行状态回传给 Airalogy。如需远程支持，由部署管理员显式生成并交付脱敏支持包。

## 正式发布

`VERSION` 是产品版本的唯一源。正式发布时：

1. 根据兼容性选择 SemVer，同步 `VERSION`、API、Web、Instrument Gateway package 和根 workspace 版本。
2. 将中英文 Changelog 的 `Unreleased` 内容移入对应版本节。
3. 在已验证且干净的提交上创建 annotated tag `v<version>` 并推送。
4. Release workflow 运行后端、前端、Instrument Gateway、部署和发布检查，构建多架构镜像和同版本 Gateway wheel/源码包，生成 SBOM 与 provenance，并组装不可变发布包。
5. 正式部署使用 `镜像:版本@sha256:摘要`，不使用 `latest` 作为唯一身份。

科研设备主机应安装同一 GitHub Release 附带的 Gateway 包，在加入本地硬件适配器前核验其发布来源。

源码 checkout 仍可用于本地开发和评估，但会标记 `BUILD_DIRTY` 且不具备正式发布清单的认证语义。

官方 `ghcr.io/airalogy/airalogy-engine:0.16.0` 镜像同时支持 `linux/amd64` 和 `linux/arm64`。Platform 固定其不可变 SHA-256 manifest 摘要，而不依赖 `latest`，因此两种架构都会解析到同一个已验证的发布身份。

## 部署、核验与支持

正式发布包解压后，复制并填写 `.env`，然后执行：

```bash
./platformctl preflight
./platformctl install
./platformctl status
```

API 的 `GET /system/version` 返回产品版本、Tag、Git SHA、构建时间、dirty 状态、发布清单摘要、Alembic revision 和不透明部署 ID。`platformctl status` 会将运行中的 API 与发布清单重新比对。

```bash
./platformctl support-bundle
```

支持包只包含版本身份、不透明的核心镜像 ID/摘要、数据库 revision 和服务健康状态。它明确排除镜像仓库名、`.env`、密钥、日志、数据库、Records、附件、用户身份和客户名。该文件仍应作为运维资料限制访问。

`AIRALOGY_STATE_DIR` 持久保存当前发布、历次安装/升级/回滚事件、发布清单快照和失败恢复依据，不保存密钥或客户业务信息。
