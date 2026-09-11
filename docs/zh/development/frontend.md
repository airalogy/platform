# Airalogy Platform JavaScript Workspace

仓库根目录是 Airalogy Platform Community Edition 的 pnpm workspace，包含 Vue 3 Web 应用，以及 Web 应用使用的共享前端包。

## 环境要求

- Node.js 20.19+ 或 22.12+
- pnpm 10.15+

## 启动

```bash
corepack enable
pnpm install
pnpm dev
```

开发服务器默认监听 `http://localhost:3000`，并把 `/api` 代理到 `http://127.0.0.1:4000`。

如果需要连接其他后端：

```bash
VITE_API_BASE_URL=http://127.0.0.1:4000 pnpm dev
```

可选的本地环境文件：

```bash
cp apps/web/.env.example apps/web/.env.local
```

## 常用脚本

```bash
pnpm dev
pnpm build
pnpm lint
pnpm --filter @airalogy/web type-check
pnpm i18n:generate
```

## 目录结构

```txt
platform/
├── apps/web/            # 主 Airalogy Web 应用
├── apps/admin/          # 预留的管理端 workspace
├── packages/components/ # 共享 UI 组件
├── packages/composables/# 共享 Vue composables
├── packages/shared/     # 共享类型、i18n、常量和工具函数
└── scripts/             # workspace 脚本
```

面向用户展示的文案应放在 `packages/shared/src/locales/langs/` 下的 i18n 语言文件中。

## 共享 UI 约定

产品字体、布局和交互规范见 `apps/web/src/styles/README.md`。卡片式弹窗使用 `aira-dialog`，需要特定宽度时通过内联 `--aira-dialog-width` 设置；长内容在内部滚动，标题和底部确认区保持可见。可选字段使用可键盘操作的折叠区；失败时保留输入并显示持久错误提示。确认过程中连接中断，不等于写入一定失败。

桌面导航与紧凑屏幕的当前模块菜单使用同一份目标定义。权限由 API 校验，不能由导航是否可见代替。修改相关交互时扩展 `tests/e2e/specs/workspace-interactions.spec.ts`，同时覆盖窄屏和 AI 关闭路径。

## Record 表格的依赖边界

列选择交互由 `@airalogy/aimd-renderer` 提供，包括原生“显示全部列”/“恢复默认列”菜单、默认列策略和中英文文案。Platform 绑定现有字段/metadata 选择事件，按用户与 Protocol 保存偏好，不在页面重复遍历 AIMD 字段。

通过 `pnpm-workspace.yaml` 的默认版本目录使用正式发布的 AIMD 包：Core 2.16.0、Editor 1.12.0、Renderer 2.13.0。所有直接引用处声明 `catalog:`，工作区版本目录是唯一版本来源，锁文件记录解析结果与完整性校验。原 Renderer 2.12.0 补丁已移除，不需要本地源码覆盖、相邻仓库或升级 Python `airalogy`。以后升级时修改版本目录、重新生成锁文件，并针对实际发布包重跑浏览器测试与生产构建。`pnpm aimd:dependencies:test` 验证准确版本、直接依赖统一及不存在 Renderer 补丁，也会随 `pnpm type-check` 执行。

执行 `pnpm e2e record-export.spec.ts record-columns.spec.ts` 验证中英文响应式导出弹窗、实际导出下载、原生列操作、隐藏提交信息恢复、键盘操作、宽表滚动和刷新后的偏好。升级 Core 或 Editor 时还应加入 `first-record.spec.ts` 和 `schema-governance.spec.ts`，验证 Protocol 创建、Record 提交/修订与历史版本证据。列测试仅把展示用 Protocol 列模型扩展为合成字段，鉴权和 Record 读取仍走真实接口；另用 `AI_ENABLED=false` 重复验证。单次运行截图与日志不提交到 Git。
