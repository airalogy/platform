<template>
  <node-view-wrapper as="div" class="table-wrapper">
    <table ref="contentDOM" class="table-view" />
  </node-view-wrapper>
</template>

<script setup lang="ts">
import type { Node } from "@tiptap/pm/model"
import { type NodeViewProps, NodeViewWrapper } from "@tiptap/vue-3"

const props = defineProps<NodeViewProps>()

const contentDOM = ref<HTMLDivElement>()

// Expose required methods for Tiptap
defineExpose({
  update(node: Node) {
    return node.type === props.node.type
  },
  ignoreMutation(mutation: MutationRecord) {
    return mutation.type === "attributes"
  },
  contentDOM,
})
</script>

<style lang="sass" scoped>
.table-wrapper
  @apply w-full overflow-x-auto my-4

:deep(.table-view)
  border-collapse: collapse
  table-layout: fixed
  width: 100%
  margin: 0
  overflow: hidden

  td, th
    border: 2px solid #ebeef5
    box-sizing: border-box
    min-width: 1em
    padding: 3px 5px
    position: relative
    vertical-align: top

  th
    font-weight: 500
    text-align: left
    background-color: #f5f7fa

  .column-resize-handle
    @apply bottom-0 pointer-events-none absolute -right-0.5 top-0 w-1 z-20

    background: rgba(var(--primary-color) / 0.4)

  .selectedCell
    @apply relative
    &::after
      @apply z-20 absolute left-0 right-0 top-0 bottom-0 pointer-events-none
      content: ""
      background: rgba(var(--primary-color) / 0.4)
</style>
