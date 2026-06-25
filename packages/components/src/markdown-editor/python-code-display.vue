<template>
  <div class="python-code-display">
    <n-tabs v-model:value="activeTab" type="segment" class="mb-4">
      <n-tab-pane name="model" tab="model.py">
        <shiki-code-viewer :code="modelCode" />
      </n-tab-pane>
      <n-tab-pane name="assigner" tab="assigner.py">
        <shiki-code-viewer :code="assignerCode" />
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue"
import ShikiCodeViewer from "../file-preview/code-preview/shiki-code-viewer.vue"

defineProps<{
  modelCode: string
  assignerCode: string
}>()

const activeTab = ref("model")
</script>

<style lang="sass" scoped>
.python-code-display
  width: 100%
</style>
