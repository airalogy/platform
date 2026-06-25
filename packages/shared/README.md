# @airalogy/shared

> Shared utilities, constants, and types for the Airalogy research platform

## Overview

This package contains shared utilities, constants, type definitions, themes, and enums that are used across the entire Airalogy platform. It provides a centralized location for common functionality that needs to be consistent across different applications and packages.

## What's Included

### Utilities

- **Request utilities** - HTTP request helpers with streaming support (SSE, EventSource)
- **File utilities** - File type detection, conversion, and validation functions
- **Schema utilities** - JSON schema validation and helpers
- **Change case utilities** - String case transformation functions (camelCase, kebabCase, snakeCase, pascalCase)
- **Clipboard utilities** - Copy-to-clipboard functionality
- **Download utilities** - File download helpers
- **Date utilities** - Date formatting and manipulation with Day.js integration
- **Error formatting** - Error message formatting and traceback handling
- **Storage utilities** - Local storage and IndexedDB helpers with monitoring
- **URI utilities** - URL parsing and manipulation
- **Var type parser** - Parse and validate AIMD variable types
- **ISO duration** - Parse ISO 8601 duration strings

### Constants & Enums

- **Editor constants** - Configuration for various editors (themes, layouts, settings)
- **Content layout** - Layout-related constants for UI structure
- **Country codes** - International country code mappings
- **Event keys** - Event key constants for system communication
- **Protocol constants** - Protocol-related constants and configurations
- **Chat enums** - Chat system constants and message types
- **Editor enums** - Editor modes, themes, and states
- **Airalogy enums** - Platform-specific constants and status

### Type Definitions

- **Common types** - Shared TypeScript interfaces and types
- **Model definitions** - Data model interfaces (protocol, chat, attachment)
- **Environment types** - Environment configuration and runtime types
- **API types** - API request/response interfaces
- **Theme types** - Theme and color configuration types
- **Field types** - AIMD field definitions and record structures
- **Union key types** - Type-safe union key utilities
- **Auto imports** - TypeScript auto-import declarations

### Theme System

- **Color palette** - Predefined color schemes and color utilities
- **Theme variables** - CSS-in-JS theme configuration
- **Color manipulation** - Advanced color utilities with Colord.js

### Assets

- **Icons** - 60+ SVG icons for UI components
  - Navigation: menu, breadcrumb, arrow icons
  - Document: file, folder, protocol icons
  - Action: save, delete, edit, search icons
  - Status: processing, cloud, record status icons
  - And more...

### Internationalization

- **Locale configuration** - Multi-language support (English, Simplified Chinese)
- **Day.js localization** - Date/time formatting for different languages
- **Translation management** - Vue i18n integration and locale loading

## Installation

```bash
pnpm add @airalogy/shared
```

## Usage

### Request Utilities

```typescript
import { createApiClient, handleApiError } from "@airalogy/shared"

// Create API client with default configuration
const apiClient = createApiClient({
  baseURL: "http://127.0.0.1:4000",
  timeout: 10000,
})

// Handle API errors consistently
try {
  const response = await apiClient.get("/data")
}
catch (error) {
  const handledError = handleApiError(error)
  console.error(handledError.message)
}
```

### File Utilities

```typescript
import { formatFileSize, getFileExtension, validateFileType } from "@airalogy/shared"

// Validate file type
const isValidImage = validateFileType(file, ["jpg", "png", "gif"])

// Format file size for display
const formattedSize = formatFileSize(1024000) // "1.02 MB"

// Get file extension
const extension = getFileExtension("document.pdf") // "pdf"

// Detect file type
const { type, icon, color } = getFileType("document.pdf")
```

### Constants and Enums

```typescript
import { ChatMessageType, CONTENT_LAYOUTS, EDITOR_THEMES, FileType } from "@airalogy/shared"

// Use editor themes
const currentTheme = EDITOR_THEMES.DARK

// Use layout constants
const layout = CONTENT_LAYOUTS.SIDEBAR_LEFT

// Use chat enums
if (message.type === ChatMessageType.AI_RESPONSE) {
  // Handle AI response
}

// Use file type enum
if (file.type === FileType.PDF) {
  // Handle PDF file
}
```

