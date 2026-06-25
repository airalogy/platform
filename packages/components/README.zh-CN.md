# @airalogy/components

> Airalogy 研究平台的共享 Vue 组件

## 概述

本包提供专为 Airalogy 平台设计的可复用 Vue 3 组件的全面集合。这些组件处理从使用 TipTap 进行富文本编辑到文件预览、聊天功能、协议管理和 UI 工具的所有功能。所有组件都使用 TypeScript 构建，遵循 Composition API 模式，并与 Airalogy 生态系统的其余部分无缝集成。

## 组件

### 聊天系统

- **`ChatComponent`** - 完整的聊天界面，支持 AI 集成
  - 消息历史和线程
  - 实时消息更新
  - AI 响应流式传输
  - 用户头像和状态指示器
  - 消息搜索和过滤
  - 基于提供者的上下文管理

### 编辑器和内容

- **`MarkdownEditor`** - 使用 TipTap 构建的富 Markdown 编辑器
  - 实时预览和协作编辑
  - 支持表格、代码块、数学表达式（KaTeX）
  - 可使用自定义插件进行扩展
  - 气泡菜单和浮动工具栏
  - Markdown 到 HTML 导出
  - 所见即所得编辑体验

- **`CodeEditor`** - Monaco 编辑器集成
  - 100+ 种语言的语法高亮
  - 代码补全和 IntelliSense
  - 迷你地图和概览标尺
  - 代码格式化和美化
  - 行号和代码折叠
  - 多文件编辑支持

### 文件管理

- **`FilePreview`** - 通用文件预览组件
  - 支持多种文件格式（PDF、图像、代码、Markdown、CSV、ZIP）
  - 文件下载和共享
  - 缩放和导航控件
  - 预览中的代码语法高亮

- **`CsvPreview`** - 专用 CSV 文件查看器
  - 具有排序和过滤的数据表
  - 大文件支持和虚拟化
  - 列调整大小和重新排序
  - 导出为不同格式

- **`PdfPreview`** - PDF 文档查看器
  - 页面导航和搜索
  - 文本选择和复制
  - 缩放控制
  - 全屏模式

- **`ImagePreview`** - 带工具的图像查看器
  - 缩放和平移控制
  - 旋转和翻转
  - 下载和共享

- **`CodePreview`** - 语法高亮代码查看器
  - 语言检测
  - 行突出显示和复制
  - 复制到剪贴板，带有反馈

- **`FileTypeIcon`** - 动态文件类型图标
  - 100+ 文件类型支持
  - 可自定义的颜色和尺寸
  - 图标主题支持

### 文件操作

- **`FileTree`** - 分层文件浏览器
  - 展开/折叠目录
  - 文件操作（重命名、删除、移动）
  - 拖放支持
  - 搜索和过滤
  - 键盘导航

- **`FilePathExplorer`** - 面包屑式路径导航
- **`FileUpload`** - 拖放文件上传，带进度

### 协议管理

- **`ProtocolBubbleMenu`** - 用于协议交互的浮动菜单
- **`ProtocolInfoCard`** - 显示协议元数据和信息
- **`ProtocolGenerator`** - 交互式协议生成界面
- **`ProtocolDocuments`** - 协议文档查看和管理
- **`ProtocolMetadataForm`** - 可编辑的协议元数据

### UI 组件

- **`CopyToClip`** - 复制到剪贴板功能
  - 复制时的视觉反馈
  - 自定义复制文本
  - 成功通知

- **`TooltipButton`** - 带内置工具提示的按钮组件
  - 工具提示定位选项
  - 键盘快捷键显示
  - 工具提示主题

- **`LangSwitch`** - 国际化语言切换器
  - 带有标志的语言列表
  - 持久选择
  - 即时语言切换

- **`PinInput`** - PIN/代码输入组件
  - 字段间自动焦点
  - 数字或字母数字支持
  - 安全掩码选项

- **`CountryPhoneInput`** - 国际电话号码输入
  - 国家代码选择
  - 电话号码验证
  - 格式支持

- **`IdInput`** - 带验证的通用标识符输入
- **`VersionInput`** - 版本号输入

### 布局组件

- **`EditorContainer`** - 带工具栏的代码编辑器容器
- **`SplitEditor`** - 并排编辑器布局
- **`TabBar`** - 带自定义的选项卡导航
- **`TabHeader`** - 带关闭按钮的选项卡标题
- **`BreadcrumbsBelowTabs`** - 选项卡下方的导航面包屑

### 输出和显示

- **`OutputError`** - 错误显示，带堆栈跟踪和友好消息
  - Python 回溯渲染
  - 框架和行突出显示
  - 复制堆栈跟踪
  - 大回溯的分页

- **`VoiceInputStatus`** - 语音输入状态指示器
- **`CommonIdInput`** - 公共 ID 输入组件
- **`CommonVersionInput`** - 公共版本输入组件

## 安装

```bash
pnpm add @airalogy/components
```

## 使用

### 基础导入

```typescript
import { ChatComponent, FilePreview, MarkdownEditor } from "@airalogy/components"
import "@airalogy/components/styles"  // 导入组件样式
```

### 组件使用示例

#### Markdown 编辑器

