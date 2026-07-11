# 单实验室部署

`single_lab` profile 将 Airalogy Platform 配置为一个实验室内部使用的私有工作空间。它与 Community Edition 共用领域模型和代码库，不另建一套 Lab Edition 分叉。

该 profile 提供唯一 Lab、默认私有 Project、首位 owner 初始化、邀请制成员准入、管理员签发的密码恢复链接和精简导航。生产 stack 包含 Web、API、PostgreSQL、Redis、MinIO、Caddy 反向代理、自动 TLS、配置校验以及完整运维脚本。

## 适用边界

它适合能够维护一台 Linux 服务器、可以接受短时维护窗口的实验室。运行环境建议从 4 核 CPU 和 8 GB 内存起步；如果在部署主机上从源码构建 Web 镜像，建议主机配置 16 GB 内存，并为 Docker 保留至少 8 GB。SSD 需同时容纳实验记录、文件、镜像、构建缓存和备份；备份应保存到异机或独立存储中。

它不是高可用集群，也不是企业身份系统。SSO/LDAP、正式审计日志、多节点故障切换、离线安装包和特定合规控制不属于这个 profile 的范围。

## 前置条件

- 安装 Docker Engine 和 Docker Compose v2 的 Linux 主机
- 使用自动 HTTPS 时，需有指向该主机的公网域名
- 公网 TCP 80/443；如需 HTTP/3，再开放 UDP 443
- 足够容纳 PostgreSQL、MinIO、镜像、构建缓存和备份的磁盘空间

本地评估不需要域名，默认使用 `http://localhost:8080`。

## 安装

在仓库根目录执行：

```bash
cd deploy/single-lab
./scripts/generate-env.sh \
  --site-url https://lab.example.org \
  --tls-email admin@example.org \
  --lab-name "示例实验室"
./scripts/start.sh
```

`generate-env.sh` 会以 `600` 权限生成 `.env`，其中应用、数据库、对象存储、AES 加密和初始化口令均为随机值。已有 `.env` 时脚本默认拒绝覆盖，只有显式传入 `--force` 才会替换。

本地 HTTP 评估：

```bash
./scripts/generate-env.sh --site-url http://localhost:8080
./scripts/start.sh
```

首次构建需要编译 PostgreSQL 扩展和前端，耗时会明显长于后续启动；之后会复用已有镜像。

## 首次初始化

1. 打开 `<SITE_URL>/setup`。
2. 执行 `./scripts/show-setup-code.sh` 查看初始部署口令。
3. 创建首位 owner 账号。
4. 确认页面中出现配置好的唯一 Lab 和 `lab_protocols` 私有 Project。

后端通过数据库锁串行化初始化请求；只要数据库中已有 User 或 Lab，就拒绝再次初始化。生产环境还必须提交 `.env` 中的部署口令，避免公开服务上线后被首位访客抢占 owner。

## 成员与账号

owner 和 Lab manager 可以在成员页面创建一次性邀请链接。新用户通过链接注册；已有账号的用户登录后接受邀请。邀请与邮箱绑定、具有有效期，数据库只保存 token 的 SHA-256 哈希。

owner 或 manager 也可以为符合权限范围的成员创建一次性密码重置链接。manager 只能管理普通 member，不能管理 owner 或其他 manager。用户修改密码或通过重置链接设定新密码后，之前签发的登录 token 会立即失效。

该部署不依赖 SMTP 或短信服务。邀请和恢复链接由实验室复制后，通过自行选择的安全渠道发送。

如果 owner 和 manager 都无法登录，Docker 主机管理员可在不对外暴露恢复接口的情况下签发重置链接：

```bash
./scripts/operator-reset-link.sh owner@example.org
```

该命令只允许为当前唯一 Lab 的成员生成链接，且要求本地访问正在运行的 API 容器和部署 `.env`。新链接会使该账号之前未使用的重置链接失效。

## 网络与 TLS

Caddy 是唯一对外服务，同时提供 Vue 页面和同源代理：

- `/api/*` 转发到 FastAPI，转发前移除 `/api`
- `/minio/*` 转发到 MinIO，并保留签名 URL 所需的 upstream `Host`

PostgreSQL、Redis 和 MinIO API 不映射到公网；MinIO console 只绑定 `127.0.0.1`。使用公网域名时，Caddy 自动申请和续期 TLS 证书，主机的 80/443 端口必须可达。

## 配置

