# @airalogy/components

> Shared Vue components for the Airalogy research platform

## Overview

This package provides a comprehensive collection of reusable Vue 3 components built specifically for the Airalogy platform. These components handle everything from rich text editing with TipTap to file preview, chat functionality, protocol management, and UI utilities. All components are built with TypeScript, follow the Composition API pattern, and integrate seamlessly with the rest of the Airalogy ecosystem.

## Components

### Chat System

- **`ChatComponent`** - Complete chat interface with AI integration
  - Message history and threading
  - Real-time message updates
  - AI response streaming
  - User avatar and status indicators
  - Message search and filtering
  - Provider-based context management

### Editors & Content

- **`MarkdownEditor`** - Rich markdown editor built with TipTap
  - Real-time preview and collaborative editing
  - Support for tables, code blocks, math expressions (KaTeX)
  - Extensible with custom plugins
  - Bubble menu and floating toolbar
  - Markdown-to-HTML export
  - WYSIWYG editing experience

- **`CodeEditor`** - Monaco Editor integration
  - Syntax highlighting for 100+ languages
  - Code completion and IntelliSense
  - Minimap and overview ruler
  - Code formatting and beautification
  - Line numbers and folding
  - Multi-file editing support

### File Management

- **`FilePreview`** - Universal file preview component
  - Supports multiple file formats (PDF, images, code, markdown, CSV, ZIP)
  - File download and sharing
  - Zoom and navigation controls
  - Code syntax highlighting in previews

- **`CsvPreview`** - Specialized CSV file viewer
  - Data table with sorting and filtering
  - Large file support with virtualization
  - Column resizing and reordering
  - Export to different formats

- **`PdfPreview`** - PDF document viewer
  - Page navigation and search
  - Text selection and copying
  - Zoom controls
  - Full-screen mode

- **`ImagePreview`** - Image viewer with tools
  - Zoom and pan controls
  - Rotation and flip
  - Download and share

- **`CodePreview`** - Syntax-highlighted code viewer
  - Language detection
  - Line highlighting and copying
  - Copy-to-clipboard with feedback

- **`FileTypeIcon`** - Dynamic file type icons
  - 100+ file type support
  - Customizable colors and sizes
  - Icon theme support

### File Operations

- **`FileTree`** - Hierarchical file browser
  - Expand/collapse directories
  - File operations (rename, delete, move)
  - Drag-and-drop support
  - Search and filter
  - Keyboard navigation

- **`FilePathExplorer`** - Breadcrumb-style path navigation
- **`FileUpload`** - Drag-and-drop file upload with progress

### Protocol Management

- **`ProtocolBubbleMenu`** - Floating menu for protocol interactions
- **`ProtocolInfoCard`** - Display protocol metadata and information
- **`ProtocolGenerator`** - Interactive protocol generation interface
- **`ProtocolDocuments`** - Protocol document viewing and management
- **`ProtocolMetadataForm`** - Editable protocol metadata

### UI Components

- **`CopyToClip`** - Copy-to-clipboard functionality
  - Visual feedback on copy
  - Custom copy text
  - Success notifications

- **`TooltipButton`** - Button component with built-in tooltip
  - Tooltip positioning options
  - Keyboard shortcuts display
  - Tooltip themes

- **`LangSwitch`** - Language switcher for internationalization
  - Language list with flags
  - Persistent selection
  - Instant language switching

- **`PinInput`** - PIN/code input component
  - Auto-focus between fields
  - Numeric or alphanumeric support
  - Security masking option

- **`CountryPhoneInput`** - International phone number input
  - Country code selection
  - Phone number validation
  - Format support

- **`IdInput`** - Common identifier input with validation
- **`VersionInput`** - Version number input

### Layout Components

- **`EditorContainer`** - Container for code editor with toolbar
- **`SplitEditor`** - Side-by-side editor layout
- **`TabBar`** - Tab navigation with customization
- **`TabHeader`** - Tab header with close buttons
- **`BreadcrumbsBelowTabs`** - Navigation breadcrumbs below tabs

### Output & Display

- **`OutputError`** - Error display with stack traces and friendly messages
  - Python traceback rendering
  - Frame and line highlighting
  - Copy stack trace
  - Pagination for large tracebacks

