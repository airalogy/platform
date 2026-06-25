<template>
  <shiki-viewer-wrapper
    :is-loading="isLoading"
    :default-collapsed="!props.errorLines || props.errorLines.length === 0"
  >
    <div v-html="highlightedContent" />
  </shiki-viewer-wrapper>
</template>

<script setup lang="ts">
import { useOrProvideShiki } from "@airalogy/composables"
import ShikiViewerWrapper from "./shiki-viewer-wrapper.vue"

interface Props {
  content: string
  errorLines?: number[]
}

const props = defineProps<Props>()
const highlightedContent = ref("")

const { highlighter, isLoading, initializeShiki } = useOrProvideShiki({ themes: ["github-dark", "aimd-theme"] })

const hast = ref<any>()

async function highlightContent() {
  if (!highlighter.value)
    return

  isLoading.value = true
  try {
    highlightedContent.value = highlighter.value.codeToHtml(props.content, {
      lang: "aimd",
      theme: "github-dark",
      transformers: [{
        line(node, line) {
          node.properties["data-line"] = line
          if (props.errorLines?.includes(line)) {
            node.properties.class = `${node.properties.class} error`
          }
          return node
        },
        tokens(node) {
          console.log(node)

          return node
        },
      }],
    })
    hast.value = highlighter.value.codeToHast(props.content, {
      lang: "aimd",
      theme: "github-dark",
    })
  }
  catch (error) {
    console.error("Failed to highlight content:", error)
    highlightedContent.value = `<pre class="error-content">${props.content}</pre>`
  }

  await nextTick(() => {
    isLoading.value = false
  })
}

watch([() => props.content, highlighter], async () => {
  await highlightContent()
})

watch(hast, (newHast) => {

})

onMounted(() => {
  initializeShiki()
})
</script>

<style lang="sass">
.error-content
  color: #ef4444
  background: rgba(239, 68, 68, 0.1)
  padding: 1rem
  border-radius: 0.375rem
  white-space: pre-wrap

:deep(.error)
  text-decoration: wavy underline rgba(239, 68, 68, 0.5)
</style>
