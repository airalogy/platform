<template>
  <div class="table-file-cell">
    <template v-if="fileInfo">
      <div class="file-display" :class="{ 'is-image': isImage }">
        <!-- Image thumbnail -->
        <div v-if="isImage" class="file-thumbnail" @click="handlePreview">
          <img v-if="thumbnailUrl" :src="thumbnailUrl" :alt="fileInfo.name">
          <n-icon v-else :component="ImageIcon" :size="32" />
        </div>

        <!-- File icon for non-images -->
        <div v-else class="file-icon" @click="handlePreview">
          <file-type-icon :type="fileType" :size="32" />
        </div>

        <!-- File info -->
        <div class="file-info">
          <div class="file-name" :title="fileInfo.name">
            {{ fileInfo.name }}
          </div>
          <div v-if="fileSize" class="file-size">
            {{ fileSize }}
          </div>
        </div>

        <!-- Actions -->
        <div class="file-actions">
          <n-button text @click="handleDownload">
            <template #icon>
              <n-icon :component="DownloadIcon" :size="16" />
            </template>
          </n-button>
          <n-button text :disabled="disabled" @click="handleRemove">
            <template #icon>
              <n-icon :component="DeleteIcon" :size="16" />
            </template>
          </n-button>
        </div>
      </div>
    </template>

    <!-- Upload button when no file -->
    <template v-else>
      <n-upload
        :custom-request="handleUpload"
        :accept="acceptType"
        :show-file-list="false"
        :disabled="disabled"
      >
        <n-button size="small" :disabled="disabled">
          <template #icon>
            <n-icon :component="UploadIcon" />
          </template>
          Upload {{ fileTypeName }}
        </n-button>
      </n-upload>
    </template>

    <!-- Preview modal for images -->
    <n-modal
      v-if="isImage && showPreview"
      v-model:show="showPreview"
      preset="card"
      :title="fileInfo?.name"
      class="max-w-90vw"
      :bordered="false"
      size="huge"
    >
      <img v-if="thumbnailUrl" :src="thumbnailUrl" :alt="fileInfo?.name" class="max-h-70vh max-w-full">
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import type { UploadCustomRequestOptions } from "naive-ui"
import type { IAIMDInputProps } from "../../types/props"
import { getCachedAttachment, postAddAttachments } from "@/service/api/attachments"
import { FileTypeIcon } from "@airalogy/components"
import { getFileExtensionFromBasename, getFileType } from "@airalogy/shared/utils"
import CloudUploadOutline from "~icons/ion/cloud-upload-outline"
import DownloadOutline from "~icons/ion/download-outline"
import ImageOutline from "~icons/ion/image-outline"
import TrashOutline from "~icons/ion/trash-outline"
import { useAIMDInject } from "../../composables/useAIMDHelpers"

const props = defineProps<IAIMDInputProps>()

const UploadIcon = CloudUploadOutline
const DeleteIcon = TrashOutline
const DownloadIcon = DownloadOutline
const ImageIcon = ImageOutline

const { handleFieldChange, protocolId } = useAIMDInject()!

const disabled = computed(() => props.disabled)
const showPreview = ref(false)
const loadedFileInfo = ref<any>(null)

// Watch for file ID changes and load file info
watchEffect(() => {
  const value = props.model?.value

  if (!value) {
    loadedFileInfo.value = null
    return
  }

  // Handle string value (direct Airalogy file ID)
  if (typeof value === "string" && value.startsWith("airalogy.id.file.")) {
    const fileId = value
    const parts = fileId.split(".")
    const extension = parts[parts.length - 1]

    getCachedAttachment(fileId).then((attachment) => {
      if (attachment) {
        loadedFileInfo.value = {
          name: attachment.filename || `file.${extension}`,
          url: attachment.url,
          thumbnailUrl: attachment.url,
          size: (attachment as any).size,
          id: attachment.id || attachment.airalogy_file_id,
          airalogy_file_id: fileId,
        }
      }
    }).catch(console.error)
    return
  }

  // Handle object value
  if (typeof value === "object") {
    // Check if it has Airalogy file ID in 'file' field
    if ("file" in value && value.file) {
      const fileId = value.file as string

      if (fileId.startsWith("airalogy.id.file.")) {
        const parts = fileId.split(".")
        const extension = parts[parts.length - 1]

        getCachedAttachment(fileId).then((attachment) => {
          if (attachment) {
            loadedFileInfo.value = {
              name: attachment.filename || `${value.label || value.title || "file"}.${extension}`,
              url: attachment.url,
              thumbnailUrl: attachment.url,
              size: (attachment as any).size,
              id: attachment.id || attachment.airalogy_file_id,
              airalogy_file_id: fileId,
            }
          }
        }).catch(console.error)
      }
    }
  }
})

