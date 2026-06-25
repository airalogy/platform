# @airalogy/composables

> Airalogy 研究平台的可复用 Vue Composables

## 概述

本包提供 Vue 3 composables 的集合，这些 composables 封装了在整个 Airalogy 平台中使用的常见反应式逻辑和功能。使用 TypeScript 构建，遵循 Vue 3 最佳实践。

## 可用的 Composables

### 文件管理

- **`useFileType`** - 检测并处理不同的文件类型
- **`useFileUtils`** - 文件操作工具函数

### UI 和布局

- **`useBasicLayout`** - 基础布局管理工具
- **`useBoolean`** - 反应式布尔状态管理
- **`useBubbleMenu`** - 气泡菜单定位和状态
- **`useScrollTrap`** - 滚动行为管理
- **`usePagination`** - 分页状态和控制

### 搜索和数据

- **`useMinisearch`** - 使用 MiniSearch 的全文搜索功能
- **`useLoading`** - 加载状态管理
- **`useClosableMessage`** - 带自动关闭的消息通知

### 导航和工具

- **`useNewTab`** - 新标签页/窗口管理
- **`useHtmlToPdf`** - HTML 到 PDF 转换工具

### 事件系统

- **`eventBus`** - 用于组件通信的全局事件总线

## 导出

所有 composables 和工具函数都从主入口点导出：

```typescript
import { 
  useBoolean, 
  useFileType, 
  useLoading,
  eventBus 
} from '@airalogy/composables'
```

### 文件管理 Composables

- **`useFileType`** - 检测并处理不同的文件类型
  - 返回用于检查文件类型的辅助函数
  - 支持图像、PDF、代码和更多文件类型
  - 返回文件类型元数据（图标、颜色等）

- **`useFileUtils`** - 文件操作工具
  - 文件读写操作
  - 大小计算和格式化
  - MIME 类型检测

### UI 和布局 Composables

- **`useBasicLayout`** - 基础布局管理工具
  - 侧边栏可见性状态
  - 布局模式管理
  - 响应式布局助手

- **`useBoolean`** - 反应式布尔状态管理
  - 简单的开/关状态管理
  - 实用方法（setTrue、setFalse、toggle）
  - 重置功能

- **`useBubbleMenu`** - 气泡菜单定位和状态
  - 菜单可见性和定位
  - 相对于选择的位置跟踪
  - 模糊时自动隐藏

- **`useScrollTrap`** - 滚动行为管理
  - 防止滚动传播
  - 将滚动锁定到特定元素
  - 恢复滚动行为

- **`usePagination`** - 分页状态和控制
  - 页面状态管理
  - 导航方法
  - 每页项目数配置

### 搜索和数据 Composables

- **`useMinisearch`** - 使用 MiniSearch 的全文搜索功能
  - 文档索引
  - 全文搜索
  - 结果排名和过滤
  - 支持自定义字段权重

- **`useLoading`** - 加载状态管理
  - 加载状态反应式 ref
  - 启动/停止加载方法
  - 异步操作包装器

- **`useClosableMessage`** - 带自动关闭的消息通知
  - 消息队列管理
  - 自动关闭计时器
  - 不同的消息类型（信息、成功、错误、警告）

### 导航和工具 Composables

- **`useNewTab`** - 新标签页/窗口管理
  - 在新标签页/窗口中打开链接
  - 窗口功能配置
  - 窗口引用处理

- **`useHtmlToPdf`** - HTML 到 PDF 转换工具
  - 将 HTML 转换为 PDF
  - 可自定义选项（边距、尺寸、方向）
  - 下载或返回 blob

### 事件系统

- **`eventBus`** - 用于组件通信的全局事件总线
  - 发布/订阅模式
  - 事件发射和监听
  - 一次性监听器
  - 使用 TypeScript 的事件类型安全

## 安装

```bash
pnpm install @airalogy/composables
```

## 使用

### 基础布尔状态

```typescript
import { useBoolean } from "@airalogy/composables"

const { bool: isVisible, setTrue: show, setFalse: hide, toggle } = useBoolean(false)

// 在模板中使用
show() // 将 isVisible 设置为 true
hide() // 将 isVisible 设置为 false
toggle() // 切换 isVisible
```

