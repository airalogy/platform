<template>
  <div
    class="editor-container"
    :class="{ 'editor-container--focus': isFocused, 'cursor-text': !props.readonly }"
  >
    <editor-content v-if="props.readonly && props.hideMenu" class="editor-content" :editor="editor" :class="props.contentClass" />
    <n-card
      v-else-if="editor"
      ref="wrapperRef"
      :bordered="false"
      class="max-w-full min-h-26"
      :class="[!isEditorExpanded ? 'resize min-w-full' : '', props.wrapperClass]"
      header-class="border-b !p-1 !pt-1.5"
      :content-class="
        [
          props.editorClass || '',
          showRawContent ? '!overflow-hidden !p-0' : 'overflow-y-auto !p-2 !pb-4',
          currPreset === 'simple' ? 'min-h-8' : 'min-h-14',
        ].join(' ')"
      :style="[props.editorStyle, editorContentStyle]"
      @click="handleFocus"
    >
      <template #header>
        <menu-bar class="size-full" :editor="editor" :preset="currPreset" :extra-actions="props.extraActions" :disabled="props.readonly" @click.stop />
      </template>

      <n-input
        v-show="showRawContent" ref="inputRef" v-model:value="rawContent" type="textarea"
        :autosize="props.autosize"
        :theme-overrides="{
          border: '0',
          color: 'transparent',
          fontSizeMedium: '16px',
          textColorDisabled: '#333',
          heightMedium: isEditorExpanded ? undefined : currPreset === 'simple' ? '1rem' : '4rem',
        }"
        class="h-full w-full pb-4"
        :class="[currPreset === 'simple' ? 'min-h-8' : 'min-h-14']"
        :style="{ '--n-padding-vertical': '8px', 'font-family': 'monospace' }"
        :disabled="props.readonly"
        @focus="handleFocus"
      />
      <editor-content v-hide="showRawContent" class="editor-content" :editor="editor" :class="props.contentClass" />
      <menu-bubble :editor="editor" :class="bubbleMenuClass" />

      <div class="absolute bottom-1 right-1 flex items-center">
        <tooltip-button
          :tooltip="isEditorExpanded ? 'Collapse Editor' : 'Expand Editor'"
          size="small"
          :icon-props="{ size: 14 }"
          quaternary
          circle
          :icon="isEditorExpanded ? CollapseAll : ExpandAll"
          @click="toggleEditorHeight"
        />
        <slot name="action" />
      </div>
      <!--
      <div
        class="flex-1"
        :class="[
          props.editorClass,
          showRawContent ? '!overflow-hidden' : 'overflow-y-auto px-2 pb-2 pt-2',
          currPreset === 'simple' ? 'min-h-8' : 'min-h-14',
        ]"
        :style="[props.editorStyle, editorContentStyle]"
        @click="() => !showRawContent && editor?.commands?.focus?.()"
      /> -->
    </n-card>
    <template v-if="!props.hideBorder">
      <div class="editor__state" />
      <div class="editor__state-border" />
    </template>
  </div>
</template>

<script setup lang="ts">
import type { EditorEvents, EditorOptions, Mark, Node } from "@tiptap/vue-3"
import type { CSSProperties, HTMLAttributes } from "vue"
import type { DEFAULT_FONT_SIZES } from "./utils/font-size"

import { useBoolean, useClosableMessage } from "@airalogy/composables"

import {
  AiralogyFile,
  Blockquote,
  // text extensions
  Bold,
  BulletList,
  CharacterCount,
  Code,
  CodeBlock,
  CompactMenu,
  Document,
  Dropcursor,
  FileHandler,

  // FontFamily,
  // FontSize,
  FormatClear,
  HardBreak,
  // paragraph extensions
  Heading,
  History,
  HorizontalRule,
  Image,
  Indent,
  // upload extensions
  // ImageUpload,
  Italic,
  LineHeight,
  // rich and tools extensions
  Link,

  ListItem,
  OrderedList,
  Paragraph,
  Placeholder,

  // Additional
  Raw,
  Strike,
  Table,
  TaskList,
  Text,
  // TextAlign,
  TextStyle,
  TiptapMarkdown,
  Underline,
} from "./extensions"
// import { CustomMarkdown } from "@airalogy/components/components/editor/extensions/markdown/custom-markdown"