- **`VoiceInputStatus`** - Voice input status indicator
- **`CommonIdInput`** - Common ID input component
- **`CommonVersionInput`** - Common version input component

## Installation

```bash
pnpm add @airalogy/components
```

## Usage

### Basic Import

```typescript
import { ChatComponent, FilePreview, MarkdownEditor } from "@airalogy/components"
import "@airalogy/components/styles"  // Import component styles
```

### Component Usage Examples

#### Markdown Editor

```vue
<template>
  <markdown-editor 
    v-model="content" 
    placeholder="Start writing..." 
    :editable="true"
    @update:model-value="saveContent"
  />
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { MarkdownEditor } from "@airalogy/components"

const content = ref('')

function saveContent(newContent: string) {
  // Auto-save logic
}
</script>
```

#### Chat Component

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
  // Handle user message
}

function clearMessages() {
  chatMessages.value = []
}
</script>
```

#### File Preview

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
  // Handle file download
}
</script>
```

#### Code Editor

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

#### File Tree

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

## Development

### Scripts

```bash
# Type checking
pnpm type-check

# Build for production
pnpm build

# Build for testing
pnpm build:test

# Build for development (without clearing output)
pnpm build:prepare
```

### Dependencies

This package relies on several peer dependencies:

- **Vue 3** - Component framework
- **Naive UI** - UI component library
- **VueUse** - Vue composition utilities
- **TipTap** - Rich text editing framework
- **Monaco Editor** - Code editor
- **Markdown-it** - Markdown parsing
- **KaTeX** - Mathematical expression rendering
- **Mermaid** - Diagram rendering
- **PDF.js** - PDF viewing
- **Pyodide** - Python runtime (for code execution)
- **xterm** - Terminal emulation

### Architecture

All components are built using:

- **Vue 3 Composition API** with `<script setup>`
- **TypeScript** for type safety and better IDE support
- **TipTap** for rich text editing capabilities
- **Naive UI** for consistent styling and UI patterns
- **Pinia** for state management in complex components
- **UnoCSS** for utility-first styling

### Component Patterns

#### Prop Validation

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

#### Event Emits

```typescript
const emit = defineEmits<{
  'update:modelValue': [value: string]
  'change': [event: Event]
  'save': [content: string]
}>()
```

#### Composition API Patterns

```typescript
const { data, loading, error } = useFetchData()
const { startLoading, stopLoading } = useLoading()
```

## Styling

Components use UnoCSS for styling and follow the Airalogy design system. They automatically adapt to:

- **Theme Settings** - Light/dark mode support
- **Responsive Design** - Mobile, tablet, desktop breakpoints
- **Accessibility** - WCAG 2.1 AA compliant
- **Custom CSS** - CSS variable overrides for theming

### Custom Theming

```css
:root {
  /* Primary colors */
  --color-primary: #3b82f6;
  --color-primary-dark: #1e40af;
  
  /* Background colors */
  --color-background: #ffffff;
  --color-surface: #f3f4f6;
  
  /* Text colors */
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

## Related Packages

- **@airalogy/aimd-core** - Core AIMD parser
- **@airalogy/aimd-renderer** - AIMD rendering engine
- **@airalogy/aimd-recorder** - AIMD editor components
- **@airalogy/composables** - Vue composables
- **@airalogy/shared** - Shared utilities

## Contributing

1. Follow the Vue 3 Composition API patterns and best practices
2. Use TypeScript for all new components with proper type definitions
3. Include comprehensive prop validation and TypeScript interfaces
4. Add JSDoc comments for public APIs and complex logic
5. Ensure components are responsive, accessible, and themeable
6. Write unit tests for component logic
7. Update README with new component documentation
8. Follow JavaScript Standard Style for code formatting

## Performance

Components are optimized for performance:

- **Code Splitting** - Large editors load on-demand
- **Lazy Loading** - Heavy dependencies loaded when needed
- **Virtualization** - Large lists use virtual scrolling
- **Memoization** - Props and computeds properly memoized
- **Tree Shaking** - Only import needed components

## License

Part of the Airalogy monorepo. All rights reserved.