部署配置位于 `deploy/single-lab/.env`。只影响后端的配置重启相关容器即可；`VITE_` 开头的值会编译进 Web 镜像，修改后必须重新构建 Web。

启动前，`preflight.sh` 和后端会分别执行配置校验。生产环境会拒绝占位密钥、无效 AES key、弱 MinIO 凭据、远程 HTTP 地址、请求正文日志、错误 API prefix 和非单实验室 profile。即使绕过脚本直接启动，错误配置也不会静默进入运行状态。

AI 功能是可选项。需要时在 `.env` 中配置模型供应商 key；不配置 AI 也不影响 Protocol / Record 基础流程。

`COMPONENT_BUILD_MEMORY_MB` 和 `WEB_BUILD_MEMORY_MB` 只用于控制 Web 镜像构建时的 Node.js heap 上限。除非主机的 Docker 内存配额有明确差异，应保留生成配置中的默认值。

## 日常运维

查看状态和日志：

```bash
docker compose --env-file .env -f compose.yml ps
docker compose --env-file .env -f compose.yml logs -f api-server web
```

停止服务但保留数据：

```bash
./scripts/stop.sh
```

除非明确准备销毁 PostgreSQL、MinIO、Caddy 和应用持久卷，否则不要附加 `--volumes`。

### 备份

```bash
backup_path="$(./scripts/backup.sh)"
echo "$backup_path"
```

脚本会短暂停止 API 写入，生成 PostgreSQL custom-format dump，镜像并归档 MinIO bucket，复制部署密钥，写入 manifest 和 SHA-256 校验值，随后恢复 API。备份包含明文凭据和加密 key，必须加密保存、限制访问并同步到异机。

### 恢复

```bash
./scripts/restore.sh ./backups/20260711T120000Z-manual
```

恢复前会校验 checksum 和 AES key，停止应用写入，替换数据库与 bucket，并等待 API/Web 恢复健康。在新服务器做灾难恢复时，先把备份中的 `secrets.env` 用作 `deploy/single-lab/.env`，再执行 restore；否则历史 Protocol secret 可能无法解密。

### 升级

先把工作树更新到目标 release 并阅读 release notes，然后执行：

```bash
./scripts/upgrade.sh
```

脚本会运行 preflight，创建一致的升级前备份，把当前 API/Web 镜像标记为 rollback 版本，在高内存构建期间停止 API/Web，按顺序重建服务，并在 API 启动时执行 Alembic migration，最后等待 readiness。构建失败会重启旧容器；启动或健康检查失败会自动恢复升级前镜像与数据。只有 release 修改了 PostgreSQL 扩展镜像时才需增加 `--build-db`。

### 回滚

```bash
./scripts/rollback.sh
```

回滚会使用上一个 API/Web 镜像，并恢复升级前的数据库和对象存储备份。由于升级后产生的新写入会被替换，脚本要求人工输入确认。

## 验收

在一次性、全新且尚未初始化的部署上执行：

```bash
./scripts/acceptance-test.sh
```

该脚本会创建 owner、校验默认 Project、邀请 member、检查成员权限、修改并重置 member 密码、验证旧 JWT 失效和一次性 token 不可重放。它会写入测试账号，因此检测到实例已初始化时会拒绝运行。

健康检查接口：

- `/api/health/live`：进程存活
- `/api/health/ready`：PostgreSQL、Redis 和对象存储可用

## 安全检查表

- `.env` 和备份只能由部署管理员读取。
- 使用独立主机，及时安装操作系统安全更新并配置主机防火墙。
- 只暴露 Caddy 端口，不要向公网映射 PostgreSQL、Redis 或 MinIO API。
- 保持 `LOG_REQUEST_BODIES=false`；请求中可能包含账号凭据和尚未公开的实验数据。
- 保持 `LOG_MAX_BYTES` 和 `LOG_BACKUP_COUNT` 配置的文件日志轮转。
- 定期实际执行恢复演练。未经恢复验证的备份还不能视为可用。
- 对模型供应商 key 和部署密钥建立明确的维护窗口与轮换流程。

## 故障排查

先运行 `./scripts/preflight.sh`。启动失败时查看 `docker compose --env-file .env -f compose.yml logs api-server`。migration 或生产配置校验失败会有意阻止 API 进入 healthy。

如果签名对象 URL 失效，检查 `MINIO_PROXY_PATH=/minio`，并确认外层代理没有再次改写路径或 upstream `Host`。自动 TLS 失败时，检查 DNS 以及公网 80/443 是否确实到达该主机。