import type { EditorProps } from "@tiptap/pm/view"

import type { MenuSectionConfig } from "./types/editor"
import { fileToBlob } from "@airalogy/shared/utils"
import { Editor, EditorContent, Extension } from "@tiptap/vue-3"
import { tryOnBeforeUnmount, unrefElement } from "@vueuse/core"
import { type InputInst, useThemeVars } from "naive-ui"
import TooltipButton from "../tooltip-button.vue"

import MenuBar from "./menu-bar.vue"
import MenuBubble from "./modules/bubble-menu/index.vue"
// Import icons dynamically
// import { CollapseAll, ExpandAll } from "@vicons/carbon"
import CollapseAll from "~icons/ion/chevron-collapse"
import ExpandAll from "~icons/ion/chevron-expand"
import { computed, markRaw, nextTick, onMounted, ref, shallowRef, watch } from "vue"

interface IProps {
  html?: string
  text?: string
  json?: Record<string, any> | null
  /** If true, the editor will emit the text content as the raw content */
  rawResult?: boolean
  readonly?: boolean
  extensions?: Extension[]
  placeholder?: string
  enableCharCount?: boolean
  charCountMax?: number
  preset?: "all" | "compact" | "simple"
  contentClass?: string
  editorClass?: string
  editorStyle?: CSSProperties
  bubbleMenuClass?: string
  autosize?: boolean
  resizable?: boolean
  defaultFontSize?: (typeof DEFAULT_FONT_SIZES)[number]
  extraActions?: MenuSectionConfig[]
  editorProps?: EditorProps
  hideMenu?: boolean
  hideBorder?: boolean
  protocolId?: string | null
  wrapperClass?: HTMLAttributes["class"]
  postAddAttachments?: (file: File, protocolId?: string | null) => Promise<any>
  resolveFile?: (id: string) => Promise<any>
}

const props = withDefaults(defineProps<IProps>(), {
  rawResult: false,
  readonly: false,
  placeholder: "",
  enableCharCount: false,
  charCountMax: 1e6,
  extensions: () => [],
  autosize: true,
  resizable: true,
  bubbleMenuClass: undefined,
  contentClass: undefined,
  editorClass: undefined,
  preset: "compact",
  html: undefined,
  text: undefined,
  json: undefined,
  hideMenu: false,
  hideBorder: false,
  protocolId: undefined,
})

const emit = defineEmits<IEmits>()

type EventHandlerNames<K = `on${Capitalize<keyof EditorEvents>}`> = K extends keyof EditorOptions ? K : never
type GetEventOptions<K extends keyof EditorEvents, P = `on${Capitalize<K>}`> = P extends keyof EditorOptions ? EditorOptions[P] : never
type EditorEventArgs<K extends keyof EditorEvents, P = GetEventOptions<K>> = P extends (...args: infer R) => void ? R : never

interface IEmits {
  (e: "update:html", html: string): void
  (e: "update:text", text: string): void
  (e: "create", ...args: EditorEventArgs<"create">): void
  (e: "transaction", ...args: EditorEventArgs<"transaction">): void
  (e: "focus", ...args: EditorEventArgs<"focus">): void
  (e: "blur", ...args: EditorEventArgs<"blur">): void
  (e: "update", ...args: EditorEventArgs<"update">): void
  (e: "selectionUpdate", ...args: EditorEventArgs<"selectionUpdate">): void
  (e: "contentError", ...args: EditorEventArgs<"contentError">): void
  (e: "destroy", ...args: EditorEventArgs<"destroy">): void
  (e: "beforeCreate", ...args: EditorEventArgs<"beforeCreate">): void
  (e: "beforeTransaction", ...args: EditorEventArgs<"beforeTransaction">): void
  (e: "paste", ...args: EditorEventArgs<"paste">): void
  (e: "drop", ...args: EditorEventArgs<"drop">): void
}

