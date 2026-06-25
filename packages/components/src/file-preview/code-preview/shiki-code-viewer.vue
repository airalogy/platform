<template>
  <shiki-viewer-wrapper v-if="useWrapper" :is-loading="isLoading" :max-height="maxHeight">
    <div v-html="highlightedCode" />
  </shiki-viewer-wrapper>
  <div v-else v-html="highlightedCode" />
</template>

<script setup lang="ts">
import { useOrProvideShiki } from "@airalogy/composables"
import { nextTick, onMounted, ref, watch } from "vue"
import ShikiViewerWrapper from "./shiki-viewer-wrapper.vue"

interface IProps {
  code: string
  language?: string
  theme?: string
  maxHeight?: number
  showLineNumbers?: boolean
  highlightLines?: number[]
  useWrapper?: boolean
}
const props = withDefaults(defineProps<IProps>(), {
  useWrapper: true,
})

const highlightedCode = ref("")

const { highlighter, isLoading, initializeShiki, loadLanguage } = useOrProvideShiki({
  langs: props.language ? [props.language] : undefined,
  themes: props.theme ? [props.theme] : undefined,
})

async function highlightCode() {
  if (!highlighter.value)
    return

  isLoading.value = true
  try {
    highlightedCode.value = highlighter.value.codeToHtml(props.code, {
      lang: props.language || "python",
      theme: props.theme || "github-dark",
      transformers: [{
        line(node, line) {
          // Add line numbers and highlighting
          node.properties.class = `${node.properties.class || ""} line`
          node.properties["data-line"] = line

          if (props.highlightLines?.includes(line)) {
            node.properties.class += " highlight"
          }
          return node
        },
        span(node, line, col) {
          if (node.properties.class && typeof node.properties.class === "string" && node.properties.class.includes("error")) {
            node.properties.class += " bg-red-500/10"
          }
          return node
        },
      }],
    })
  }
  catch (error) {
    console.error("Failed to highlight code:", error)
    highlightedCode.value = `<pre class="error-content">${props.code}</pre>`
  }

  await nextTick(() => {
    isLoading.value = false
  })
}

watch([() => props.code, () => props.language, () => props.theme, highlighter], async () => {
  await loadLanguage(props.language || "python")
  await highlightCode()
})

onMounted(() => {
  initializeShiki()
})
</script>

<style lang="sass" scoped>
.line
  display: block
  padding: 0 1rem

  &.highlight
    background: rgba(255, 255, 255, 0.1)

.error-content
  color: #ef4444
  background: rgba(239, 68, 68, 0.1)
  padding: 1rem
  border-radius: 0.375rem
  white-space: pre-wrap

:deep(.error)
  text-decoration: wavy underline rgba(239, 68, 68, 0.5)
</style>
