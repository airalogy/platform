# Platform 开发

Airalogy Platform 是一个 monorepo，包含 FastAPI 后端、Vue Web 应用、共享包、部署资源、测试和本统一文档。修改代码前应阅读仓库 `AGENTS.md` 以及相关子系统文档。

## 仓库结构

| 路径                | 责任                                                             |
| ------------------- | ---------------------------------------------------------------- |
| `apps/api`          | FastAPI API、数据库模型与迁移、后台任务、存储和执行器集成。      |
| `apps/web`          | 登录后的 Vue 产品体验和部署感知导航。                            |
| `packages/*`        | 共享 UI、composable、类型、国际化和跨界面契约。                  |
| `deploy/single-lab` | 面向生产的单实验室镜像、代理配置、初始化、校验、备份与升级工具。 |
| `docs`              | Platform 公开站和镜像内本地站的唯一文档源码。                    |

## 本地开发流程

使用仓库指定的包管理器和运行时版本。按锁文件安装依赖，先运行最小相关测试，再运行受影响子系统要求的广泛检查。国际化生成类型应通过仓库脚本生成，不应手工修改。

文档开发命令：

```bash
pnpm docs:dev
DOCS_BASE=/platform/ pnpm docs:build
```

`DOCS_BASE` 是唯一的基础路径输入。GitHub Pages 公开镜像使用 `/platform/`，正式 Platform 部署使用同源 `/docs/`。根目录的 `pnpm dev` 和 `pnpm build` 会先在 Web 公共资源中生成与当前版本匹配的文档。

## 提交、推送与 CI 检查

- **pre-commit** 仅处理暂存文件的格式和快速 lint，不执行浏览器、数据库或镜像测试。
- **pre-push** 按实际待推送的提交差异选择检查，先检查工作流、CLI 参数等快速失败项，再运行相关单元、浏览器或数据库测试。手工调用只比较已提交内容与 upstream，不会把未提交编辑误称为已验证的推送。
- **GitHub CI** 使用同一注册检查入口，并保留 Linux/macOS 矩阵、托管运行时权限、SDK 打包、真实发布签名、镜像安装和备份恢复验收。本地通过不等于这些远端验收已经通过。

首次配置开发环境时，安装 GitHub CLI `gh`，按锁文件安装仓库依赖，然后显式安装固定版本的工作流检查器：

```bash
pnpm ci:tools:install
pnpm exec playwright install chromium
pnpm prepush:check --plan
pnpm prepush:full --plan
pnpm prepush:full
```

`ci:tools:install` 下载官方 actionlint 1.7.12，核对归档和可执行文件 SHA-256，存入被忽略的 `.cache/actionlint/`；后续每次执行重新核对字节。支持 Linux/macOS 的 x64 和 arm64。推送检查不会偷偷安装工具、联网升级或修改系统权限；缺少工具或缓存校验失败会明确阻止对应检查。actionlint 检查工作流结构和表达式，不等于 ShellCheck、全部 Shell 命令兼容性或远端权限验证。

`prepush:full` 不依赖文件差异，执行注册的完整本地检查：版本、Python 锁文件、lint、类型、API、Gateway、真实 `gh` 离线拒绝测试、Compute Runner、仪器契约、模拟浏览器与演练、发布清单及部署身份、科研数据库集成、文档、生产构建和完整浏览器 E2E。macOS 额外编译原生辅助程序；Linux 不宣称通过 macOS 编译。完整 E2E 已包含定向 AI 用例，不重复执行子集。

完整检查需要 Docker 和隔离测试基础设施，耗时明显长于普通推送，不应移到每次提交。它不执行真实仪器动作、不申请桌面权限、不推送镜像、不创建发布，也不替代真实来源证明和跨平台 CI。不得与另一组使用同一 E2E 基础设施的测试同时运行。

快速单独检查或复现 CI 步骤：

```bash
pnpm ci:check
node scripts/pre-push.mjs --check gateway-cli
node scripts/pre-push.mjs --check interface-tests
```

`scripts/pre-push.mjs` 是检查命令、环境和选择规则的共同入口。新增工作流路径或检查时，同时更新其回归测试；CI 准备脚本的测试只使用临时文件，实际权限调整仍仅允许一次性的 GitHub 托管环境。所有图形会话与实机验收保持独立、显式授权。

## 架构与契约

- [前端开发](../development/frontend)：JavaScript workspace 和 Web 构建。
- [文件存储桥接](../architecture/file-storage-bridge)：稳定文件身份和存储解析。
- [自托管架构](../architecture/self-hosted-architecture)：服务与数据位置。
- [访问控制](../access-control)：角色、授权、继承和后端执行。

应优先维护单一共享契约，避免各界面重复实现。权限、校验和运维决定应由确定性代码负责；AI 生成的叙述不能暗中改变这些决定。

## 文档边界

产品行为、公开架构、部署步骤和更新日志属于本仓库。客户服务器细节、账号密钥、私有网络拓扑、SLA 和交付记录不得进入公开仓库。帮助中心按角色显示卡片只用于优化导航，不能作为公开文档文件的权限控制。

调整导航时应保持既有公开文档路径可用。旧的独立文档仓库只作为迁移参考保留到新站上线；是否归档应单独决定。
