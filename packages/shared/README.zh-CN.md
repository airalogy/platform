# @airalogy/shared

> Airalogy 研究平台的共享工具、常量和类型

## 概述

本包包含在整个 Airalogy 平台中使用的共享工具、常量、类型定义、主题和枚举。它为需要在不同应用和包中保持一致的常见功能提供了一个集中的位置。

## 包含内容

### 工具函数

- **请求工具** - HTTP 请求助手，支持流式传输（SSE、EventSource）
- **文件工具** - 文件类型检测、转换和验证函数
- **Schema 工具** - JSON Schema 验证和助手
- **变换工具** - 字符串情况转换函数（camelCase、kebabCase、snakeCase、pascalCase）
- **剪贴板工具** - 复制到剪贴板功能
- **下载工具** - 文件下载助手
- **日期工具** - 日期格式化和 Day.js 集成的日期操作
- **错误格式化** - 错误消息格式化和回溯处理
- **存储工具** - 本地存储和 IndexedDB 助手，支持监视
- **URI 工具** - URL 解析和操作
- **变量类型解析器** - 解析和验证 AIMD 变量类型
- **ISO 时长** - 解析 ISO 8601 时长字符串

### 常量和枚举

- **编辑器常量** - 各种编辑器的配置（主题、布局、设置）
- **内容布局** - UI 结构的布局相关常量
- **国家代码** - 国际国家代码映射
- **事件键** - 系统通信的事件键常量
- **协议常量** - 协议相关的常量和配置
- **聊天枚举** - 聊天系统常量和消息类型
- **编辑器枚举** - 编辑器模式、主题和状态
- **Airalogy 枚举** - 平台特定的常量和状态

### 类型定义

- **通用类型** - 共享的 TypeScript 接口和类型
- **模型定义** - 数据模型接口（协议、聊天、附件）
- **环境类型** - 环境配置和运行时类型
- **API 类型** - API 请求/响应接口
- **主题类型** - 主题和颜色配置类型
- **字段类型** - AIMD 字段定义和记录结构
- **Union 键类型** - 类型安全的 union 键工具
- **自动导入** - TypeScript 自动导入声明

### 主题系统

- **颜色调色板** - 预定义的颜色方案和颜色工具
- **主题变量** - CSS-in-JS 主题配置
- **颜色操作** - 使用 Colord.js 的高级颜色工具

### 资源

- **图标** - 60+ 个 SVG 图标用于 UI 组件
  - 导航：菜单、面包屑、箭头图标
  - 文档：文件、文件夹、协议图标
  - 操作：保存、删除、编辑、搜索图标
  - 状态：处理中、云、记录状态图标
  - 以及更多...

### 国际化

- **区域设置配置** - 多语言支持（英语、简体中文）
- **Day.js 本地化** - 不同语言的日期/时间格式化
- **翻译管理** - Vue i18n 集成和区域设置加载

## 安装

```bash
pnpm add @airalogy/shared
```

## 使用

### 请求工具

```typescript
import { createApiClient, handleApiError } from "@airalogy/shared"

// 使用默认配置创建 API 客户端
const apiClient = createApiClient({
  baseURL: "http://127.0.0.1:4000",
  timeout: 10000,
})

// 一致地处理 API 错误
try {
  const response = await apiClient.get("/data")
}
catch (error) {
  const handledError = handleApiError(error)
  console.error(handledError.message)
}
```

### 文件工具

```typescript
import { formatFileSize, getFileExtension, validateFileType } from "@airalogy/shared"

// 验证文件类型
const isValidImage = validateFileType(file, ["jpg", "png", "gif"])

// 格式化文件大小以显示
const formattedSize = formatFileSize(1024000) // "1.02 MB"

// 获取文件扩展名
const extension = getFileExtension("document.pdf") // "pdf"

// 检测文件类型
const { type, icon, color } = getFileType("document.pdf")
```

### 常量和枚举

```typescript
import { ChatMessageType, CONTENT_LAYOUTS, EDITOR_THEMES, FileType } from "@airalogy/shared"

// 使用编辑器主题
const currentTheme = EDITOR_THEMES.DARK

// 使用布局常量
const layout = CONTENT_LAYOUTS.SIDEBAR_LEFT

// 使用聊天枚举
if (message.type === ChatMessageType.AI_RESPONSE) {
  // 处理 AI 响应
}

// 使用文件类型枚举
if (file.type === FileType.PDF) {
  // 处理 PDF 文件
}
```

