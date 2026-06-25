<template>
  <div class="min-h-[32px] w-full">
    <n-spin :show="isLoading">
      <!-- Error State -->
      <div v-if="hasError" class="mt-2 flex items-center justify-between">
        <n-text type="error">
          Failed to load asset {{ props.id }}
        </n-text>
        <n-button secondary size="tiny" type="error" @click="fetchAssetUrl">
          <template #icon>
            <n-icon><icon-tabler-refresh /></n-icon>
          </template>
        </n-button>
      </div>

      <!-- Empty State -->
      <div v-else-if="!assetData" class="mt-2 flex items-center gap-2">
        <file-type-icon :type="props.type" />
        <n-text class="text-gray-400">
          No asset found for {{ props.id }}
        </n-text>
      </div>

      <!-- Use FilePreview directly -->
      <file-preview
        v-else-if="fileForPreview"
        :file="fileForPreview"
        :can-edit="false"
        content-class="max-w-full"
        @error="handlePreviewError"
        @open-as-text="handleOpenAsText"
      />
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import type { UploadFileInfo } from "naive-ui"
import { getReferenceAssets } from "@/service/api/project-protocols"
import FilePreview from "@airalogy/components/file-preview/index.vue"
import FileTypeIcon from "@airalogy/components/file-type-icon.vue"

interface Props {
  id?: string | number
  protocolId?: string | number
  url?: string
  name?: string
  type: "image" | "audio" | "file" | "unknown" | "csv" | "video"
}

const props = defineProps<Props>()
const assetData = ref<Api.Attachment.AttachmentItem | null>(null)
const isLoading = ref(false)
const hasError = ref(false)

// Convert assetData to UploadFileInfo format for FilePreview component
const fileForPreview = computed((): UploadFileInfo | null => {
  if (!assetData.value)
    return null

  return {
    id: assetData.value.airalogy_file_id || assetData.value.id || "",
    airalogy_file_id: assetData.value.airalogy_file_id || assetData.value.id || "",
    name: assetData.value.filename || "Unknown File",
    url: assetData.value.url,
    status: "finished",
    file: undefined, // We don't have the actual File object
    type: props.type || "unknown",
  } as UploadFileInfo
})

function handlePreviewError(error: string) {
  console.error("Preview error:", error)
  // You can add user notification here if needed
}

function handleOpenAsText(file: UploadFileInfo) {
  // Handle opening file as text - could open in a new modal or external editor
  if (file.url) {
    window.open(file.url, "_blank")
  }
}

async function fetchAssetUrl() {
  if (!props.id || !props.protocolId)
    return
  isLoading.value = true
  hasError.value = false
  try {
    const response = await getReferenceAssets(props.id)
    if (response.data)
      assetData.value = response.data
  }
  catch (error) {
    console.error("Failed to fetch asset URL:", error)
    hasError.value = true
  }
  finally {
    isLoading.value = false
  }
}

onMounted(() => {
  if (props.url) {
    assetData.value = {
      id: props.id?.toString() ?? "",
      filename: props.name ?? "Unknown",
      url: props.url,
      airalogy_file_id: props.id?.toString() ?? "",
    }
  }
  else if (props.id) {
    fetchAssetUrl()
  }
})
</script>

<style scoped lang="sass">
</style>
