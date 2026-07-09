<!-- eslint-disable vue/no-v-html -->
<template>
  <div class="preview__wrapper min-w-[20px] pb-6 text-black" :class="`preview__wrapper--${props.mode}`">
    <div ref="previewContainerRef" class="break-words leading-relaxed">
      <!-- VNode rendering mode (with form) -->
      <n-form
        v-if="props.record && useVNodes"
        class="markdown-body"
        :class="markdownBodyClasses"
        :rules="props.record.rules"
        :model="props.value"
      >
        <component :is="node" v-for="(node, idx) in vnodes" :key="idx" />
      </n-form>

      <!-- VNode rendering mode (without form) -->
      <div v-else-if="useVNodes && vnodes.length > 0" class="markdown-body" :class="markdownBodyClasses">
        <component :is="node" v-for="(node, idx) in vnodes" :key="idx" />
      </div>

      <!-- HTML rendering mode -->
      <div
        v-else-if="!asRawText"
        class="markdown-body"
        :class="markdownBodyClasses"
        v-html="htmlContent"
      />

      <!-- Raw text mode -->
      <div v-else class="whitespace-pre-wrap" v-text="props.text" />
    </div>

    <protocol-bubble-menu v-if="previewContainerRef" :container-ref="previewContainerRef" />
    <slot />
  </div>
</template>

<script lang="ts" setup>
import type { ExtractedAimdFields, RenderContext } from "@airalogy/aimd-core/types"
import { getSubvarNames } from "@airalogy/aimd-core"
import { createMermaidRenderer, renderReadonlyRecordToVue, renderToHtml, renderToVue, type VueRendererOptions } from "@airalogy/aimd-renderer"
import { useBoolean, useClosableMessage } from "@airalogy/composables"
import DOMPurify from "dompurify"
import MermaidBlock from "../markdown-editor/modules/mermaid/mermaid-block.vue"
import ProtocolBubbleMenu from "../protocol-bubble-menu.vue"

import "github-markdown-css/github-markdown-light.css"
import "katex/dist/katex.min.css"
import "@airalogy/aimd-recorder/styles"

type VueRenderResult = Awaited<ReturnType<typeof renderToVue>>
type MarkdownRenderResult = string | VueRenderResult

interface StepRecordNode {
  id: string
  name: string
  scope: "research_step"
  level: number
  sequence: number
  step?: string
  parent: StepRecordNode | null
  prev: StepRecordNode | null
  hasChildren?: boolean
  hasContent: true
  siblings: StepRecordNode[]
  next: StepRecordNode | null
}

export interface IProps {
  error?: boolean
  text?: string
  loading?: boolean
  mode?: "edit" | "preview" | "report"
  asRawText?: boolean
  value?: Record<string, Record<string, unknown>>
  readonly?: boolean
  immediate?: boolean
  record?: { rules?: any } | null
  readonlyRecordData?: unknown
  /**
   * Custom AIMD component renderers
   * Used to render Vue components instead of simple HTML elements
   */
  aimdRenderers?: VueRendererOptions["aimdRenderers"]
  /**
   * Whether the editor bubble menu is active
   */
  isEditorBubbleActive?: boolean
  /**
   * Function to resolve file paths (e.g., relative paths like "files/image.png") to URLs
   */
  resolveFile?: (src: string) => Promise<{ url: string } | null>
}

export interface IEmits {
  (e: "mounted:field", record: Record<string, Record<string, HTMLElement | null>>): void
  (e: "edit-start:field", path: string): void
  (e: "parse:field", data: any): void
  (e: "add-row:table", group: string, props: string[], source: string, index: number): void
  (e: "remove-row:table", group: string, props: string[], source: string, index: number): void
  (e: "update:field", payload: Record<string, any>): void
  (e: "render:result", result: MarkdownRenderResult): void
}

const props = withDefaults(defineProps<IProps>(), {
  text: undefined,
  value: undefined,
  mode: "preview",
  readonly: false,
  immediate: false,
  resolveFile: undefined,
})

const emit = defineEmits<IEmits>()

const previewContainerRef = ref<HTMLElement>()
const message = useClosableMessage()

