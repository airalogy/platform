<template>
  <div class="space-y-4">
    <div class="border rounded-lg bg-gray-50 p-4">
      <h4 class="mb-2 font-medium">
        Installation
      </h4>
      <n-code :code="installationCode" language="bash" />
    </div>

    <div class="border rounded-lg bg-gray-50 p-4">
      <h4 class="mb-2 font-medium">
        Quick Start
      </h4>
      <div class="prose max-w-none">
        <markdown-editor
          :text="quickStartGuide"
          readonly
          content-class="!p-0"
          :post-add-attachments="postAddAttachments"
          :resolve-file="getCachedAttachment"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { getCachedAttachment, postAddAttachments } from "@/service/api/attachments"
import { MarkdownEditor } from "@airalogy/components"

interface Props {
  installationCode?: string
  quickStartGuide?: string
}

withDefaults(defineProps<Props>(), {
  installationCode: "# Installation instructions not available",
  quickStartGuide: "Usage guide not available",
})
</script>
