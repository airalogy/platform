<template>
  <div class="chat-markdown-body">
    <template v-if="vnodes.length > 0">
      <component :is="node" v-for="(node, idx) in vnodes" :key="idx" />
    </template>
    <n-icon v-else-if="isLoading" :component="LoadingIcon" size="18" class="top-1" />
    <div v-else-if="htmlContent" v-html="htmlContent" />
  </div>
</template>

<script setup lang="ts">
import { renderToVue, type VueRendererOptions } from "@airalogy/aimd-renderer"
import { useOrProvideShiki } from "@airalogy/composables"
import { watchOnce } from "@vueuse/core"
import LoadingIcon from "~icons/svg-spinners/3-dots-fade"
import { NIcon } from "naive-ui"
import { h, ref, watch } from "vue"
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

const emit = defineEmits<{
  (e: "update:modelValue", value: string): void
}>()

const vnodes = ref<any[]>([])
const htmlContent = ref("")
const isLoading = ref(false)

const LANGUAGE_CLASS_NAME_PREFIX = "language-"

const { highlighter, isLoading: shikiLoading } = useOrProvideShiki()

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

/**
 * 自定义元素渲染器
 */
const elementRenderers = {
  // 代码块渲染
  pre: async (node: HastElementNode, children: any[]) => {
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

    // 等待 Shiki 加载
    let highlighterInst = highlighter.value
    if (!highlighterInst && shikiLoading.value) {
      highlighterInst = await new Promise((res) => {
        watchOnce(highlighter, val => res(val))
      })
    }

    // 使用 Shiki 高亮
    if (highlighterInst && lang) {
      try {
        const tokens = highlighterInst.codeToTokensWithThemes(codeContent, {
          lang: lang || "text",
          themes: {
            light: "github-light",
            dark: "github-light",
          },
        })

        return h(StepContainerPreToolbar as any, {
          language: lang,
          class: "my-2",
          codeBlockContent: codeContent,
        } as any, {
          default: () => [
            h("pre", { class: ["chat-message--nested", `${LANGUAGE_CLASS_NAME_PREFIX}${lang}`] }, h("code", { class: `${LANGUAGE_CLASS_NAME_PREFIX}${lang}` }, tokens.map(line =>
              h("div", { class: "line" }, line.map(token =>
                h("span", { style: `color: ${token.variants.light.color}` }, token.content),
              )),
            ))),
          ],
        }) as any
      }
      catch (error) {
        console.error("Failed to highlight code:", error)
      }
    }

    // 后备：无高亮
    return h("pre", {}, h("code", { class: `${LANGUAGE_CLASS_NAME_PREFIX}${lang || "text"}` }, codeContent)) as any
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

  // 图片渲染
  img: async (node: HastElementNode) => {
    const attrs = { ...node.properties } as Record<string, any>

    // 解析文件 ID
    if (props.resolveFile && attrs.src) {
      try {
        const res = await props.resolveFile(attrs.src)
        if (res?.url) {
          attrs.src = res.url
        }
      }
      catch (e) {
        console.error("Failed to resolve image:", e)
      }
    }

    return h("img", attrs as any) as any
  },
} as unknown as NonNullable<VueRendererOptions["elementRenderers"]>

/**
 * 渲染源内容
 */
async function renderSource() {
  const source = props.source
  if (!source) {
    vnodes.value = []
    htmlContent.value = ""
    return
  }

  isLoading.value = true

  try {
    if (Array.isArray(source)) {
      // 数组源：合并渲染结果
      const results = await Promise.all(
        source.filter((item): item is string => typeof item === "string")
          .map(item => renderToVue(item, {
            gfm: true,
            math: true,
            elementRenderers,
          })),
      )

      vnodes.value = results.flatMap(r => r.nodes) as any[]
    }
    else if (typeof source === "string") {
      // 字符串源
      const result = await renderToVue(source, {
        gfm: true,
        math: true,
        elementRenderers,
      })

      vnodes.value = result.nodes as any[]
    }
  }
  catch (error) {
    console.error("Markdown render error:", error)
    // 后备：显示原始文本
    htmlContent.value = `<pre>${source}</pre>`
  }
  finally {
    isLoading.value = false
  }
}

// 监听源变化
watch(() => props.source, renderSource, { immediate: true })
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

  // AIMD field styles
  .aimd-var,
  .aimd-var_table,
  .aimd-step,
  .aimd-check,
  .aimd-ref_step,
  .aimd-ref_var
    display: inline-flex
    align-items: center
    gap: 4px
    padding: 2px 8px
    border-radius: 4px
    font-size: 13px
    line-height: 1.4
    vertical-align: middle
    font-weight: 500

  .aimd-var
    background-color: var(--aimd-var-bg, #e3f2fd)
    border: 1px solid var(--aimd-border-color, #90caf9)
    color: var(--aimd-var-text, #1565c0)

  .aimd-var_table
    background-color: #e8f5e9
    border: 1px solid #a5d6a7
    color: #2e7d32

  .aimd-step
    background-color: #fff3e0
    border: 1px solid #ffcc80
    color: #e65100

  .aimd-check
    background-color: #fce4ec
    border: 1px solid #f48fb1
    color: #c2185b

  .aimd-ref_step
    background-color: #fff8e1
    border: 1px solid #ffcc80
    color: #ff8f00

  .aimd-ref_var
    background-color: #e8eaf6
    border: 1px solid #c5cae9
    color: #3949ab
</style>