const { bool: isFieldMounted, setTrue: setMountField, setFalse: resetMountField } = useBoolean(false)

// Render state
const vnodes = ref<VueRenderResult["nodes"]>([] as VueRenderResult["nodes"])
const htmlContent = ref("")
const extractedFields = ref<ExtractedAimdFields>({
  var: [],
  var_table: [],
  client_assigner: [],
  quiz: [],
  step: [],
  check: [],
  ref_step: [],
  ref_var: [],
})

// Whether to use VNode rendering
// Use VNode when: not in preview mode, has record, or has custom renderers
const hasMermaidBlock = computed(() => /```mermaid(?:\s|$)/i.test(props.text || ""))

// Mermaid renderer for fenced code blocks: ```mermaid ... ```
const mermaidRenderer = createMermaidRenderer(MermaidBlock)

const elementRenderers = computed(() => ({
  pre: mermaidRenderer,
}))

const isReadonlyRecordRender = computed(() =>
  props.mode === "report" && Boolean(props.readonlyRecordData),
)

const markdownBodyClasses = computed(() => ({
  "aimd-renderer": props.mode === "preview" || isReadonlyRecordRender.value,
  "rendered-aimd-document": isReadonlyRecordRender.value,
  "markdown-body-generate": props.loading,
}))

const useVNodes = computed(() =>
  props.mode !== "preview"
  || Boolean(props.record)
  || Boolean(props.aimdRenderers)
  || isReadonlyRecordRender.value
  || hasMermaidBlock.value,
)

/**
 * Render context
 */
const renderContext = computed<RenderContext>(() => ({
  mode: props.mode,
  value: props.value,
  readonly: Boolean(props.readonly),
}))

/**
 * Helper function to check if a path is relative (needs resolution)
 * Includes paths starting with / (relative to protocol root)
 */
function isRelativePath(src: string): boolean {
  return Boolean(src
    && !src.startsWith("http://")
    && !src.startsWith("https://")
    && !src.startsWith("data:")
    && !src.startsWith("blob:"))
}

/**
 * Pre-resolve all relative file paths in markdown text
 */
async function preResolveFilePaths(text: string): Promise<string> {
  if (!props.resolveFile) {
    return text
  }

  // Extract all image and video sources
  const imgMatches = [...text.matchAll(/!\[([^\]]*)\]\(([^)]+)\)/g)]
  const videoMatches = [...text.matchAll(/<source[^>]+src="([^"]+)"/g)]

  // Collect all relative file paths that need resolution
  const filePaths = new Set<string>()
  imgMatches.forEach((match) => {
    const src = match[2]
    if (isRelativePath(src)) {
      filePaths.add(src)
    }
  })
  videoMatches.forEach((match) => {
    const src = match[1]
    if (isRelativePath(src)) {
      filePaths.add(src)
    }
  })

  // Resolve all file paths
  const resolutions = new Map<string, string>()
  await Promise.all(
    Array.from(filePaths).map(async (filePath) => {
      try {
        const result = await props.resolveFile!(filePath)
        if (result?.url) {
          resolutions.set(filePath, result.url)
        }
      }
      catch (e) {
        console.error("Failed to resolve file:", filePath, e)
      }
    }),
  )

  // Replace all file paths in the text with resolved URLs
  let textToRender = text
  resolutions.forEach((url, filePath) => {
    // Replace in markdown image syntax
    textToRender = textToRender.replace(
      new RegExp(`!\\[([^\\]]*)\\]\\(${filePath.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\)`, "g"),
      `![$1](${url})`,
    )
    // Replace in HTML source tags
    textToRender = textToRender.replace(
      new RegExp(`src="${filePath.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}"`, "g"),
      `src="${url}"`,
    )
  })

  return textToRender
}

/**
 * Transform extractedFields to AimdTemplateEnv format using unified utilities
 * This is the canonical way to convert remark-aimd output to field parsing input
 */
const env = computed(() => {
  const fields = extractedFields.value

  const byId: Record<string, StepRecordNode> = {}
  const byLevel: Record<number, StepRecordNode[]> = {}

  if (fields.step_hierarchy) {
    for (const step of fields.step_hierarchy) {
      const level = step.level ?? 0
      const sequence = step.sequence ?? 0
      const node: StepRecordNode = {
        id: step.id,
        name: step.id,
        scope: "research_step",
        level,
        sequence,
        step: step.step,
        parent: null,
        prev: null,
        hasChildren: step.has_children,
        hasContent: true,
        siblings: [],
        next: null,
      }

      byId[step.id] = node

      if (!byLevel[level]) {
        byLevel[level] = []
      }
      byLevel[level].push(node)
    }

    for (const step of fields.step_hierarchy) {
      const node = byId[step.id]
      if (!node) {
        continue
      }
      if (step.parent_id) {
        node.parent = byId[step.parent_id] ?? null
      }
      if (step.prev_id) {
        node.prev = byId[step.prev_id] ?? null
        if (node.prev) {
          node.prev.next = node
        }
      }
    }
  }

  return {
    fields: {
      rv: fields.var.reduce((acc, name) => {
        acc[name] = { label: name, type: "text", required: false }
        return acc
      }, {} as Record<string, any>),
      rs: fields.step.reduce((acc, name) => {
        acc[name] = { label: name, type: "step" }
        return acc
      }, {} as Record<string, any>),
      rc: fields.check.reduce((acc, name) => {
        acc[name] = { label: name, type: "checkbox" }
        return acc
      }, {} as Record<string, any>),
      rt: fields.var_table.reduce((acc, table) => {
        acc[table.id] = {
          label: table.id,
          type: "table",
          columns: getSubvarNames(table.subvars),
        }
        return acc
      }, {} as Record<string, any>),
    },
    typed: {},
    record: {
      byId,
      byLevel,
      byScope: {
        rv: {},
        rs: byId as Record<string, unknown>,
        rc: {},
        rt: {},
      },
    },
    tables: fields.var_table.map((table): [string, typeof table] => [table.id, table]),
    refs: {
      ref_step: fields.ref_step.map((id, idx) => ({ id, line: 0, sequence: idx })),
      ref_var: fields.ref_var.map((id, idx) => ({ id, line: 0, sequence: idx })),
    },
  }
})

/**
 * Reload rendering
 */
async function reload(reset = true) {
  if (reset) {
    resetMountField()
  }

  if (!props.text) {
    vnodes.value = []
    htmlContent.value = ""
    return
  }

  if (isReadonlyRecordRender.value) {
    try {
      const textToRender = await preResolveFilePaths(props.text)
      const result = await renderReadonlyRecordToVue(textToRender, props.readonlyRecordData, {
        gfm: true,
        math: true,
        elementRenderers: elementRenderers.value,
      })

      vnodes.value = result.nodes
      extractedFields.value = result.fields
      htmlContent.value = ""

      emit("render:result", result)
      processExtractedFields()
    }
    catch (e) {
      message.error((e as Error).message)
      console.error("Readonly record render error:", e)
    }
    return
  }

  if (props.mode === "report") {
    htmlContent.value = props.text
    emit("render:result", props.text)
    return
  }

  try {
    if (useVNodes.value) {
      // Pre-resolve all file URLs before rendering
      const textToRender = await preResolveFilePaths(props.text)

      // VNode rendering with pre-resolved URLs
      const result = await renderToVue(textToRender, {
        mode: props.mode,
        gfm: true,
        math: true,
        context: renderContext.value,
        aimdRenderers: props.aimdRenderers,
        elementRenderers: elementRenderers.value,
      })

      vnodes.value = result.nodes
      extractedFields.value = result.fields
      htmlContent.value = ""

      emit("render:result", result)
    }
    else {
      // HTML rendering - pre-resolve file URLs before rendering
      const textToRender = await preResolveFilePaths(props.text)

      const result = await renderToHtml(textToRender, {
        mode: props.mode,
        gfm: true,
        math: true,
      })

      htmlContent.value = DOMPurify.sanitize(result.html, {
        ADD_TAGS: ["iframe", "video", "source"],
        ADD_ATTR: ["allow", "allowfullscreen", "frameborder", "controls", "type"],
        // Allow all data-* attributes for AIMD elements
        ALLOW_DATA_ATTR: true,
      })
      extractedFields.value = result.fields
      vnodes.value = []

      emit("render:result", htmlContent.value)
    }

    // Extract fields and notify
    processExtractedFields()
  }
  catch (e) {
    message.error((e as Error).message)
    console.error("Markdown render error:", e)
  }
}

/**
 * Process extracted fields
 */
function processExtractedFields() {
  const fields = extractedFields.value
  const payload: Record<string, any> = {}

  // Process variable fields
  if (fields.var.length > 0) {
    payload.rv = fields.var.reduce((acc, name) => {
      acc[name] = { label: name, type: "text", required: false }
      return acc
    }, {} as Record<string, any>)
  }

  // Process step fields
  if (fields.step.length > 0) {
    payload.rs = fields.step.reduce((acc, name) => {
      acc[name] = { label: name, type: "step" }
      return acc
    }, {} as Record<string, any>)
  }

  // Process checkpoint fields
  if (fields.check.length > 0) {
    payload.rc = fields.check.reduce((acc, name) => {
      acc[name] = { label: name, type: "checkbox" }
      return acc
    }, {} as Record<string, any>)
  }

  // Process table fields
  if (fields.var_table.length > 0) {
    payload.rt = fields.var_table.reduce((acc, table) => {
      const columns = getSubvarNames(table.subvars)
      acc[table.id] = { label: table.id, type: "table", columns }
      return acc
    }, {} as Record<string, any>)
  }

  if (Object.keys(payload).length > 0) {
    emit("update:field", payload)
  }
}

// Watch text changes
watch(
  () => props.text,
  async (val) => {
    if (val && (props.immediate || !isFieldMounted.value)) {
      await reload()
      setMountField()
    }
  },
  { immediate: true },
)

// Watch value changes in edit mode to sync left panel changes to AIMD preview
// This re-renders VNodes when field values change
watch(
  () => props.value,
  () => {
    if (props.mode === "edit" && isFieldMounted.value && props.text) {
      reload(false)
    }
  },
  { deep: true },
)

watch(
  () => props.readonlyRecordData,
  () => {
    if (isReadonlyRecordRender.value && isFieldMounted.value && props.text) {
      reload(false)
    }
  },
  { deep: true },
)

// Watch field mounting
watch(isFieldMounted, (isMounted) => {
  if (!isMounted)
    return

  void nextTick(() => {
    emit("mounted:field", {})
  })
})

defineExpose({
  extractedFields,
  env,
  reload,
  previewContainerRef,
})
</script>

<style lang="sass">
.preview__wrapper
  position: relative

  &--edit, &--report
    .markdown-body
      table
        overflow: visible

      .aimd-field-wrapper--inline
        .n-form-item
          align-self: flex-end

        .n-form-item--no-label
          margin-bottom: -2px

      [data-has-variable="true"]:has(+ [data-has-variable="true"]),
      [data-has-variable="true"] + [data-has-variable="true"],
      :not([data-has-variable="true"]):has(+ [data-has-variable="true"])
        margin-bottom: 0 !important
        margin-top: 2px !important

      [data-has-variable="true"]
        line-height: max(1.25em + 12px, 1.5em)

        br
          content: " "
          display: block
          margin-top: 2px

      [data-has-checkbox="true"]
        margin-bottom: 0 !important
        margin-top: 16px !important

.preview__wrapper
  .markdown-body
    img
      max-width: 75%

    video
      max-width: 75%
      height: auto

    ul
      list-style-type: disc !important
      padding-left: 2em

      li
        list-style-type: disc !important

    ol
      list-style-type: decimal !important
      padding-left: 2em

      li
        list-style-type: decimal !important

  li
    margin-bottom: 12px !important

// AIMD field styles are imported from @airalogy/aimd-recorder/styles

.rendered-aimd-document
  .aimd-record-field
    margin: 0 1px
    vertical-align: middle

  .aimd-record-field--scalar
    display: inline
    padding: 0 2px
    border-bottom: 1px solid rgba(31, 143, 99, 0.28)
    background: transparent
    color: #162f35
    font-weight: 600
    overflow-wrap: anywhere

  .aimd-record-field--empty
    display: inline-flex
    align-items: center
    gap: 6px
    padding: 1px 7px
    border: 1px dashed #c5d2d6
    border-radius: 4px
    background: #fbfdfd
    color: #6d7c82
    font-size: 13px

  .aimd-record-field__missing-label
    color: #8a6b2b
    font-size: 11px
    font-weight: 700
    text-transform: uppercase

  .aimd-record-field__missing-name,
  .aimd-record-field__filename
    overflow-wrap: anywhere

  .aimd-record-field--boolean,
  .aimd-record-check
    display: inline-flex
    align-items: center
    gap: 8px
    color: #253f38

  .aimd-checkbox
    width: 16px
    height: 16px
    accent-color: #1f8f63

  .aimd-record-field--asset
    max-width: 100%
    margin: 10px 0 16px

  a.aimd-record-field--asset,
  span.aimd-record-field--asset
    min-height: 42px
    display: inline-flex
    align-items: center
    gap: 10px
    padding: 8px 10px
    border: 1px solid #d5e1e4
    border-radius: 6px
    background: #fff
    color: #21373d
    text-decoration: none

  a.aimd-record-field--asset:hover
    border-color: #216dff
    color: #164eb8

  .aimd-record-field__badge
    flex: 0 0 auto
    min-width: 34px
    padding: 2px 6px
    border-radius: 4px
    background: #e5f0f2
    color: #275059
    font-size: 11px
    font-weight: 700
    text-align: center

  .aimd-record-field--image,
  .aimd-record-field--video
    display: block

  .aimd-record-field__image,
  .aimd-record-field__video
    max-width: 100%
    max-height: 520px
    border: 1px solid #e0e8ea
    border-radius: 8px
    background: #fff
    object-fit: contain

  .aimd-record-field__audio
    width: min(100%, 520px)

  .aimd-record-field__caption
    margin-top: 6px
    color: #65777d
    font-size: 13px
    line-height: 1.4

  .aimd-record-field--code,
  .aimd-record-field--dna
    display: block
    overflow: auto
    padding: 12px
    border: 1px solid #d8e5e8
    border-radius: 8px
    background: #f8fbfc

  .aimd-record-field--markdown
    display: block
    margin: 8px 0 14px
    padding: 10px 12px
    border-left: 3px solid #7bb7bd
    background: #f7fbfb
    overflow-wrap: anywhere

    > :first-child
      margin-top: 0

    > :last-child
      margin-bottom: 0

    img
      max-width: 100%
      height: auto

  .aimd-record-field__markdown-fallback,
  .aimd-record-field__sequence
    margin: 0
    padding: 0
    border: 0
    background: transparent
    white-space: pre-wrap

  .aimd-record-table
    margin: 12px 0 16px
    overflow: auto

    table
      min-width: 420px

    th
      background: #f7fafb
      color: #53686f

  .aimd-record-table--empty
    display: inline-flex
    align-items: center
    gap: 6px
    padding: 6px 8px
    border: 1px dashed #c5d2d6
    border-radius: 6px
    background: #fbfdfd
    color: #6d7c82

  .aimd-record-quiz
    margin: 12px 0 16px
    padding: 12px
    border: 1px solid #d8e0ea
    border-radius: 8px
    background: #fbfcff

  .aimd-record-quiz__stem
    margin-bottom: 6px
    font-weight: 700

  .aimd-record-quiz__answer--empty
    color: #748489
    font-style: italic
</style>

<style scoped lang="sass">
:deep(.n-input__placeholder)
  word-break: break-all !important

:deep(.n-form-item-blank)
  --n-blank-height: fit-content

:deep(.n-input__textarea-el)
  padding: 0 !important

:deep(.n-input-wrapper)
  padding: 6px 10px

:deep(.n-form-item-label__asterisk)
  position: absolute
  left: -10px

:deep(.n-checkbox__label)
  flex: 1
  display: inline-flex
  align-items: center

:deep(.n-base-selection-label)
  min-height: 34px

:deep(.n-upload-file-info .n-image)
  min-height: 51px

:deep(.n-upload-trigger.n-upload-trigger--image-card)
  width: 100%

:deep(.n-upload-file-list.n-upload-file-list--grid)
  grid-template-columns: repeat(auto-fit, minmax(96px, 1fr))
</style>
