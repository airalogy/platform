<template>
  <n-upload
    :file-list="attachments"
    :max="props.max || 5"
    :show-download-button="false"
    :show-remove-button="!readonly"
    :list-type="props.compact ? 'image' : 'image-card'"
    :abstract="props.compact"
    @remove="handleRemove"
    @preview="handlePreview"
  >
    <n-upload-file-list v-if="props.compact" class="compact__list" />
  </n-upload>
</template>

<script setup lang="ts">
import type { UploadFileInfo } from "naive-ui"
import { NUpload, NUploadFileList } from "naive-ui"

const props = defineProps<{
  attachments: Chat.Attachment[]
  max?: number
  readonly?: boolean
  compact?: boolean
}>()

const emit = defineEmits<{
  (e: "remove", fileId: string): void
}>()

function handleRemove(data: { file: UploadFileInfo, fileList: UploadFileInfo[] }) {
  emit("remove", data.file.id as string)
}

function handlePreview(file: UploadFileInfo) {
  if (file.type === "application/pdf" && file.url)
    window.open(file.url, "_blank")
}

function formatFileSize(bytes: number): string {
  if (bytes === 0)
    return "0 B"
  const k = 1024
  const sizes = ["B", "KB", "MB", "GB"]
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${Number.parseFloat((bytes / (k ** i)).toFixed(1))} ${sizes[i]}`
}
</script>

<style lang="sass" scoped>
.file-preview
  transition: all 0.3s ease
  &:hover
    background-color: rgba(0, 0, 0, 0.05)

.compact__list
  margin-bottom: 6px
  :deep(.n-upload-file-info__action .n-button)
    --n-height: 24px!important
    --n-padding: 0 3px!important

:deep(.n-upload-file.n-upload-file--image-card-type), :deep(.n-upload-trigger.n-upload-trigger--image-card)
  height: 64px
  width: 64px
:deep(.n-upload-file-list.n-upload-file-list--grid)
  grid-template-columns: repeat(auto-fill, 64px)
</style>
