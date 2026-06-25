<template>
  <markdown-editor
    v-if="isMarkdownMode"
    v-model:text="localValue"
    preset="simple" :placeholder="props.placeholder"
    :readonly="props.disabled" class="size-full !b-0"
    :extra-actions="[{ name: 'toggleMode', items: ['toggleMode'] }]" :extensions="[ToggleModeExtension]"
    raw-result
    :editor-props="{ attributes: { class: '!p-0 tiptap-editor' } }"
    :style="editorBorderStyle"
    :post-add-attachments="postAddAttachments"
    @focus="handleFocus"
    @blur="handleBlur"
  />
  <n-input v-else v-bind="{ ...$attrs, ...annotationInputProps }" class="min-w-80 flex-1">
    <template v-if="!props.disabled" #suffix>
      <n-button
        quaternary type="primary" size="small" class="flex-shrink-0 opacity-20 !h-full hover:opacity-100"
        :color="isRsAnnotation ? 'rgba(255, 157, 0, 0.8)' : 'rgba(24, 160, 88, 0.8)'" :title="isMarkdownMode ? 'Switch to simple input' : 'Switch to markdown editor'"
        @click="toggleMode"
      >
        <template #icon>
          <icon-mdi-markdown v-if="!isMarkdownMode" />
          <icon-mdi-text-box v-else />
        </template>
      </n-button>
    </template>
  </n-input>
</template>

<script setup lang="ts">
import type { EditorEvents } from "@tiptap/vue-3"
import type { IAIMDInputProps } from "../../types/props"
import { postAddAttachments } from "@/service/api/attachments"
import { MarkdownEditor } from "@airalogy/components"
import { createToggleMode } from "@airalogy/components/markdown-editor/extensions/create-toggle-menu"
import { NButton, NInput } from "naive-ui"
import { computed, ref, watch } from "vue"
import { useInputProps } from "../../composables/useInputProps"

defineOptions({
  inheritAttrs: false,
})

const props = defineProps<IAIMDInputProps>()

const { annotationInputProps } = useInputProps(props)
const isMarkdownMode = ref(false)
const localValue = ref(props.model?.value?.annotation || "")

// Computed properties for styling based on annotation type
const isRsAnnotation = computed(() => props.type === "rs-annotation" || props.type === "rs-minimal")
const editorBorderStyle = computed(() => {
  if (isRsAnnotation.value) {
    return {
      "--editor-border-color": "255 157 0",
      "--editor-border-hover-color": "255 157 0",
      "--editor-border-focus-color": "255 157 0",
    }
  }
  else {
    // For rc-annotation, use blue color
    return {
      "--editor-border-color": "24 160 88",
      "--editor-border-hover-color": "24 160 88",
      "--editor-border-focus-color": "24 160 88",
    }
  }
})

function hasMarkdownFormatting(text: string): boolean {
  // Common markdown patterns
  const patterns = [
    /[*_]{1,2}[^*_]+[*_]{1,2}/, // Bold/Italic
    /`[^`]+`/, // Inline code
    /```[\s\S]*?```/, // Code blocks
    /^\s*#{1,6}\s+/, // Headers
    /^\s*[-*+]\s+/m, // Unordered lists
    /^\s*\d+\.\s+/m, // Ordered lists
    /\[([^\]]+)\]\(([^)]+)\)/, // Links
    /!\[([^\]]+)\]\(([^)]+)\)/, // Images
    /^\s*>\s+/m, // Blockquotes
    /^\s*[-*_]{3,}\s*$/m, // Horizontal rules
    /\|[^|]+\|/, // Tables
    /~~[^~]+~~/, // Strikethrough
  ]

  return patterns.some(pattern => pattern.test(text))
}

// Check for markdown formatting once during initialization
if (localValue.value && hasMarkdownFormatting(localValue.value)) {
  isMarkdownMode.value = true
}

watch(localValue, (value) => {
  if (!isMarkdownMode.value) {
    return
  }

  const onUpdateValue = annotationInputProps.value["onUpdate:value"]
  if (Array.isArray(onUpdateValue)) {
    onUpdateValue.forEach(fn => fn?.(value, value))
  }
  else if (onUpdateValue) {
    onUpdateValue(value, value)
  }
})

const ToggleModeExtension = createToggleMode(() => {
  toggleMode()
})

watch(() => props.model?.value?.annotation, (newVal) => {
  localValue.value = newVal || ""
})

function toggleMode() {
  isMarkdownMode.value = !isMarkdownMode.value
}

function handleFocus(options: EditorEvents["focus"]) {
  if (annotationInputProps.value.onFocus) {
    // @ts-expect-error only one callback is allowed
    annotationInputProps.value.onFocus(options)
  }
}

function handleBlur(options: EditorEvents["blur"]) {
  if (annotationInputProps.value.onBlur) {
    // @ts-expect-error only one callback is allowed
    annotationInputProps.value.onBlur(options.event)
  }
}
</script>

<style scoped lang="sass">

</style>
