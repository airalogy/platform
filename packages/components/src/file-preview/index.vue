<template>
  <n-card
    size="small" :bordered="props.bordered" class="size-full"
    :content-class="['overflow-auto !flex-auto !min-w-full min-h-fit', collapsed ? 'hidden' : 'resize', props.contentClass || ''].join(' ')"
    :content-style="contentStyle"
  >
    <template #header>
      <div class="w-full flex flex-wrap items-center justify-between">
        <div class="flex items-center gap-2">
          <slot name="icon">
            <n-icon size="16" :component="fileIcon" />
          </slot>
          <slot name="name">
            <n-tooltip v-if="props.file.airalogy_file_id" trigger="hover">
              <template #trigger>
                <span class="min-w-10 text-sm font-medium">{{ fileName }}</span>
              </template>
              <copy-to-clip :text="props.file.airalogy_file_id" show-success color="#ffffff" />
            </n-tooltip>
            <span v-else class="text-sm font-medium">{{ fileName }}</span>
          </slot>

          <slot name="type">
            <n-tag size="small" type="info">
              {{ fileType.toUpperCase() }}
            </n-tag>
          </slot>

          <div v-if="fileSize" class="ml-2 text-xs text-gray-500">
            {{ fileSize }}
          </div>

          <slot name="info" />
        </div>

        <div class="flex items-center gap-2">
          <n-button
            v-if="props.showPreview"
            size="small"
            quaternary
            @click="handlePreview"
          >
            <template #icon>
              <n-icon><icon-ion-eye-outline /></n-icon>
            </template>
            Preview
          </n-button>
          <n-button
            v-if="props.canEdit"
            size="small"
            quaternary
            type="error"
            @click="handleRemove"
          >
            <template #icon>
              <n-icon><icon-ion-trash-outline /></n-icon>
            </template>
            Delete
          </n-button>
          <n-button v-if="downloadUrl" size="small" quaternary @click="handleDownload">
            <template #icon>
              <n-icon><icon-ion-download-outline /></n-icon>
            </template>
            Download
          </n-button>
          <n-button v-if="downloadUrl && canOpenInBrowser" size="small" quaternary @click="handleOpenExternal">
            <template #icon>
              <n-icon><icon-ion-open-outline /></n-icon>
            </template>
            Open in Tab
          </n-button>

          <slot name="actions" />
        </div>
      </div>
    </template>
    <template #header-extra>
      <n-button
        size="small"
        quaternary
        :aria-label="collapsed ? 'Expand preview' : 'Collapse preview'"
        @click="handleToggleCollapse"
      >
        <template #icon>
          <n-icon>
            <icon-ion-chevron-forward-outline v-if="collapsed" />
            <icon-ion-chevron-down-outline v-else />
          </n-icon>
        </template>
      </n-button>
    </template>

    <!-- PDF Preview -->
    <div v-if="error" class="h-64 flex flex-col items-center justify-center text-red-500">
      <n-icon size="48" class="mb-4">
        <icon-ion-warning-outline />
      </n-icon>
      <p class="mb-2 text-lg font-medium">
        {{ error }}
      </p>
    </div>

    <template v-else>
      <pdf-viewer v-if="fileType === 'pdf'" :pdf-url="props.file.url || ''" class="size-full min-h-12" />

      <!-- CSV Preview -->
      <csv-preview v-else-if="fileType === 'csv'" :show-card="false" :file-url="props.file.url || ''" :max-rows="20" class="size-full min-h-12" @error="emit('error', $event)" />

      <!-- Archive Files -->
      <zip-file-preview
        v-else-if="fileType === 'zip'"
        :file="zipFile"
        :show-close-button="false"
        :show-reset="false"
        class="size-full min-h-12"
      />

      <!-- Image Preview -->
      <image-preview
        v-else-if="fileType === 'image'" class="size-full"
        :src="props.file.url || undefined"
        :alt="fileName"
        @download="handleImageDownload"
        @resize="handleSetContainer"
      />

      <!-- Other File Types Preview Content -->
      <template v-else>
        <!-- Loading State -->
        <div v-if="loading" class="h-64 flex items-center justify-center">
          <n-spin>
            <template #description>
              Loading preview...
            </template>
          </n-spin>
        </div>

        <!-- Error State -->
        <div v-else-if="error" class="h-64 flex flex-col items-center justify-center text-red-500">
          <n-icon size="48" class="mb-4">
            <icon-ion-warning-outline />
          </n-icon>
          <p class="mb-2 text-lg font-medium">
            Preview Error
          </p>
          <p class="text-sm text-gray-500">
            {{ error }}
          </p>
        </div>

        <!-- Video Preview -->
        <div v-else-if="fileType === 'video'" class="video-preview">
          <video
            :src="props.file.url || undefined"
            controls
            class="mx-auto h-auto max-w-full rounded-lg shadow-lg"
            @loadedmetadata="handleVideoLoad"
            @error="handleVideoError"
          >
            Your browser does not support the video element.
          </video>
        </div>

        <!-- Audio Preview -->
        <div v-else-if="fileType === 'audio'" class="audio-preview flex items-center justify-center">
          <div class="max-w-md w-full">
            <div class="mb-4 text-center">
              <n-icon size="64" class="text-blue-500">
                <icon-ion-musical-notes-outline />
              </n-icon>
            </div>
            <audio
              :src="props.file.url || undefined"
              controls
              class="w-full"
              @loadedmetadata="handleAudioLoad"
              @error="handleAudioError"
            >
              Your browser does not support the audio element.
            </audio>
          </div>
        </div>

        <!-- Binary/Executable Files -->
        <div v-else-if="fileType === 'exe'" class="executable-preview h-64 flex flex-col items-center justify-center">
          <n-icon size="64" class="mb-4 text-red-500">
            <icon-ion-code-working />
          </n-icon>
          <p class="mb-2 text-lg font-medium">
            Executable File
          </p>
          <p class="mb-4 text-sm text-gray-500">
            Binary executable file
          </p>
          <n-button @click="handleDownload">
            <template #icon>
              <n-icon><icon-ion-download-outline /></n-icon>
            </template>
            Download File
          </n-button>
        </div>

        <!-- Office Documents -->
        <div v-else-if="['word', 'excel', 'ppt'].includes(fileType)" class="office-preview h-64 flex flex-col items-center justify-center">
          <n-icon size="64" class="mb-4" :class="getOfficeIconColor(fileType)">
            <component :is="getOfficeIcon(fileType)" />
          </n-icon>
          <p class="mb-2 text-lg font-medium">
            {{ getOfficeTypeName(fileType) }} Document
          </p>
          <p class="mb-4 text-sm text-gray-500">
            Preview not available in browser
          </p>
          <div class="flex gap-2">
            <n-button @click="handleDownload">
              <template #icon>
                <n-icon><icon-ion-download-outline /></n-icon>
              </template>
              Download
            </n-button>
            <n-button secondary @click="handleOpenExternal">
              <template #icon>
                <n-icon><icon-ion-open-outline /></n-icon>
              </template>
              Open Externally
            </n-button>
          </div>
        </div>

        <!-- Unknown/Unsupported Files -->
        <div v-else class="unknown-preview h-full min-h-fit flex flex-col items-center justify-center">
          <n-icon size="64" class="mb-4 text-gray-400">
            <icon-ion-document-outline />
          </n-icon>
          <p class="mb-2 text-lg font-medium">
            File Preview
          </p>
          <p class="mb-4 text-sm text-gray-500">
            Preview not available for this file type
          </p>
        </div>
      </template>
    </template>
  </n-card>