### Schema Validation

```typescript
import { commonSchemas, createValidator } from "@airalogy/shared"

// Create validator for user data
const validateUser = createValidator(commonSchemas.user)

const result = validateUser({
  id: "123",
  email: "user@example.com",
  name: "John Doe",
})

if (!result.valid) {
  console.error("Validation errors:", result.errors)
}
```

### Internationalization

```typescript
import { loadLocale, setupI18n } from "@airalogy/shared"

// Setup i18n with default configuration
const i18n = setupI18n({
  locale: "en",
  fallbackLocale: "en",
})

// Load additional locale
await loadLocale("zh-CN")
```

### Change Case Utilities

```typescript
import { camelCase, kebabCase, pascalCase, snakeCase } from "@airalogy/shared"

const text = "hello world example"

console.log(camelCase(text)) // "helloWorldExample"
console.log(kebabCase(text)) // "hello-world-example"
console.log(snakeCase(text)) // "hello_world_example"
console.log(pascalCase(text)) // "HelloWorldExample"
```

### Storage Utilities

```typescript
import { useLocalStorage, useSessionStorage } from "@airalogy/shared"

// Simple key-value storage
const token = useLocalStorage("auth_token", "")
token.value = "abc123"

// Storage with monitoring
import { StorageMonitor } from "@airalogy/shared"
const monitor = new StorageMonitor()
monitor.track("key")
```

### Date Utilities

```typescript
import { formatDate, parseDate, getDaysDiff } from "@airalogy/shared"

const now = new Date()
const formatted = formatDate(now, "YYYY-MM-DD") // "2024-01-28"
const diff = getDaysDiff(now, new Date(now.getTime() + 86400000)) // 1
```

## Exports

### Main Entry (`@airalogy/shared`)

All utilities, constants, enums, types, and theme exports from the main entry point.

```typescript
import {
  // Constants
  CONTENT_LAYOUTS,
  EDITOR_THEMES,
  // Enums
  ChatMessageType,
  EditorMode,
  // Utils
  formatFileSize,
  formatDate,
  // Types
  type Protocol,
  type ChatMessage,
} from "@airalogy/shared"
```

### Utils Entry (`@airalogy/shared/utils`)

Direct access to utility functions:

```typescript
import {
  formatFileSize,
  validateFileType,
  formatDate,
  camelCase
} from "@airalogy/shared/utils"
```

### Unified Entry (`@airalogy/shared/unified`)

AIMD and Markdown-it related exports:

```typescript
import { /* unified markdown utilities */ } from "@airalogy/shared/unified"
```

## Development

### Scripts

```bash
# Type checking
pnpm type-check

# Build for production
pnpm build

# Build type declarations
pnpm build:types
```

### AIMD Grammar Testing

The AIMD (Airalogy Markdown) syntax highlighting is tested using TextMate grammar tests. This ensures that syntax highlighting works correctly across different editors (VS Code, Monaco, Shiki).

#### Grammar Files

| File | Description |
|------|-------------|
| `packages/shared/src/constants/aimd/aimdSyntax.ts` | Shiki/TextMate grammar definition |
| `packages/shared/src/constants/aimd/aimd.ts` | Monaco Editor grammar definition |
| `packages/shared/src/constants/aimd/tokens.ts` | Token/scope name definitions |
| `test/grammar/aimd.tmLanguage.json` | Generated TextMate grammar file |
| `test/grammar/aimd.test.aimd` | Grammar test cases |
| `scripts/generate-grammar.ts` | Grammar and test generator script |

#### Running Grammar Tests

```bash
# From the monorepo root:

# Generate grammar files and run tests
pnpm grammar:test

# Only regenerate grammar files (without testing)
pnpm grammar:generate
```

#### Test File Format

The test file uses the standard TextMate grammar test format:

```aimd
{{var|name: str}}
//<- punctuation.definition.begin.aimd    ← Tests {{ token
//^^^ keyword.variable.aimd               ← Tests var token
//   ^ delimiter.pipe.aimd                ← Tests | token
//    ^^^^ variable.other.aimd            ← Tests name token
//        ^ delimiter.colon.aimd          ← Tests : token
//          ^^^ support.type.aimd         ← Tests str token
```