### Schema 验证

```typescript
import { commonSchemas, createValidator } from "@airalogy/shared"

// 为用户数据创建验证器
const validateUser = createValidator(commonSchemas.user)

const result = validateUser({
  id: "123",
  email: "user@example.com",
  name: "张三",
})

if (!result.valid) {
  console.error("验证错误:", result.errors)
}
```

### 国际化

```typescript
import { loadLocale, setupI18n } from "@airalogy/shared"

// 使用默认配置设置 i18n
const i18n = setupI18n({
  locale: "zh-CN",
  fallbackLocale: "en",
})

// 加载额外的区域设置
await loadLocale("zh-TW")
```

### 变换工具

```typescript
import { camelCase, kebabCase, pascalCase, snakeCase } from "@airalogy/shared"

const text = "hello world example"

console.log(camelCase(text)) // "helloWorldExample"
console.log(kebabCase(text)) // "hello-world-example"
console.log(snakeCase(text)) // "hello_world_example"
console.log(pascalCase(text)) // "HelloWorldExample"
```

### 存储工具

```typescript
import { useLocalStorage, useSessionStorage } from "@airalogy/shared"

// 简单的键值存储
const token = useLocalStorage("auth_token", "")
token.value = "abc123"

// 支持监视的存储
import { StorageMonitor } from "@airalogy/shared"
const monitor = new StorageMonitor()
monitor.track("key")
```

### 日期工具

```typescript
import { formatDate, parseDate, getDaysDiff } from "@airalogy/shared"

const now = new Date()
const formatted = formatDate(now, "YYYY-MM-DD") // "2024-01-28"
const diff = getDaysDiff(now, new Date(now.getTime() + 86400000)) // 1
```

## 导出

### 主入口 (`@airalogy/shared`)

从主入口点导出所有工具、常量、枚举、类型和主题。

```typescript
import {
  // 常量
  CONTENT_LAYOUTS,
  EDITOR_THEMES,
  // 枚举
  ChatMessageType,
  EditorMode,
  // 工具
  formatFileSize,
  formatDate,
  // 类型
  type Protocol,
  type ChatMessage,
} from "@airalogy/shared"
```

### 工具入口 (`@airalogy/shared/utils`)

直接访问工具函数：

```typescript
import {
  formatFileSize,
  validateFileType,
  formatDate,
  camelCase
} from "@airalogy/shared/utils"
```

### Unified 入口 (`@airalogy/shared/unified`)

AIMD 和 Markdown-it 相关导出：

```typescript
import { /* unified markdown 工具 */ } from "@airalogy/shared/unified"
```

## 开发

### 脚本命令

```bash
# 类型检查
pnpm type-check

# 生产环境构建
pnpm build

# 构建类型声明
pnpm build:types
```

### AIMD 语法测试

AIMD（Airalogy Markdown）语法高亮使用 TextMate 语法测试进行测试。这确保了语法高亮在不同编辑器中正常工作（VS Code、Monaco、Shiki）。

#### 语法文件

| 文件 | 描述 |
|------|------|
| `packages/shared/src/constants/aimd/aimdSyntax.ts` | Shiki/TextMate 语法定义 |
| `packages/shared/src/constants/aimd/aimd.ts` | Monaco 编辑器语法定义 |
| `packages/shared/src/constants/aimd/tokens.ts` | 令牌/范围名称定义 |
| `test/grammar/aimd.tmLanguage.json` | 生成的 TextMate 语法文件 |
| `test/grammar/aimd.test.aimd` | 语法测试用例 |
| `scripts/generate-grammar.ts` | 语法和测试生成脚本 |

#### 运行语法测试

```bash
# 从单体仓库根目录：

# 生成语法文件并运行测试
pnpm grammar:test

# 仅重新生成语法文件（不测试）
pnpm grammar:generate
```

#### 测试文件格式

测试文件使用标准 TextMate 语法测试格式：

```aimd
{{var|name: str}}
//<- punctuation.definition.begin.aimd    ← 测试 {{ 令牌
//^^^ keyword.variable.aimd               ← 测试 var 令牌
//   ^ delimiter.pipe.aimd                ← 测试 | 令牌
//    ^^^^ variable.other.aimd            ← 测试 name 令牌
//        ^ delimiter.colon.aimd          ← 测试 : 令牌
//          ^^^ support.type.aimd         ← 测试 str 令牌
```