### 文件类型检测

```typescript
import { useFileType } from "@airalogy/composables"

const { getFileType, isImage, isPdf, isCode } = useFileType()

const fileType = getFileType("document.pdf")
// 返回: { type: 'pdf', icon: 'pdf-icon', color: 'red' }

if (isImage("photo.jpg")) {
  // 处理图像文件
}
```

### 搜索功能

```typescript
import { useMinisearch } from "@airalogy/composables"

const searchOptions = {
  fields: ["title", "content", "tags"],
  storeFields: ["title", "id"],
}

const { search, addDocument, removeDocument, clearIndex } = useMinisearch(searchOptions)

// 添加文档
addDocument({ id: "1", title: "研究论文", content: "内容..." })

// 搜索
const results = search("research")
```

### 加载状态管理

```typescript
import { useLoading } from "@airalogy/composables"

const { loading, startLoading, stopLoading, withLoading } = useLoading()

// 手动控制
startLoading()
// ... 异步操作
stopLoading()

// 使用异步函数自动控制
await withLoading(async () => {
  // 这个函数将自动显示/隐藏加载
  await fetchData()
})
```

### HTML 到 PDF 转换

```typescript
import { useHtmlToPdf } from "@airalogy/composables"

const { generatePdf, downloading } = useHtmlToPdf()

const options = {
  margin: 1,
  filename: "document.pdf",
  image: { type: "jpeg", quality: 0.98 },
  html2canvas: { scale: 2 },
  jsPDF: { unit: "in", format: "letter", orientation: "portrait" },
}

await generatePdf(elementRef.value, options)
```

### 事件总线

```typescript
import { eventBus } from "@airalogy/composables"

// 发射事件
eventBus.emit("user-login", { userId: "123" })

// 监听事件
eventBus.on("user-login", (data) => {
  console.log("用户已登录:", data.userId)
})

// 一次性监听
eventBus.once("app-ready", () => {
  console.log("应用就绪!")
})

// 移除监听
eventBus.off("user-login", handler)
```

## 🔧 开发

### 脚本命令

```bash
# 类型检查
pnpm type-check

# 生产环境构建
pnpm build

# 开发准备
pnpm build:prepare
```

### 依赖

本包依赖于多个对等依赖：

- **Vue 3** - Composition API
- **VueUse Core** - Vue Composition 工具
- **Naive UI** - 某些 composables 的 UI 组件

### 主要特性

- **完全类型化** - 完整的 TypeScript 支持和适当的类型推断
- **树可摇** - 仅导入所需的内容
- **SSR 就绪** - 服务端渲染兼容
- **Vue 3 原生** - 专为 Vue 3 Composition API 构建
- **反应式** - 利用 Vue 的反应性系统

## 架构

所有 composables 遵循这些原则：

1. **单一职责** - 每个 composable 有明确、专注的目的
2. **默认反应式** - 返回反应式 refs 和计算属性
3. **可组合** - 可以轻松与其他 composables 组合
4. **类型安全** - 完整的 TypeScript 支持和适当的泛型
5. **内存高效** - 适当的清理和内存管理

## 贡献指南

1. 遵循 Vue 3 Composition API 最佳实践
2. 使用 TypeScript 和适当的类型定义
3. 包含详细的 JSDoc 注释
4. 为新 composables 编写测试
5. 在 `onUnmounted` 中确保适当的清理
6. 遵循现有的命名约定

### 创建新的 Composables

```typescript
// useExample.ts
import { computed, onUnmounted, ref, readonly } from "vue"

export function useExample(initialValue: string = "") {
  const value = ref(initialValue)
  const upperValue = computed(() => value.value.toUpperCase())

  const setValue = (newValue: string) => {
    value.value = newValue
  }

  const reset = () => {
    value.value = initialValue
  }

  // 如需要，进行清理
  onUnmounted(() => {
    // 清理逻辑
  })

  return {
    value: readonly(value),
    upperValue,
    setValue,
    reset,
  }
}
```

## 许可证

Airalogy 单体仓库的一部分。保留所有权利。
