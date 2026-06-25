<template>
  <template v-if="splitState[editorId]">
    <n-split
      v-model:size="splitSize"
      :resize-trigger-size="disabled ? 0 : 3"
      :pane2-class="disabled ? 'hidden' : undefined"
    >
      <template #1>
        <code-editor
          :key="`editor-${editorId}`"
          :editor-id="editorId"
          class="flex-1 overflow-hidden"
        />
      </template>
      <template v-if="nextEditorId !== -1" #2>
        <split-editor
          :key="`split-${editorId + 1}`"
          :class="{ hidden: nextEditorId === -1 }"
          :editor-id="nextEditorId"
          :split-state="splitState"
        />
      </template>
    </n-split>
  </template>
</template>

<script setup lang="ts">
import { onBeforeUnmount, watch } from "vue"
import CodeEditor from "./code-editor.vue"
import { useEditorStore } from "./store/editorStore"

interface Props {
  editorId: number
  splitState: boolean[]
}

const props = defineProps<Props>()
const { getEditorInfo, removeEditor } = useEditorStore()

const nextEditorId = computed(() => props.splitState.findIndex((active, index) => active && index > props.editorId))

const disabled = computed(() => !props.splitState[nextEditorId.value] || !nextEditorId.value)

// Reactive split size that changes based on split state
const splitSize = ref(disabled.value ? 1 : 0.5)

// Watch for changes in split state or disabled state
watch(
  [() => [...props.splitState], disabled],
  ([newSplitState, newDisabled]) => {
    // Update split size when split state changes
    if (newDisabled) {
      splitSize.value = 1
    }
    else {
      // If we're enabling a previously disabled split
      // Distribute space evenly among all active editors
      const activeEditors = newSplitState.filter(Boolean).length

      if (activeEditors > 1) {
        // Calculate proportions based on the active editors
        // For nested splits, we need to set proportional sizes
        // If total editors = 3, first split should be 1/3 : 2/3
        // If total editors = 2, first split should be 1/2 : 1/2

        if (props.editorId === 0) {
          // First split level calculation
          const firstProportion = 1 / activeEditors
          splitSize.value = firstProportion
        }
        else if (props.editorId === 1 && activeEditors === 3) {
          // Second split level calculation (only needed with 3 editors)
          // For 3 editors, the second split should divide the remaining 2/3 in half
          // So second split is 1/2 : 1/2 (of the remaining 2/3)
          splitSize.value = 0.5
        }
      }
    }
  },
  { immediate: true, deep: true },
)

// Clean up only if component is completely unmounted, not just hidden
onBeforeUnmount(() => {
  // Only dispose editor if the parent split view is being completely unmounted
  // Not when just toggling between views
  if (!props.splitState[props.editorId]) {
    const editor = getEditorInfo(props.editorId)
    if (editor) {
      try {
        removeEditor(props.editorId)
      }
      catch (error) {
        console.error(`Error cleaning up editor ${props.editorId}:`, error)
      }
    }
  }
})
</script>

<style lang="scss" scoped>
.hidden {
  display: none;
}
</style>