```vue
<template>
  <markdown-editor 
    v-model="content" 
    placeholder="开始写作..." 
    :editable="true"
    @update:model-value="saveContent"
  />
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { MarkdownEditor } from "@airalogy/components"

const content = ref('')

function saveContent(newContent: string) {
  // 自动保存逻辑
}
</script>
```

#### 聊天组件

```vue
<template>
  <chat-component 
    :messages="chatMessages" 
    @send-message="handleMessage"
    @clear-history="clearMessages"
  />
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ChatComponent } from "@airalogy/components"

const chatMessages = ref([])

function handleMessage(message: string) {
  // 处理用户消息
}

function clearMessages() {
  chatMessages.value = []
}
</script>
```

#### 文件预览

```vue
<template>
  <file-preview 
    :file="selectedFile" 
    :show-download="true"
    @download="downloadFile"
  />
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { FilePreview } from "@airalogy/components"

const selectedFile = ref(null)

function downloadFile(file: File) {
  // 处理文件下载
}
</script>
```

#### 代码编辑器

```vue
<template>
  <code-editor 
    v-model="code"
    language="typescript"
    theme="github-dark"
    :line-numbers="true"
  />
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { CodeEditor } from "@airalogy/components"

const code = ref('')
</script>
```

#### 文件树

```vue
<template>
  <file-tree 
    :files="fileStructure"
    @select="selectFile"
    @delete="deleteFile"
  />
</template>

<script setup lang="ts">
const fileStructure = ref([
  {
    name: 'src',
    type: 'folder',
    children: [
      { name: 'main.ts', type: 'file' },
    ]
  }
])
</script>
```

## 开发

### 脚本命令

```bash
# 类型检查
pnpm type-check

# 生产环境构建
pnpm build

# 测试构建
pnpm build:test

# 开发构建（不清空输出）
pnpm build:prepare
```

### 依赖

本包依赖于多个对等依赖，应该在项目中安装：

- **Vue 3** - 组件框架
- **Naive UI** - UI 组件库
- **VueUse** - Vue Composition 工具
- **TipTap** - 富文本编辑框架
- **Monaco 编辑器** - 代码编辑器
- **Markdown-it** - Markdown 解析
- **KaTeX** - 数学表达式渲染
- **Mermaid** - 图表渲染
- **PDF.js** - PDF 查看
- **Pyodide** - Python 运行时（用于代码执行）
- **xterm** - 终端仿真

### 架构

所有组件使用以下技术构建：

- **Vue 3 Composition API** 配合 `<script setup>`
- **TypeScript** 用于类型安全和更好的 IDE 支持
- **TipTap** 用于富文本编辑功能
- **Naive UI** 用于一致的样式和 UI 模式
- **Pinia** 用于复杂组件中的状态管理
- **UnoCSS** 用于原子样式

### 组件模式

#### Prop 验证

```typescript
interface ComponentProps {
  modelValue: string
  disabled?: boolean
  readonly?: boolean
}

withDefaults(defineProps<ComponentProps>(), {
  disabled: false,
  readonly: false,
})
```

#### 事件 Emits

```typescript
const emit = defineEmits<{
  'update:modelValue': [value: string]
  'change': [event: Event]
  'save': [content: string]
}>()
```

#### Composition API 模式

```typescript
const { data, loading, error } = useFetchData()
const { startLoading, stopLoading } = useLoading()
```

## 样式

组件使用 UnoCSS 进行样式设计，遵循 Airalogy 设计系统。它们自动适应：

- **主题设置** - 亮色/暗色模式支持
- **响应式设计** - 移动、平板、桌面断点
- **可访问性** - WCAG 2.1 AA 兼容
- **自定义 CSS** - 用于主题化的 CSS 变量覆盖

### 自定义主题

```css
:root {
  /* 主色 */
  --color-primary: #3b82f6;
  --color-primary-dark: #1e40af;
  
  /* 背景色 */
  --color-background: #ffffff;
  --color-surface: #f3f4f6;
  
  /* 文本色 */
  --color-text: #1f2937;
  --color-text-secondary: #6b7280;
}

[data-theme="dark"] {
  --color-primary: #60a5fa;
  --color-background: #1f2937;
  --color-surface: #111827;
  --color-text: #f3f4f6;
  --color-text-secondary: #d1d5db;
}
```

## 相关包

- **@airalogy/aimd-core** - 核心 AIMD 解析器
- **@airalogy/aimd-renderer** - AIMD 渲染引擎
- **@airalogy/aimd-recorder** - AIMD 编辑器组件
- **@airalogy/composables** - Vue Composables
- **@airalogy/shared** - 共享工具

## 贡献指南

1. 遵循 Vue 3 Composition API 模式和最佳实践
2. 为所有新组件使用 TypeScript，并包含适当的类型定义
3. 包含详细的 prop 验证和 TypeScript 接口
4. 为公开 API 和复杂逻辑添加 JSDoc 注释
5. 确保组件响应式、可访问且可主题化
6. 为组件逻辑编写单元测试
7. 在 README 中更新新组件文档
8. 遵循 JavaScript 标准样式进行代码格式化

## 性能

组件针对性能进行了优化：

- **代码分割** - 大型编辑器按需加载
- **延迟加载** - 重型依赖在需要时加载
- **虚拟化** - 大型列表使用虚拟滚动
- **记忆化** - Props 和计算值适当记忆化
- **树摇** - 只导入所需的组件

## 许可证

Airalogy 单体仓库的一部分。保留所有权利。
