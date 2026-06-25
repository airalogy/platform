<template>
  <node-view-wrapper class="task-item-wrapper">
    <li :data-type="props.node?.type.name" :data-done="done.toString()" data-drag-handle>
      <span contenteditable="false">
        <n-checkbox v-model="done" class="mr-2" />
      </span>

      <node-view-content class="todo-content" />
    </li>
  </node-view-wrapper>
</template>

<script setup lang="ts">
import { NodeViewContent, type NodeViewProps, NodeViewWrapper } from "@tiptap/vue-3"

const props = defineProps<NodeViewProps>()

const done = computed(() => {
  return {
    get(): boolean {
      return props.node?.attrs.done
    },
    set(done: boolean) {
      props.updateAttributes?.({
        done,
      })
    },
  }
})
</script>