const wrapperRef = ref<HTMLElement | null>(null)
const inputRef = ref<InputInst | null>(null)

const themeVars = useThemeVars()
const message = useClosableMessage()
const actionMapping = {
  copyImage: "Copy Image",
  copyLink: "Copy Link",
  download: "Download",
  copyId: "Copy ID",
}

const basicExtensions = [
  Document,
  Text,
  HardBreak,
  Paragraph, // Use default Paragraph without custom Enter handling
  Table,
  AiralogyFile.configure({
    allowedMimeTypes: ["application/pdf", "text/csv"],
    maxFileSize: 5 * 1024 * 1024,
    allowBase64: true,
    protocolId: props.protocolId,
    postAddAttachments: props.postAddAttachments,
    resolveFile: props.resolveFile,
    onFileRemoved({ id, src }) {
      console.log("File removed", { id, src })
    },
    onValidationError(errors) {
      errors.forEach((error) => {
        message.error(`File validation error: ${error.reason}`)
      })
    },
    onActionSuccess({ action }) {
      message.success(actionMapping[action])
    },
    onActionError(error, { action }) {
      message.error(`Failed to ${actionMapping[action]} - ${error.message}`)
    },
  }),
  Image.configure({
    allowedMimeTypes: ["image/*"],
    maxFileSize: 5 * 1024 * 1024,
    allowBase64: true,
    protocolId: props.protocolId,
    postAddAttachments: props.postAddAttachments,
    resolveFile: props.resolveFile,
    onImageRemoved({ id, src }) {
      console.log("Image removed", { id, src })
    },
    onValidationError(errors) {
      errors.forEach((error) => {
        message.error(`Image validation error: ${error.reason}`)
      })
    },
    onActionSuccess({ action }) {
      message.success(actionMapping[action])
    },
    onActionError(error, { action }) {
      message.error(`Failed to ${actionMapping[action]} - ${error.message}`)
    },
  }),
  TiptapMarkdown.configure({
    html: true, // Allow HTML input/output
    breaks: true, // Single newlines are converted to <br> - this makes newlines work consistently
    transformPastedText: true, // Allow to paste markdown text in the editor
    transformCopiedText: true, // Copied text is transformed to markdown
  }),
  Placeholder.configure({
    emptyEditorClass: "tiptap-editor__placeholder",
    placeholder: () => props.placeholder,
  }),
  FileHandler.configure({
    allowBase64: true,
    allowedMimeTypes: ["image/*", "application/pdf", "text/csv"],
    maxFileSize: 5 * 1024 * 1024,
    onDrop: async (editor, files, pos) => {
      // const type = files[0].type
      files.forEach((file) => {
        const type = file.type
        editor.commands.insertContentAt(pos, {
          type: type.startsWith("image/") ? "airalogyImage" : "airalogyFile",
          attrs: { src: fileToBlob(file) },
        })
      })
    },
    onPaste: (editor, files) => {
      files.forEach(async (file) => {
        editor.commands.insertContent({
          type: file.type.startsWith("image/") ? "airalogyImage" : "airalogyFile",
          attrs: { src: fileToBlob(file) },
        })
      })
    },
    onValidationError: (errors) => {
      errors.forEach((error) => {
        message.error(`Image validation error: ${error.reason}`)
      })
    },
  }),
  Dropcursor.configure({ width: 2, class: "ProseMirror-dropcursor border" }),
]

const textExtensions: (Extension | Mark)[] = [
  Bold.configure({ bubble: true }),
  Underline.configure({ bubble: true }),
  Italic.configure({ bubble: true }),
  Strike.configure({ bubble: true }),
  Code,
  // FontFamily,
  // FontSize,
  // Color.configure({ bubble: true }),
  // Highlight.configure({ bubble: true }),
  FormatClear,
  TextStyle,
]

