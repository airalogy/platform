<template>
  <div v-if="thinkingText" class="thinking-content mb-3">
    <n-collapse
      v-model:expanded-names="expandedNames"
      :theme-overrides="{ titlePadding: '12px 0 0 0', itemMargin: '0 0 0 0' }"
    >
      <n-collapse-item name="thinking">
        <template #header>
          <div class="flex items-center gap-2">
            <n-icon :component="BrainIcon" size="16" class="text-gray-400" />
            <span class="text-sm text-gray-500">Thinking Process</span>
          </div>
        </template>
        <div class="thinking-text overflow-hidden text-ellipsis whitespace-pre-wrap break-all rounded-md bg-white p-3 text-sm">
          <styled-markdown-preview :source="thinkingText" />
        </div>
      </n-collapse-item>
    </n-collapse>
  </div>
</template>

<script setup lang="ts">
import StyledMarkdownPreview from "@airalogy/components/markdown-editor/extensions/chat/StyledMarkdownPreview.vue"
import BrainIcon from "~icons/ion/bulb-outline"
import { NCollapse, NCollapseItem, NIcon } from "naive-ui"
import { onMounted, ref, watch } from "vue"

interface Props {
  thinkingText?: string
  hasActualContent?: boolean
}

const props = defineProps<Props>()

// Reactive expanded state, initialized based on hasActualContent
const expandedNames = ref<string[]>([])

// Initialize and update expanded state
function updateExpandedState() {
  // Collapse if actual content exists, otherwise expand
  expandedNames.value = props.hasActualContent ? [] : ["thinking"]
}

// Initialize on component mount
onMounted(() => {
  updateExpandedState()
})

// Watch for thinkingText changes (e.g., when switching conversations)
watch(() => props.thinkingText, () => {
  updateExpandedState()
}, { immediate: true })

// Watch for hasActualContent changes and auto-collapse when actual content appears
watch(() => props.hasActualContent, (hasActual, prevHasActual) => {
  // Auto-collapse when transitioning from no content to having content
  if (hasActual && !prevHasActual) {
    expandedNames.value = []
  }
})
</script>

<style lang="sass" scoped>
.thinking-text
  line-height: 1.6
  color: #9ca3af
  opacity: 0.85

  :deep(.chat-markdown-body)
    color: #9ca3af
    opacity: 0.85

  :deep(p)
    margin: 0.5em 0
    color: inherit

    &:first-child
      margin-top: 0

    &:last-child
      margin-bottom: 0

  :deep(code)
    color: #6b7280
    background: #e5e7eb
    padding: 0.125rem 0.25rem
    border-radius: 0.25rem

  :deep(pre)
    color: #6b7280
    background: #e5e7eb

  :deep(strong), :deep(b)
    color: #6b7280

  :deep(em), :deep(i)
    color: #9ca3af

  // Dark mode has been removed from the project

    :deep(pre)
      color: #9ca3af
      background: #374151
</style>