// Get file info from model value
const fileInfo = computed(() => {
  const value = props.model?.value

  if (!value)
    return null

  // Return cached loaded file info if available (for Airalogy file IDs)
  if (loadedFileInfo.value) {
    return loadedFileInfo.value
  }

  // Handle string value (direct Airalogy file ID)
  if (typeof value === "string" && value.startsWith("airalogy.id.file.")) {
    const parts = value.split(".")
    const extension = parts[parts.length - 1]

    // Return temporary info while loading
    return {
      name: `file.${extension}`,
      url: null,
      thumbnailUrl: null,
      id: value,
      airalogy_file_id: value,
    }
  }

  // Handle different object value formats
  if (typeof value === "object") {
    // Check if it has airalogy_file_id directly (assigner result format)
    if ("airalogy_file_id" in value && value.airalogy_file_id) {
      return {
        name: (value as any).name || (value as any).filename,
        url: (value as any).url,
        thumbnailUrl: (value as any).thumbnailUrl || (value as any).url,
        size: (value as any).size,
        id: (value as any).id || (value as any).airalogy_file_id,
        airalogy_file_id: (value as any).airalogy_file_id,
      }
    }

    // Check if it has Airalogy file ID in 'file' field
    if ("file" in value && value.file) {
      const fileId = value.file as string
      if (fileId.startsWith("airalogy.id.file.")) {
        const parts = fileId.split(".")
        const extension = parts[parts.length - 1]

        // Return temporary info while loading
        return {
          name: `${value.label || value.title || "file"}.${extension}`,
          url: null,
          thumbnailUrl: null,
          id: fileId,
          airalogy_file_id: fileId,
        }
      }
    }

    // Check if it has file info properties (original format)
    if ("name" in value || "filename" in value) {
      return {
        name: (value as any).name || (value as any).filename,
        url: (value as any).url,
        thumbnailUrl: (value as any).thumbnailUrl,
        size: (value as any).size,
        id: (value as any).id || (value as any).airalogy_file_id,
        airalogy_file_id: (value as any).airalogy_file_id,
      }
    }
  }

  return null
})

const fileType = computed(() => {
  if (!fileInfo.value?.name)
    return "file"
  const ext = getFileExtensionFromBasename(fileInfo.value.name)
  return getFileType(ext, true)
})

const isImage = computed(() => fileType.value === "image")

const thumbnailUrl = computed(() => {
  if (!fileInfo.value)
    return null
  return fileInfo.value.url || fileInfo.value.thumbnailUrl || null
})

const fileSize = computed(() => {
  if (!fileInfo.value?.size)
    return null
  return formatFileSize(fileInfo.value.size)
})

const acceptType = computed(() => {
  const type = props.type
  // Ensure type is a string, not an object
  if (!type || typeof type !== "string")
    return "*"

  if (type === "image")
    return "image/*"
  if (type === "pdf")
    return ".pdf"
  if (type === "csv")
    return ".csv"
  return "*"
})

const fileTypeName = computed(() => {
  const type = props.type
  // Ensure type is a string, not an object
  if (!type || typeof type !== "string")
    return "File"

  if (type === "image")
    return "Image"
  if (type === "csv")
    return "CSV"
  if (type === "pdf")
    return "PDF"
  return "File"
})

function formatFileSize(bytes: number): string {
  if (bytes === 0)
    return "0 B"
  const k = 1024
  const sizes = ["B", "KB", "MB", "GB"]
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / k ** i).toFixed(1)} ${sizes[i]}`
}

function handlePreview() {
  if (isImage.value) {
    showPreview.value = true
  }
  else if (thumbnailUrl.value) {
    window.open(thumbnailUrl.value, "_blank")
  }
}

async function handleDownload() {
  if (!fileInfo.value)
    return

  // If we have URL, download directly
  if (thumbnailUrl.value) {
    const link = document.createElement("a")
    link.href = thumbnailUrl.value
    link.download = fileInfo.value.name || "download"
    link.click()
    return
  }

  // If no URL but we have Airalogy file ID, fetch the file info and download
  const airalogyFileId = fileInfo.value.airalogy_file_id || fileInfo.value.id
  if (airalogyFileId && airalogyFileId.startsWith("airalogy.id.file.")) {
    try {
      const attachment = await getCachedAttachment(airalogyFileId)
      if (attachment && attachment.url) {
        const link = document.createElement("a")
        link.href = attachment.url
        link.download = attachment.filename || fileInfo.value.name || "download"
        link.click()
      }
    }
    catch (error) {
      console.error("Failed to download file:", error)
    }
  }
}

function handleRemove() {
  const { scope, prop, info } = props
  handleFieldChange({
    scope,
    prop,
    value: null,
    info,
  })
}

async function handleUpload({ file, onFinish, onError }: UploadCustomRequestOptions) {
  try {
    // Use the existing postAddAttachments API function
    const response = await postAddAttachments(file.file as File, protocolId.value)

    if (response.error) {
      throw new Error(response.error as any)
    }

    if (!response.data) {
      throw new Error("No data returned from upload")
    }

    const result = response.data
    const uploadedFileInfo = {
      id: result.id || result.airalogy_file_id,
      name: result.filename || file.name,
      url: result.url,
      size: (file.file as File).size,
      airalogy_file_id: result.airalogy_file_id || result.id,
    }

    onFinish()

    // Update the field value
    const { scope, prop, info } = props
    handleFieldChange({
      scope,
      prop,
      value: uploadedFileInfo,
      info,
    })
  }
  catch (error) {
    console.error("Upload failed:", error)
    onError()
  }
}
</script>

<style scoped lang="sass">
.table-file-cell
  width: 100%
  max-width: 300px

.file-display
  display: flex
  align-items: center
  gap: 8px
  padding: 4px 8px
  border: 1px solid #e0e0e0
  border-radius: 4px
  background: #fafafa

  &:hover
    background: #f5f5f5

  &.is-image
    cursor: pointer

.file-thumbnail,
.file-icon
  flex-shrink: 0
  width: 40px
  height: 40px
  display: flex
  align-items: center
  justify-content: center
  border-radius: 4px
  overflow: hidden
  background: white
  cursor: pointer

  img
    width: 100%
    height: 100%
    object-fit: cover

.file-info
  flex: 1
  min-width: 0

.file-name
  font-size: 13px
  font-weight: 500
  overflow: hidden
  text-overflow: ellipsis
  white-space: nowrap

.file-size
  font-size: 11px
  color: #999

.file-actions
  display: flex
  gap: 4px
  flex-shrink: 0
</style>
