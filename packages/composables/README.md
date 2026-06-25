# @airalogy/composables

> Reusable Vue composables for the Airalogy research platform

## Overview

This package provides a collection of Vue 3 composables that encapsulate common reactive logic and functionality used throughout the Airalogy platform. Built with TypeScript and following Vue 3 best practices.

## Available Composables

### File Management

- **`useFileType`** - Detect and handle different file types
- **`useFileUtils`** - File manipulation utilities

### UI & Layout

- **`useBasicLayout`** - Basic layout management utilities
- **`useBoolean`** - Reactive boolean state management
- **`useBubbleMenu`** - Bubble menu positioning and state
- **`useScrollTrap`** - Scroll behavior management
- **`usePagination`** - Pagination state and controls

### Search & Data

- **`useMinisearch`** - Full-text search functionality with MiniSearch
- **`useLoading`** - Loading state management
- **`useClosableMessage`** - Message notifications with auto-close

### Navigation & Utils

- **`useNewTab`** - New tab/window management
- **`useHtmlToPdf`** - HTML to PDF conversion utilities

### Event System

- **`eventBus`** - Global event bus for component communication

## Installation

```bash
pnpm install @airalogy/composables
```

## Exports

All composables and utilities are exported from the main entry point:

```typescript
import { 
  useBoolean, 
  useFileType, 
  useLoading,
  eventBus 
} from '@airalogy/composables'
```

### File Management Composables

- **`useFileType`** - Detect and handle different file types
  - Returns helper functions to check file type
  - Supports image, PDF, code, and more file types
  - Returns file type metadata (icon, color, etc.)

- **`useFileUtils`** - File manipulation utilities
  - File reading and writing operations
  - Size calculations and formatting
  - MIME type detection

### UI & Layout Composables

- **`useBasicLayout`** - Basic layout management utilities
  - Sidebar visibility state
  - Layout mode management
  - Responsive layout helpers

- **`useBoolean`** - Reactive boolean state management
  - Simple on/off state management
  - Utility methods (setTrue, setFalse, toggle)
  - Reset functionality

- **`useBubbleMenu`** - Bubble menu positioning and state
  - Menu visibility and positioning
  - Position tracking relative to selection
  - Auto-hide on blur

- **`useScrollTrap`** - Scroll behavior management
  - Prevent scroll propagation
  - Lock scroll to specific element
  - Restore scroll behavior

- **`usePagination`** - Pagination state and controls
  - Page state management
  - Navigation methods
  - Items per page configuration

### Search & Data Composables

- **`useMinisearch`** - Full-text search functionality with MiniSearch
  - Document indexing
  - Full-text search
  - Result ranking and filtering
  - Support for custom field weights

- **`useLoading`** - Loading state management
  - Loading state reactive ref
  - Start/stop loading methods
  - Async operation wrapper

- **`useClosableMessage`** - Message notifications with auto-close
  - Message queue management
  - Auto-close timer
  - Different message types (info, success, error, warning)

### Navigation & Utils Composables

- **`useNewTab`** - New tab/window management
  - Open links in new tab/window
  - Window features configuration
  - Window reference handling

- **`useHtmlToPdf`** - HTML to PDF conversion utilities
  - Convert HTML to PDF
  - Customizable options (margins, size, orientation)
  - Download or return blob

### Event System

- **`eventBus`** - Global event bus for component communication
  - Publish/subscribe pattern
  - Event emission and listening
  - One-time listeners
  - Event type safety with TypeScript

## Usage

### Basic Boolean State

```typescript
import { useBoolean } from "@airalogy/composables"

const { bool: isVisible, setTrue: show, setFalse: hide, toggle } = useBoolean(false)

// Use in template
show() // Sets isVisible to true
hide() // Sets isVisible to false
toggle() // Toggles isVisible
```

### File Type Detection

```typescript
import { useFileType } from "@airalogy/composables"

const { getFileType, isImage, isPdf, isCode } = useFileType()

const fileType = getFileType("document.pdf")
// Returns: { type: 'pdf', icon: 'pdf-icon', color: 'red' }

if (isImage("photo.jpg")) {
  // Handle image file
}
```

### Search Functionality

```typescript
import { useMinisearch } from "@airalogy/composables"

const searchOptions = {
  fields: ["title", "content", "tags"],
  storeFields: ["title", "id"],
}

const { search, addDocument, removeDocument, clearIndex } = useMinisearch(searchOptions)

// Add documents
addDocument({ id: "1", title: "Research Paper", content: "Content..." })

// Search
const results = search("research")
```

### Loading State Management

```typescript
import { useLoading } from "@airalogy/composables"

const { loading, startLoading, stopLoading, withLoading } = useLoading()

// Manual control
startLoading()
// ... async operation
stopLoading()

// Automatic with async function
await withLoading(async () => {
  // This function will automatically show/hide loading
  await fetchData()
})
```

### HTML to PDF Conversion

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

### Event Bus

```typescript
import { eventBus } from "@airalogy/composables"

// Emit event
eventBus.emit("user-login", { userId: "123" })

// Listen for event
eventBus.on("user-login", (data) => {
  console.log("User logged in:", data.userId)
})

// One-time listener
eventBus.once("app-ready", () => {
  console.log("App is ready!")
})

// Remove listener
eventBus.off("user-login", handler)
```

## 🔧 Development

### Scripts

```bash
# Type checking
pnpm type-check

# Build for production
pnpm build

# Prepare for development
pnpm build:prepare
```

### Dependencies

This package relies on several peer dependencies:

- **Vue 3** - Composition API
- **VueUse Core** - Vue composition utilities
- **Naive UI** - UI components for certain composables

### Key Features

- **Fully Typed** - Complete TypeScript support with proper type inference
- **Tree Shakable** - Only import what you need
- **SSR Ready** - Server-side rendering compatible
- **Vue 3 Native** - Built specifically for Vue 3 Composition API
- **Reactive** - Leverages Vue's reactivity system

## Architecture

All composables follow these principles:

1. **Single Responsibility** - Each composable has a clear, focused purpose
2. **Reactive by Default** - Return reactive refs and computed properties
3. **Composable** - Can be easily combined with other composables
4. **Type Safe** - Full TypeScript support with proper generics
5. **Memory Efficient** - Proper cleanup and memory management

## Contributing

1. Follow Vue 3 Composition API best practices
2. Use TypeScript with proper type definitions
3. Include comprehensive JSDoc comments
4. Write tests for new composables
5. Ensure proper cleanup in `onUnmounted`
6. Follow the existing naming conventions

### Creating New Composables

```typescript
// useExample.ts
import { computed, onUnmounted, ref } from "vue"

export function useExample(initialValue: string = "") {
  const value = ref(initialValue)
  const upperValue = computed(() => value.value.toUpperCase())

  const setValue = (newValue: string) => {
    value.value = newValue
  }

  const reset = () => {
    value.value = initialValue
  }

  // Cleanup if needed
  onUnmounted(() => {
    // Cleanup logic
  })

  return {
    value: readonly(value),
    upperValue,
    setValue,
    reset,
  }
}
```

## License

Part of the Airalogy monorepo. All rights reserved.