- `//<-` tests the token at the start of the previous line
- `//^^^` each `^` corresponds to a character position on the previous line
- Spaces are used for alignment and indicate positions not being tested

#### Adding New Test Cases

1. Edit `scripts/generate-grammar.ts` to add new test generation logic
2. Run `pnpm grammar:generate` to regenerate test files
3. Run `pnpm grammar:test` to verify all tests pass

#### Supported AIMD Type Syntax

The grammar supports the new type syntax for variables:

```aimd
{{var|name: str}}                              # Simple type
{{var|age: int = 18}}                          # Type with default
{{var|name: str = "张三", title = "姓名"}}      # With kwargs
{{var|active: bool = true}}                    # Boolean type
{{var|students: list[Student], subvars=[...]}} # List with subvars
```

### Dependencies

This package includes:

- **Core utilities** - Lodash-ES, Day.js, nanoid
- **Color utilities** - Colord for advanced color manipulation
- **File handling** - JS-YAML, Big.js, LocalForage, fflate
- **Markdown/Unified** - Remark, Rehype, Shiki for markdown processing
- **Internationalization** - Vue i18n
- **Schema validation** - AJV, async-validator
- **DOM utilities** - DOMPurify

### Peer Dependencies

- **@monaco-editor/loader** - Monaco editor loader
- **@vueuse/core** - Vue composition utilities
- **Day.js** - Date manipulation
- **Lodash-ES** - Utility functions
- **nanoid** - Unique ID generation

## Architecture

### Modular Design

All utilities are organized into logical modules that can be imported independently:

```typescript
import { ChatMessageType } from "@airalogy/shared/enum"
import { createMarkdownRenderer } from "@airalogy/shared/unified"
// Import specific utilities
import { formatDate } from "@airalogy/shared/utils"

// Or import everything (not recommended for production)
import * as shared from "@airalogy/shared"
```

### Type Safety

Full TypeScript support with:

- Strict type checking
- Generic type utilities
- Comprehensive interface definitions
- Proper type exports
- Model types for API responses

### Tree Shaking

Optimized for tree shaking to ensure minimal bundle size:

- Named exports only
- No side effects in utility functions
- Modular structure for selective imports
- Icon assets included as SVG files

## Asset Management

### Icons

The package includes 60+ SVG icons organized by category:

```typescript
import IconAdd from "@airalogy/shared/assets/icons/add-circle.svg"
import IconDelete from "@airalogy/shared/assets/icons/delete.svg"
// Or use in dynamic imports for better tree shaking
```

## Extending

### Adding New Utilities

```typescript
// utils/myUtility.ts
export function myUtility(input: string): string {
  // Implementation
  return processed
}

// Add to utils/index.ts
export * from "./myUtility"

// Add to main index.ts if needed
export * from "./utils"
```

### Adding New Constants

```typescript
// constants/myConstants.ts
export const MY_CONSTANTS = {
  VALUE_ONE: "value1",
  VALUE_TWO: "value2",
} as const

// Add to constants/index.ts
export * from "./myConstants"
```

### Adding New Themes

```typescript
// theme/myTheme.ts
export const MY_THEME = {
  colors: {
    primary: "#3b82f6",
    secondary: "#8b5cf6",
  },
}

// Add to theme/index.ts
export * from "./myTheme"
```

## Contributing

1. **Follow TypeScript best practices** - Use strict typing
2. **Add comprehensive JSDoc comments** - Document all public APIs
3. **Write unit tests** - Test all utility functions
4. **Maintain backward compatibility** - Use deprecation warnings when needed
5. **Update documentation** - Keep README and inline docs current
6. **Follow JavaScript Standard Style** - Consistent code formatting

## Performance Considerations

- **Lazy loading** - Use dynamic imports for heavy utilities
- **Tree shaking** - Ensure named exports for better optimization
- **Caching** - Storage utilities support caching strategies
- **Memory efficiency** - Storage monitor tracks memory usage

## License

Part of the Airalogy monorepo. All rights reserved.