</template>

<script setup lang="ts">
import { useLoading } from "@airalogy/composables"
import { getFileInfo, getFileSpecificIcon, type IFileType } from "@airalogy/shared/utils"
import IconIonBarChart from "~icons/ion/bar-chart"

import IconIonChevronDownOutline from "~icons/ion/chevron-down-outline"
import IconIonCodeWorking from "~icons/ion/code-working"
import IconIonDocumentOutline from "~icons/ion/document-outline"
import { NButton, NCard, NIcon, NSpin, NTag, type UploadFileInfo } from "naive-ui"
import { computed, onMounted, ref, watch } from "vue"
import CopyToClip from "../copy-to-clip.vue"
import CsvPreview from "./csv-preview.vue"
import ImagePreview from "./image-preview/index.vue"
import PdfViewer from "./pdf-preview/index.vue"
import ZipFilePreview from "./zip-file-preview.vue"

// Icons
import IconIonDownloadOutline from "~icons/ion/download-outline"
import IconIonEyeOutline from "~icons/ion/eye-outline"
import IconIonMusicalNotesOutline from "~icons/ion/musical-notes-outline"

import IconIonOpenOutline from "~icons/ion/open-outline"
import IconIonTrashOutline from "~icons/ion/trash-outline"
import IconIonWarningOutline from "~icons/ion/warning-outline"
// Office icons (these would need to be imported based on your icon setup)
import IconIonDocument from "~icons/ion/document"
import IconIonGrid from "~icons/ion/grid"

export interface IProps {
  file: UploadFileInfo & { airalogy_file_id?: string }
  canEdit?: boolean
  showPreview?: boolean
  contentClass?: string
  bordered?: boolean
}

const props = withDefaults(defineProps<IProps>(), {
  canEdit: true,
  showPreview: false,
  bordered: false,
})

const emit = defineEmits<Emits>()