const paragraphExtensions: (Extension | Mark | Node)[] = [
  Heading.configure({ level: 5 }),
  BulletList,
  OrderedList,
  TaskList,
  // TextAlign,
  LineHeight,
  Indent,
  Blockquote,
  CodeBlock,
  ListItem,
]

const richAndToolsExtensions: (Extension | Mark | Node)[] = [
  Link,
  HorizontalRule,
  History,
  Raw,
]

const extensions = computed(() => {
  const propsExtensions = props.extensions.filter(Boolean)
  const exts
    = [...basicExtensions, ...textExtensions, ...paragraphExtensions, ...richAndToolsExtensions, ...propsExtensions, CompactMenu]

  if (exts.some(it => it.type === "listItem" || it.name === "listItem")) {
    exts.push(
      Extension.create({
        addKeyboardShortcuts() {
          return {
            Tab: () => {
              if (this.editor.can().sinkListItem("listItem")) {
                return this.editor.chain().sinkListItem("listItem").run()
              }

              // Only insert spaces if sinkListItem wasn't possible
              return this.editor
                .chain()
                .command(({ tr }) => {
                  tr.insertText("    ")
                  return true
                })
                .run()
            },
          }
        },
      }),
    )
  }
  else {
    exts.push(
      Extension.create({
        addKeyboardShortcuts() {
          return {
            Tab: () => {
              if (this.editor.can().sinkListItem("listItem")) {
                return this.editor.chain().sinkListItem("listItem").run()
              }

              // Only insert spaces if sinkListItem wasn't possible
              return this.editor
                .chain()
                .command(({ tr }) => {
                  tr.insertText("    ")
                  return true
                })
                .run()
            },
          }
        },
      }),
    )
  }

  if (props.enableCharCount) {
    exts.push(CharacterCount.configure({
      limit: props.charCountMax,
    }))
  }

  return exts
})

const editor = shallowRef<Editor | undefined>(undefined)

const rawContent = ref(props.text)
const showRawContent = computed(() => editor.value?.storage.rawContent?.isRaw || false)
// const isCompactMode = computed(() => editor.value?.storage.compactMenu?.isCompact || false)

// const currPreset = computed(() => {
//   if (isCompactMode.value) {
//     return props.preset === "simple" ? "simple" : "compact"
//   }

//   return props.preset === "simple" ? "compact" : "all"
// })
const currPreset = ref(props.preset)

watch(() => editor.value?.storage.compactMenu?.isCompact, (isCompact) => {
  if (isCompact) {
    currPreset.value = props.preset === "simple" ? "simple" : "compact"
  }
  else {
    currPreset.value = props.preset === "simple" ? "compact" : "all"
  }
}, { immediate: true, flush: "post" })

watch(
  () => props.text,
  (text, prevText) => {
    if (rawContent.value === text) {
      return
    }

    rawContent.value = text

    const editorInst = editor.value
    if (editorInst) {
      editorInst.commands.setContent(text || "", false)
    }
  },
  { flush: "post" },
)

watch(rawContent, (text) => {
  if (!showRawContent.value) {
    return
  }

  const editorInst = editor.value
  if (editorInst) {
    editorInst.commands.setContent(text || "", false)
  }
  emit("update:text", text || "")
})

watch(
  () => props.readonly,
  () => {
    editor.value?.setOptions({ editable: !props.readonly })
  },
)

// async function resolveAiralogyImages(editorDom: HTMLElement) {
//   const images = editorDom.querySelectorAll("img[data-airalogy-id]")
//   await Promise.all(
//     Array.from(images).map(async (img) => {
//       const airalogyId = img.getAttribute("data-airalogy-id")
//       if (airalogyId) {
//         const url = await resolveImageUrl(airalogyId)
//         img.setAttribute("src", url)
//       }
//     }),
//   )
// }