- `//<-` 测试前一行开头的令牌
- `//^^^` 每个 `^` 对应前一行的一个字符位置
- 空格用于对齐，表示不被测试的位置

#### 添加新测试用例

1. 编辑 `scripts/generate-grammar.ts` 以添加新的测试生成逻辑
2. 运行 `pnpm grammar:generate` 以重新生成测试文件
3. 运行 `pnpm grammar:test` 以验证所有测试通过

#### 支持的 AIMD 类型语法

语法支持新的变量类型语法：

```aimd
{{var|name: str}}                              # 简单类型
{{var|age: int = 18}}                          # 带默认值的类型
{{var|name: str = "张三", title = "姓名"}}      # 带 kwargs
{{var|active: bool = true}}                    # 布尔类型
{{var|students: list[Student], subvars=[...]}} # 列表带子变量
```

### 依赖

本包包括：

- **核心工具** - Lodash-ES、Day.js、nanoid
- **颜色工具** - Colord 用于高级颜色操作
- **文件处理** - JS-YAML、Big.js、LocalForage、fflate
- **Markdown/Unified** - Remark、Rehype、Shiki 用于 markdown 处理
- **国际化** - Vue i18n
- **Schema 验证** - AJV、async-validator
- **DOM 工具** - DOMPurify

### 对等依赖

- **@monaco-editor/loader** - Monaco 编辑器加载器
- **@vueuse/core** - Vue Composition 工具
- **Day.js** - 日期操作
- **Lodash-ES** - 工具函数
- **nanoid** - 唯一 ID 生成

## 架构

### 模块化设计

所有工具都组织成逻辑模块，可以独立导入：

```typescript
import { ChatMessageType } from "@airalogy/shared/enum"
import { createMarkdownRenderer } from "@airalogy/shared/unified"
// 导入特定工具
import { formatDate } from "@airalogy/shared/utils"

// 或导入所有（不推荐用于生产）
import * as shared from "@airalogy/shared"
```

### 类型安全

完整的 TypeScript 支持：

- 严格的类型检查
- 通用类型工具
- 综合接口定义
- 适当的类型导出
- 用于 API 响应的模型类型

### 树摇

针对树摇进行了优化以确保最小的包大小：

- 仅命名导出
- 工具函数中没有副作用
- 用于选择性导入的模块结构
- SVG 资源作为文件包含

## 资源管理

### 图标

本包包括 60+ 个按类别组织的 SVG 图标：

```typescript
import IconAdd from "@airalogy/shared/assets/icons/add-circle.svg"
import IconDelete from "@airalogy/shared/assets/icons/delete.svg"
// 或使用动态导入以获得更好的树摇效果
```

## 扩展

### 添加新工具

```typescript
// utils/myUtility.ts
export function myUtility(input: string): string {
  // 实现
  return processed
}

// 添加到 utils/index.ts
export * from "./myUtility"

// 如需要，添加到主 index.ts
export * from "./utils"
```

### 添加新常量

```typescript
// constants/myConstants.ts
export const MY_CONSTANTS = {
  VALUE_ONE: "value1",
  VALUE_TWO: "value2",
} as const

// 添加到 constants/index.ts
export * from "./myConstants"
```

### 添加新主题

```typescript
// theme/myTheme.ts
export const MY_THEME = {
  colors: {
    primary: "#3b82f6",
    secondary: "#8b5cf6",
  },
}

// 添加到 theme/index.ts
export * from "./myTheme"
```

## 贡献指南

1. **遵循 TypeScript 最佳实践** - 使用严格类型
2. **添加详细的 JSDoc 注释** - 文档所有公开 API
3. **编写单元测试** - 测试所有工具函数
4. **保持向后兼容性** - 需要时使用弃用警告
5. **更新文档** - 保持 README 和内联文档最新
6. **遵循 JavaScript 标准样式** - 一致的代码格式

## 性能考虑

- **延迟加载** - 为重型工具使用动态导入
- **树摇** - 确保命名导出以获得更好的优化
- **缓存** - 存储工具支持缓存策略
- **内存效率** - 存储监视器跟踪内存使用情况

## 许可证

Airalogy 单体仓库的一部分。保留所有权利。