interface Emits {
  (e: "preview", file: UploadFileInfo): void
  (e: "remove", file: UploadFileInfo): void
  (e: "openAsText", file: UploadFileInfo): void
  (e: "error", value: string): void
}

const { loading, startLoading, endLoading } = useLoading()
const error = ref<string>("")
const zipFile = ref<File | null>(null)
const collapsed = ref(true)

const fileName = computed(() => props.file.name || `file.${props.file.type}`)
const fileType = computed(() => props.file.type || getFileInfo(fileName.value).type as IFileType)

const fileIcon = computed(() => getFileSpecificIcon(fileName.value))
const downloadUrl = computed(() => props.file.url)

const canOpenAsText = computed(() => {
  // Allow opening unknown files as text if they might be text-based
  return ["csv", "file"].includes(fileType.value)
})

const browserSupportedTypes = ["pdf", "image", "video", "audio"]
const canOpenInBrowser = computed(() => {
  // File types that browsers can display directly
  return browserSupportedTypes.includes(fileType.value)
})

const contentStyle = ref<Record<string, string>>({})
function handleSetContainer(size: { width: number, height: number }) {
  const { height } = size
  if (height) {
    contentStyle.value.height = `${height}px`
  }
}
function formatFileSize(bytes: number): string {
  if (bytes === 0)
    return "0 Bytes"

  const k = 1024
  const sizes = ["Bytes", "KB", "MB", "GB", "TB"]
  const i = Math.floor(Math.log(bytes) / Math.log(k))

  return `${Number.parseFloat((bytes / k ** i).toFixed(2))} ${sizes[i]}`
}

function getOfficeIcon(type: string) {
  switch (type) {
    case "word": return IconIonDocument
    case "excel": return IconIonGrid
    case "ppt": return IconIonBarChart
    default: return IconIonDocument
  }
}

function getOfficeIconColor(type: string): string {
  switch (type) {
    case "word": return "text-blue-500"
    case "excel": return "text-green-500"
    case "ppt": return "text-orange-500"
    default: return "text-gray-500"
  }
}

function getOfficeTypeName(type: string): string {
  switch (type) {
    case "word": return "Word"
    case "excel": return "Excel"
    case "ppt": return "PowerPoint"
    default: return "Office"
  }
}

function handleDownload() {
  if (downloadUrl.value) {
    const link = document.createElement("a")
    link.href = downloadUrl.value
    link.download = fileName.value
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }
}

function handleOpenExternal() {
  if (downloadUrl.value) {
    window.open(downloadUrl.value, "_blank")
  }
}

function handleOpenAsText() {
  emit("openAsText", props.file)
}

function handleImageLoad() {
  loading.value = false
  error.value = ""
}

function handleImageError() {
  loading.value = false
  error.value = "Failed to load image"
}

function handleVideoLoad() {
  loading.value = false
  error.value = ""
}

function handleVideoError() {
  loading.value = false
  error.value = "Failed to load video"
}

function handleAudioLoad() {
  loading.value = false
  error.value = ""
}

function handleAudioError() {
  loading.value = false
  error.value = "Failed to load audio"
}

function handlePreview() {
  emit("preview", props.file)
}

function handleRemove() {
  emit("remove", props.file)
}

function handleToggleCollapse() {
  collapsed.value = !collapsed.value
}

function handleImageDownload(src: string) {
  const link = document.createElement("a")
  link.href = src
  link.download = fileName.value
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

async function fetchZipFile() {
  if (fileType.value === "zip" && props.file.url) {
    try {
      loading.value = true
      const response = await fetch(props.file.url)
      const blob = await response.blob()
      zipFile.value = new File([blob], fileName.value, { type: "application/zip" })
    }
    catch (err) {
      error.value = "Failed to load zip file"
      console.error("Zip file loading error:", err)
    }
    finally {
      loading.value = false
    }
  }
}

const fileSize = computed(() => {
  const { file } = props.file
  if (file && file.size) {
    return formatFileSize(file.size)
  }

  return ""
})

watch(() => props.file, (file) => {
  if (!file) {
    return
  }

  const { status } = file
  if (status === "error") {
    error.value = "Failed to load file"
    endLoading()
  }
})

onMounted(() => {
  startLoading()
  // Fetch zip file if needed
  if (fileType.value === "zip") {
    fetchZipFile()
  }
  else {
    // Simulate loading time for preview setup
    setTimeout(() => {
      if (!error.value) {
        endLoading()
      }
    }, 500)
  }
})

// Watch for changes in fileUrl to refetch zip file
watch(() => [props.file.url, fileType.value], () => {
  if (fileType.value === "zip") {
    fetchZipFile()
  }
})
</script>

<style scoped lang="sass">
.video-preview video
  max-height: 70vh

.pdf-preview object
  border: 1px solid var(--n-border-color)
</style>
