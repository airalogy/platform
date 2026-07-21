<template>
  <div class="chat-markdown-body">
    <template v-if="sourceItems.length > 0">
      <aimd-markdown-preview
        v-for="(sourceItem, index) in sourceItems"
        :key="index"
        :content="sourceItem"
        :loading="props.loading"
        :resolve-url="props.resolveFile"
        :mermaid-component="MermaidBlock"
        body-class="chat-markdown-body__content"
      />
    </template>
    <n-icon v-else-if="props.loading" :component="LoadingIcon" size="18" class="top-1" />
  </div>
</template>

<script setup lang="ts">
import { AimdMarkdownPreview } from "@airalogy/aimd-renderer/vue"
import LoadingIcon from "~icons/svg-spinners/3-dots-fade"
import { NIcon } from "naive-ui"
import { computed } from "vue"
import MermaidBlock from "../../modules/mermaid/mermaid-block.vue"

interface Props {
  source?: string | string[]
  loading?: boolean
  resolveFile?: (id: string) => Promise<{ url: string } | null>
}

const props = withDefaults(defineProps<Props>(), {
  source: "",
  loading: false,
  resolveFile: undefined,
})

const sourceItems = computed(() => {
  const source = props.source
  if (Array.isArray(source)) {
    return source.filter((item): item is string => typeof item === "string" && Boolean(item))
  }
  return source ? [source] : []
})
</script>
