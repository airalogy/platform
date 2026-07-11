<template>
  <div class="chat-markdown-body">
    <template v-if="sourceItems.length > 0">
      <aimd-markdown-preview
        v-for="(sourceItem, index) in sourceItems"
        :key="index"
        :content="sourceItem"
        :loading="props.loading"
        :render-options="renderOptions"
        :resolve-url="props.resolveFile"
        body-class="chat-markdown-body__content"
      />
    </template>
    <n-icon v-else-if="props.loading" :component="LoadingIcon" size="18" class="top-1" />
  </div>
</template>

<script setup lang="ts">
import { AimdMarkdownPreview, type AimdMarkdownPreviewRenderOptions } from "@airalogy/aimd-renderer/vue"
import { useOrProvideShiki } from "@airalogy/composables"
import LoadingIcon from "~icons/svg-spinners/3-dots-fade"
import { NIcon } from "naive-ui"
import { computed, defineComponent, h } from "vue"
import StepContainerPreToolbar from "./StepContainerPreToolbar/index.vue"

interface HastTextNode {
  type: "text"
  value: string
}

interface HastElementNode {
  type: "element"
  tagName: string
  properties?: Record<string, unknown>
  children: HastNode[]
}

type HastNode = HastElementNode | HastTextNode

interface Props {
  source?: string | string[]
  modelValue?: string
  isRenderingInStepContainer?: boolean
  scrollLocked?: boolean
  itemIndex?: number
  useParentBackgroundColor?: boolean
  loading?: boolean
  resolveFile?: (id: string) => Promise<{ url: string } | null>
}

const props = withDefaults(defineProps<Props>(), {
  source: "",
  modelValue: "",
  isRenderingInStepContainer: false,
  scrollLocked: false,
  itemIndex: undefined,
  loading: false,
  useParentBackgroundColor: false,
  resolveFile: undefined,
})

defineEmits<{
  (e: "update:modelValue", value: string): void
}>()

const sourceItems = computed(() => {
  const source = props.source
  if (Array.isArray(source)) {
    return source.filter((item): item is string => typeof item === "string" && Boolean(item))
  }
  return source ? [source] : []
})

const LANGUAGE_CLASS_NAME_PREFIX = "language-"

const { highlighter } = useOrProvideShiki()

/**
 * 从 className 获取语言
 */
function getLanguageFromClassName(className: any): string | null {
  if (!className || typeof className !== "string") {
    return null
  }

  const language = className
    .split(" ")
    .find(word => word.startsWith(LANGUAGE_CLASS_NAME_PREFIX))
    ?.split("-")[1]

  return language ?? null
}

const ChatCodeBlock = defineComponent({
  name: "ChatCodeBlock",
  props: {
    code: { type: String, required: true },
    language: { type: String, default: "text" },
  },
  setup(codeBlockProps) {
    return () => {
      let codeContent: ReturnType<typeof h>
      const highlighterInstance = highlighter.value

      if (highlighterInstance && codeBlockProps.language !== "text") {
        try {
          const tokens = highlighterInstance.codeToTokensWithThemes(codeBlockProps.code, {
            lang: codeBlockProps.language,
            themes: {
              light: "github-light",
              dark: "github-light",
            },
          })
          codeContent = h("code", { class: `${LANGUAGE_CLASS_NAME_PREFIX}${codeBlockProps.language}` }, tokens.map(line =>
            h("div", { class: "line" }, line.map(token =>
              h("span", { style: `color: ${token.variants.light.color}` }, token.content),
            )),
          ))
        }
        catch (error) {
          console.error("Failed to highlight code:", error)
          codeContent = h("code", { class: `${LANGUAGE_CLASS_NAME_PREFIX}${codeBlockProps.language}` }, codeBlockProps.code)
        }
      }
      else {
        codeContent = h("code", { class: `${LANGUAGE_CLASS_NAME_PREFIX}${codeBlockProps.language}` }, codeBlockProps.code)
      }

      return h(StepContainerPreToolbar as any, {
        language: codeBlockProps.language,
        class: "my-2",
        codeBlockContent: codeBlockProps.code,
      } as any, {
        default: () => [
          h("pre", {
            class: ["chat-message--nested", `${LANGUAGE_CLASS_NAME_PREFIX}${codeBlockProps.language}`],
          }, codeContent),
        ],
      })
    }
  },
})

/**
 * 自定义元素渲染器
 */
const elementRenderers = {
  // 代码块渲染
  pre: (node: HastElementNode, children: any[]) => {
    const codeNode = node.children.find(
      (child): child is HastElementNode => child.type === "element" && child.tagName === "code",
    )

    if (!codeNode) {
      return h("pre", {}, children as any) as any
    }

    const className = codeNode.properties?.className
    const lang = Array.isArray(className)
      ? getLanguageFromClassName(className.join(" "))
      : getLanguageFromClassName(className as string)

    // 获取代码内容
    const codeContent = codeNode.children
      .map((child: HastNode) => (child.type === "text" ? child.value : ""))
      .join("")

    return h(ChatCodeBlock, {
      code: codeContent,
      language: lang || "text",
    }) as any
  },

  // 链接渲染
  a: (node: HastElementNode, children: any[]) => {
    const href = node.properties?.href as string
    return h("a", {
      href,
      class: "hover:underline",
      target: "_blank",
      rel: "noopener",
    }, children as any) as any
  },

} as unknown as NonNullable<AimdMarkdownPreviewRenderOptions["elementRenderers"]>

const renderOptions: AimdMarkdownPreviewRenderOptions = {
  elementRenderers,
}
</script>

<style lang="sass">
.chat-markdown-body
  // 基础样式
  font-size: 14px
  line-height: 1.6

  // 代码块样式
  pre
    margin: 8px 0
    padding: 12px
    border-radius: 6px
    background-color: #f6f8fa
    overflow-x: auto

    code
      font-family: 'Fira Code', 'Consolas', monospace
      font-size: 13px

  // 内联代码
  code:not(pre code)
    padding: 2px 6px
    border-radius: 4px
    background-color: rgba(175, 184, 193, 0.2)
    font-size: 85%

  // 链接
  a
    color: #0969da

    &:hover
      text-decoration: underline

  // 列表
  ul, ol
    padding-left: 1.5em
    margin: 8px 0

  // 段落
  p
    margin: 8px 0

  // 图片
  img
    max-width: 100%
    border-radius: 6px

  // 数学公式
  .katexmath-block
    overflow-x: auto
    padding: 10px
    background-color: #f6f8fa
    border-radius: 6px

  // 代码行
  .line
    min-height: 1.5em
</style>