watch(showRawContent, async (show) => {
  const editorInst = editor.value
  if (editorInst) {
    if (show) {
      const mdContent = editorInst.storage.markdown.getMarkdown()
      rawContent.value = mdContent
    }
    else {
      // When switching back to WYSIWYG mode, re-parse markdown content
      // This ensures HTML tags like <br> are properly converted to nodes
      let content = rawContent.value || ""

      // Ensure tables have blank line after them to prevent following content
      // from being parsed as part of the table
      // Match: table row followed by newline, then non-empty, non-table content
      content = content.replace(
        /(\|[^\n]*\|)\n(?=\S)(?!\|)/g,
        "$1\n\n",
      )

      editorInst.commands.setContent(content, false)
    }
  }
})
const { bool: isFocused, setTrue: setFocused, setFalse: setUnfocused } = useBoolean(false)

const defaultEventHandlers = Array.from(new Set<keyof EditorEvents>(["destroy", "beforeCreate", "beforeTransaction", "blur", "contentError", "create", "drop", "focus", "paste", "selectionUpdate", "transaction", "update"])).reduce((acc, key) => {
  const eventName = `on${key.charAt(0).toUpperCase() + key.slice(1)}` as EventHandlerNames
  acc[eventName] = (...args: any[]) => {
    emit(key as any, ...args)
  }
  return acc
}, {} as Partial<EditorOptions>)

watch(editor, (editorInst, prevEditorInst) => {
  if (prevEditorInst) {
    prevEditorInst.removeAllListeners()
  }

  if (!editorInst) {
    return
  }

  // editorInst.on("create", (options) => {
  //   const { rawContent, compactMenu } = options.editor?.extensionStorage || {}
  //   showRawContent.value = rawContent?.isRaw || false
  //   isCompactMode.value = compactMenu?.isCompact || false
  // })

  // editorInst.on("transaction", (options) => {
  //   const { rawContent, compactMenu } = options.editor.extensionStorage || {}
  //   showRawContent.value = rawContent?.isRaw || false
  //   isCompactMode.value = compactMenu?.isCompact || false
  // })

  editorInst.on("focus", (options) => {
    setFocused()
  })

  editorInst.on("blur", (options) => {
    setUnfocused()
  })

  editorInst.on("update", ({ editor: editorInst }) => {
    if (props.rawResult) {
      const mdContent = editorInst.storage.markdown.getMarkdown()
      if (rawContent.value !== mdContent) {
        emit("update:text", mdContent)
        rawContent.value = mdContent
      }
    }
    emit("update:html", editorInst.getHTML())
  })
}, { immediate: true })

defineExpose({
  editorRef: editor,
  wrapperRef,
})
// Add observer to handle dynamically added images
onMounted(() => {
  try {
    let content: string | Record<string, any> = ""
    if (props.html) {
      content = props.html
    }
    else if (props.json) {
      content = props.json
    }
    else if (props.text) {
      content = props.text
    }

    const newEditorInst = new Editor({
      content,
      extensions: extensions.value,
      editable: !props.readonly,
      editorProps: props.editorProps,
      ...defaultEventHandlers,
    })

    if (props.defaultFontSize) {
      newEditorInst.commands.setFontSize(props.defaultFontSize)
    }

    editor.value = markRaw(newEditorInst)
  }
  catch (e) {
    message.error("Failed to initialize markdown editor")
  }
})

// Clean up observer on component unmount
tryOnBeforeUnmount(() => {
  if (editor.value) {
    editor.value.destroy()
  }
})

const isEditorExpanded = ref(false)

async function toggleEditorHeight() {
  isEditorExpanded.value = !isEditorExpanded.value
  await nextTick()
  const el = unrefElement(wrapperRef)
  if (el) {
    if (isEditorExpanded.value) {
      el.style.setProperty("width", "auto")
      el.scrollIntoView({ behavior: "smooth", block: "end" })
    }
    else {
      el.scrollIntoView({ behavior: "smooth", block: "start" })
    }
  }
}

