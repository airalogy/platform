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
        <aimd-markdown-preview
          v-if="protocolInfo.aimd"
          :content="protocolInfo.aimd"
          :mermaid-component="MermaidBlock"
          body-class="markdown-body"
          mode="preview"
        />
      </n-collapse-item>
    </n-collapse>
  </div>
</template>

<script setup lang="ts">
import { useProtocolInfoStore } from "@/views/project-protocols/hooks/useProtocolInfoStore"
import ProtocolFields from "@/views/project-protocols/modules/protocol/protocol-fields.vue"
import { AimdMarkdownPreview } from "@airalogy/aimd-renderer/vue"
import MermaidBlock from "@airalogy/components/markdown-editor/modules/mermaid/mermaid-block.vue"
import { NCollapse, NCollapseItem } from "naive-ui"

const { protocolInfo } = useProtocolInfoStore()! || {}
</script>

<style scoped lang="scss">
.overview-tab {
  @apply p-4;
}
</style>
