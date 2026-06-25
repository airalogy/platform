<template>
  <n-spin ref="container" class="mermaid__wrapper group/mermaid" :show="loading" content-class="size-full" :class="errMsg ? 'mermaid__wrapper--error' : ''" v-bind="props.attrs">
    <div class="mermaid__actions skip-print">
      <tooltip-button size="small" tooltip="Download as svg" tertiary @click="exportSvg">
        SVG
      </tooltip-button>
      <tooltip-button size="small" tooltip="Download as png" tertiary @click="exportPng">
        PNG
      </tooltip-button>
    </div>
    <n-image v-if="imageUrl" ref="imgRef" :src="imageUrl" :data-path="props.path" alt="mermaid" class="size-full" :loading="loading" :lazy="true" :img-props="{ class: 'mx-auto' }" />
    <pre class="mermaid__error skip-export">{{ errMsg }}</pre>
  </n-spin>
</template>

<script setup lang="ts">
import type { MermaidConfig } from "mermaid"
import { useLoading } from "@airalogy/composables"
import { downloadAsUrl } from "@airalogy/shared"
import { nanoid } from "nanoid"
import { render as renderDiagram } from "./helpers"

const props = withDefaults(defineProps<IProps>(), {
  config: () => ({}),
})

interface IProps {
  attrs: Record<string, any>
  code?: string
  path?: string
  config?: MermaidConfig
}

const imgRef = ref<{ imageRef: HTMLImageElement }>()
const result = ref("")
const { loading, startLoading, endLoading } = useLoading()
const container = ref()
const errMsg = ref("")

const imageUrl = computed(() => {
  return getImageUrl(result.value)
})

function getImageUrl(code?: string) {
  let svg = code || container.value?.innerHTML
  if (!svg) {
    return ""
  }

  svg = svg.replace(/<\/(area|base|br|col|command|embed|hr|img|input|keygen|link|meta|param|source|track|wbr)>/g, "")
    .replace(/<(area|base|br|col|command|embed|hr|img|input|keygen|link|meta|param|source|track|wbr)([^>]*)>/g, "<$1$2/>")

  // Add white background to SVG
  svg = svg.replace(/<svg([^>]*)>/, (_match: string, attrs: string) => {
    return `<svg${attrs}><rect width="100%" height="100%" fill="white"/>`
  })

  return `data:image/svg+xml;base64,${btoa(svg)}`
}

async function render() {
  try {
    startLoading()
    const { code = "", config } = props

    if (!code) {
      return
    }

    const { svg } = await renderDiagram(config, code, `mermaid-${nanoid()}`)
    if (!svg) {
      return
    }

    // get max width
    const width = svg.match(/style="max-width: ([\d.]+px);"/)?.[1]
    if (width) {
      result.value = svg.replace("width=\"100%\"", `width="${width}"`)
    }
    else {
      result.value = svg
    }
    errMsg.value = ""
  }
  catch (error) {
    errMsg.value = (error as any).str || String(error)
  }
  finally {
    endLoading()
  }
}

function exportSvg() {
  const url = imageUrl.value
  if (!url) {
    return
  }

  downloadAsUrl(url, `mermaid-${Date.now()}.svg`)
}

async function exportPng() {
  if (!imgRef.value) {
    return
  }

  const img = imgRef.value.imageRef
  const width = img.clientWidth
  const height = img.clientHeight

  const canvas = document.createElement("canvas")
  canvas.width = width * 2
  canvas.height = height * 2
  canvas.getContext("2d")?.drawImage(img, 0, 0, canvas.width, canvas.height)
  const dataUrl = canvas.toDataURL("image/png")

  downloadAsUrl(dataUrl, `mermaid-${Date.now()}.png`)
}

const renderDebounce = useDebounceFn(render, 100)

watch(() => [props.code, props.path], renderDebounce, { immediate: true })
const width = ref(0)

useResizeObserver(container, (entries) => {
  const entry = entries[0]
  if (!entry)
    return

  if (!width.value) {
    width.value = entry.contentRect.width
    return
  }

  console.error("container resize", entry.contentRect.width)

  if (entry.contentRect.width !== width.value) {
    width.value = entry.contentRect.width
    renderDebounce()
  }
})
</script>

<style scoped lang="sass">
.mermaid__wrapper
  @apply relative
.mermaid__actions
  @apply absolute-br opacity-0 group-hover/mermaid:opacity-100 flex gap-2 items-center transition
</style>
