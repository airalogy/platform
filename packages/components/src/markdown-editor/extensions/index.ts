import type { Editor, Extension } from "@tiptap/vue-3"
import type { Component, ComputedRef } from "vue"

export { default as Blockquote } from "./blockquote"

// marks
export { default as Bold } from "./bold"

export { default as BulletList } from "./bullet-list"
export { default as CodeBlock } from "./code-block"
export { default as Color } from "./color"
export { default as CompactMenu } from "./compact-menu"
// nodes
export { default as Document } from "./document"
// file extensions
// export { default as FileUpload } from "./file/file-upload"
// export { default as ImageUpload } from "./file/image-upload"
// export { default as Iframe } from './iframe';

export { default as AiralogyFile } from "./file"
export { default as FileHandler } from "./file/handler"
export { default as Image } from "./file/image"
export { default as FontFamily } from "./font-family"
export { default as FontSize } from "./font-size"
export { default as FormatClear } from "./format-clear"
export { default as Fullscreen } from "./fullscreen"
export { default as HardBreak } from "./hard-break"
export { default as Heading } from "./heading"
export { default as Highlight } from "./highlight"

export { default as History, TiptapHistory } from "./history"
export { default as HorizontalRule } from "./horizontal-rule"
export { default as Indent } from "./indent"
export { default as Italic } from "./italic"
export { default as LineHeight } from "./line-height"
export { default as Link } from "./link"
export { default as TiptapMarkdown } from "./markdown/tiptap-markdown"
export { default as Mention } from "./mention"
export { default as OrderedList } from "./ordered-list"
export { default as Print } from "./print"
// export { default as CodeView } from './code-view';

export { default as Raw } from "./raw"

export { default as SelectAll } from "./select-all"
export { default as SlashCommand } from "./slash-command"

export { default as Strike } from "./strike"
export { default as Table } from "./table"

export { default as TaskList } from "./task-list"

export { default as TextAlign } from "./text-align"

export { default as Underline } from "./underline"

export { default as CharacterCount } from "@tiptap/extension-character-count"

export { default as Code } from "@tiptap/extension-code"

export { default as Dropcursor } from "@tiptap/extension-dropcursor"

// extensions
export { default as ListItem } from "@tiptap/extension-list-item"

export { default as Paragraph } from "@tiptap/extension-paragraph"

export { default as Placeholder } from "@tiptap/extension-placeholder"

export { default as Text } from "@tiptap/extension-text"

export { default as TextStyle } from "@tiptap/extension-text-style"

export interface RendererSpec {
  component: Component
  componentProps?: ComputedRef<Record<string, any>>
  componentEvents?: any
}

export interface VisibleItem<T = any> {
  extension: ExtensionWithRenderer<T>
  item: string | { name: string, label?: string, renderLabel?: (t: (...args: any[]) => string, ...args: any[]) => string }
}

export interface ExtensionRenderParams<T = any> {
  editor: Editor
  extension: ExtensionWithRenderer<T>
  renderLabel?: ($t: (...args: any[]) => string, ...args: any[]) => string
  disabled?: boolean
  eventHandlers?: Record<string, (...args: any[]) => any>
}
export interface ExtensionOptions<T = any> {
  renderer: (params: ExtensionRenderParams<T>) => RendererSpec | RendererSpec[]
  bubble?: boolean
  eventHandlers?: Record<string, (...args: any[]) => any>
}
export type ExtensionWithRenderer<T> = Extension<
  ExtensionOptions<T> & T
>
export interface MenuButtonSpec {
  spec: {
    component: Component
    componentProps?: ComputedRef<Record<string, any>>
    componentEvents?: any
  }
  name: string
  label?: string
}
