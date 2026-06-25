<template>
  <div v-if="protocolInfo" class="overview-tab">
    <!-- Protocol Fields Preview -->
    <n-collapse>
      <n-collapse-item title="Protocol Fields" name="fields">
        <protocol-fields
          v-if="protocolInfo.fields"
          :item="protocolInfo"
        />
      </n-collapse-item>
    </n-collapse>

    <!-- Protocol Content -->
    <n-collapse class="mt-4">
      <n-collapse-item title="Protocol Content" name="content">
        <markdown-preview
          v-if="protocolInfo.aimd"
          :text="protocolInfo.aimd"
          mode="preview"
        />
      </n-collapse-item>
    </n-collapse>
  </div>
</template>

<script setup lang="ts">
import { useProtocolInfoStore } from "@/views/project-protocols/hooks/useProtocolInfoStore"
import ProtocolFields from "@/views/project-protocols/modules/protocol/protocol-fields.vue"
import MarkdownPreview from "@airalogy/components/file-preview/markdown-preview.vue"
import { NCollapse, NCollapseItem } from "naive-ui"

// Use unified system - in preview mode, no custom renderers needed
// The markdown-preview component will use default rendering
const { protocolInfo } = useProtocolInfoStore()! || {}
</script>

<style scoped lang="scss">
.overview-tab {
  @apply p-4;
}
</style>