function handleFocus() {
  if (!showRawContent.value && editor.value) {
    editor.value.commands.focus()
  }
}
const editorContentStyle = computed(() => {
  const style: CSSProperties = {}

  if (isEditorExpanded.value) {
    style.height = "auto"
    style.overflow = "visible"
  }
  else {
    style.overflow = "auto"
  }

  return style
})
</script>

<style scoped lang="sass">
.editor-container
  @apply min-w-80 flex-1 relative max-w-100%
  border-radius: 8px
  --editor-border-color: var(--border-color)
  --editor-border-hover-color: var(--border-hover-color)
  --editor-border-focus-color: var(--border-focus-color)

  &:hover
    .editor__state-border
      border: 1px solid rgba(var(--editor-border-hover-color) / 80%)
  &--focus
    .editor__state-border
      border: 1px solid rgba(var(--editor-border-focus-color) / 80%)
      box-shadow: 0 0 0 2px rgba(var(--editor-border-focus-color) / 30%)

.editor__state, .editor__state-border
  box-sizing: border-box
  position: absolute
  left: 0
  right: 0
  top: 0
  bottom: 0
  pointer-events: none
  border-radius: inherit
  border: 1px solid rgba(var(--editor-border-color) / 80%)
  transition: box-shadow .3s cubic-bezier(.4, 0, .2, 1), border-color .3s cubic-bezier(.4, 0, .2, 1)

:deep(.ProseMirror-focused)
  outline: none

:deep(code br.ProseMirror-trailingBreak)
  display: unset

:deep(.ProseMirror)
  font-size: 16px

  & > * + *
    margin-top: 0.75em

  p
    margin: 0

  ul,
  ol
    padding-left: 2rem

  h1
    font-size: 2.25em
    font-weight: 700

  h2
    font-size: 1.75em
    font-weight: 600

  h3
    font-size: 1.5em
    font-weight: 500

  h4
    font-size: 1.25em
    font-weight: 400

  h1,
  h2,
  h3,
  h4,
  h5,
  h6
    line-height: 1.1

  code
    background-color: v-bind("themeVars.codeColor")
    padding: 2px 4px
    border-radius: 5px
    font-size: 85%

  pre
    background: v-bind("themeVars.codeColor")
    font-family: monospace
    padding: 0.75rem 1rem
    border-radius: 0.5rem

    code
      color: inherit
      padding: 0
      background: none
      font-size: 0.8rem

  mark
    background-color: #faf594

  img
    max-width: 100%
    height: auto

  hr
    height: .1em

  blockquote
    padding-left: 1rem
    border-left: 2px solid rgba(#0d0d0d, 0.1)

  ul[data-type="taskList"]
    list-style: none
    padding: 0

    li
      display: flex
      align-items: center

      > label
        flex: 0 0 auto
        margin-right: 0.5rem
        user-select: none

      > div
        flex: 1 1 auto

  ol
    list-style: decimal
  ul
    list-style: disc

  li
    margin-bottom: 0px!important

  &.resize-cursor
    @apply cursor-ew-resize

:deep(.tippy-box)
  background: white
  box-shadow: 0 0 8px 0 rgba(0, 0, 0, 0.12), 0 8px 16px 0 rgba(0, 0, 0, 0.08)
  border-radius: 8px
  padding: 8px

:deep(.n-input__textarea-el)
  padding: 0!important
:deep(.n-input__textarea-mirror)
  padding: 0!important
:deep(.n-input__placeholder)
  padding: 0!important
:deep(.n-input-wrapper)
  @apply p-2
:deep(.n-input--resizable .n-input-wrapper)
  resize: both !important

:deep(.tiptap-editor__placeholder::before)
  color: rgba(53, 38, 28, 0.3)
  content: attr(data-placeholder)
  float: left
  height: 0
  pointer-events: none
  white-space: nowrap
</style>
