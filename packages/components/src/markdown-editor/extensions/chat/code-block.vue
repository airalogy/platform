<template>
  <node-view-wrapper class="chat-code-block" as="div">
    <code-snippet-preview
      :item="item"
      :input-id="inputId"
      :border-color="borderColor"
      @delete="deleteNode"
    />
  </node-view-wrapper>
</template>

<script setup lang="ts">
import { type NodeViewProps, NodeViewWrapper } from "@tiptap/vue-3"
import { useThemeVars } from "naive-ui"
import CodeSnippetPreview from "./CodeSnippetPreview.vue"

const props = defineProps<NodeViewProps>()
const { node, deleteNode, selected } = toRefs(props)

const item = computed(() => node.value.attrs.item)
const inputId = computed(() => node.value.attrs.inputId)
const themeVars = useThemeVars()

const borderColor = computed(() => {
  if (selected.value) {
    return themeVars.value.primaryColor
  }

  return undefined
})
</script>
