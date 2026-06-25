<template>
  <div
    ref="filePreviewRef"
    class="file-preview"
    :style="{ height: typeof props.height === 'number' ? `${props.height}px` : props.height }"
  >
    <n-spin :show="isLoading" size="medium" class="size-full">
      <!-- ZIP Content Preview -->
      <template v-if="zipContent.items.length">
        <div class="mb-4 flex items-center justify-between">
          <slot name="breadcrumb" :current-path="currentPath" :navigate-to="navigateTo">
            <n-breadcrumb>
              <n-breadcrumb-item @click="navigateTo(-1)">
                File Preview
              </n-breadcrumb-item>
              <n-breadcrumb-item
                v-for="(part, index) in currentPath"
                :key="index"
                @click="navigateTo(index)"
              >
                {{ part || 'Root' }}
              </n-breadcrumb-item>
            </n-breadcrumb>
          </slot>

          <slot name="reset-button">
            <n-button v-if="fileModel && props.showReset" size="small" type="primary" @click="reset">
              <template #icon>
                <n-icon><icon-tabler-reload /></n-icon>
              </template>
              Re-upload
            </n-button>
          </slot>
          <slot v-if="props.showCloseButton !== false" name="close-button">
            <n-button text type="error" @click="handleClose">
              <template #icon>
                <n-icon><close-outline /></n-icon>
              </template>
              Close
            </n-button>
          </slot>
        </div>

        <!-- File List -->
        <n-scrollbar style="max-height: 400px">
          <n-list hoverable clickable>
            <!-- List Header -->
            <n-list-item class="bg-gray-50">
              <div class="grid grid-cols-12 w-full gap-4">
                <div class="col-span-6">
                  Name
                </div>
                <div class="col-span-2 text-right">
                  Size
                </div>
                <div class="col-span-4 text-right">
                  Last Modified
                </div>
              </div>
            </n-list-item>

            <!-- List Items -->
            <n-list-item
              v-for="item in currentDirContent"
              :key="item.path"
              @click="handleItemClick(item)"
            >
              <div class="grid grid-cols-12 w-full gap-4">
                <div class="col-span-6 flex items-center gap-2">
                  <n-icon size="20">
                    <template v-if="item.isDirectory">
                      <folder-outline />
                    </template>
                    <template v-else>
                      <document-outline />
                    </template>
                  </n-icon>
                  <span class="truncate">{{ item.name }}</span>
                </div>
                <div class="col-span-2 text-right text-sm text-gray-500">
                  {{ !item.isDirectory ? formatFileSize(item.size) : '--' }}
                </div>
                <div class="col-span-4 text-right text-sm text-gray-500">
                  {{ item.lastModified ? formatDate(item.lastModified) : '--' }}
                </div>
              </div>
            </n-list-item>
          </n-list>
        </n-scrollbar>

        <!-- File Content Preview -->
        <div v-if="selectedFile" class="mt-4">
          <div class="mb-2 flex items-center justify-between">
            <span class="text-lg font-medium">{{ selectedFile.name }}</span>
            <n-button text type="primary" size="small" @click="selectedFile = null">
              <template #icon>
                <n-icon><close-outline /></n-icon>
              </template>
              Close Preview
            </n-button>
          </div>
          <shiki-protocol-viewer
            v-if="isProtocolFile"
            :content="fileContent[selectedFile.path] || ''"
            :error-lines="errorLines"
          />
          <csv-preview
            v-else-if="isCsvFile"
            :content="fileContent[selectedFile.path] || ''"
            :show-card="false"
            class="h-auto max-w-full"
          />
          <shiki-code-viewer
            v-else-if="isTextFile"
            :code="fileContent[selectedFile.path] || ''"
            :language="getFileLanguage(selectedFile.name)"
          />
          <img
            v-else-if="isImageFile"
            :src="fileContent[selectedFile.path] || ''"
            :alt="selectedFile.name"
            class="h-auto max-w-full"
          >
          <div v-else class="py-4 text-center text-gray-500">
            Preview not available for this file type
          </div>
        </div>
      </template>

      <!-- Upload Area -->
      <slot v-else name="upload-area" :handle-file-change="handleFileListUpdate">
        <n-upload
          ref="uploadRef"
          :show-file-list="false"
          multiple
          @update:file-list="handleFileListUpdate"
          @before-upload="handleBeforeUpload"
        >
          <n-upload-dragger class="upload-area">
            <slot name="upload-icon">
              <n-icon size="48" class="mb-2">
                <archive-outline />
              </n-icon>
            </slot>
            <slot name="upload-text">
              <p class="text-base">
                Click or drag directory here
              </p>
              <p class="text-sm text-gray-500">
                Support for directory upload and ZIP archives
              </p>
            </slot>
          </n-upload-dragger>
        </n-upload>
      </slot>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import type { UploadFileInfo, UploadInst } from "naive-ui"
import type { UploadContent } from "../monaco-editor/types/upload"
import CsvPreview from "@airalogy/components/file-preview/csv-preview.vue"
import { useClosableMessage, useFileType, useFileUtils, useZipContent } from "@airalogy/composables"
import { formatDate as formatDateBase, getFileLanguage } from "@airalogy/shared/utils"
import { useVModel } from "@vueuse/core"
import ArchiveOutline from "~icons/ion/archive-outline"
import CloseOutline from "~icons/ion/close-outline"
import DocumentOutline from "~icons/ion/document-outline"
import FolderOutline from "~icons/ion/folder-outline"
// import { ReloadOutline } from "~icons/ion/reload-outline"
import ShikiCodeViewer from "./code-preview/shiki-code-viewer.vue"
import ShikiProtocolViewer from "./code-preview/shiki-protocol-viewer.vue"

interface IProps {
  height?: string | number
  acceptedFileTypes?: string
  maxFileSize?: number
  showCloseButton?: boolean
  showReset?: boolean
  file?: File | null
  fileContent?: Record<string, string> | { files: Array<{
    name: string
    path: string
    file: File
    size?: number
    lastModified?: number
  }> } | null | string
}

interface IEmits {
  (e: "selected:file", file: File | null): void
  (e: "loaded:content", content: UploadContent | null): void
  (e: "closed:preview"): void
  (e: "update:file", value: File | null): void
  (e: "update:fileContent", value: string | null): void
}

const props = defineProps<IProps>()
const emit = defineEmits<IEmits>()

const message = useClosableMessage()

// Two-way binding for file and fileContent
const fileModel = useVModel(props, "file", emit)
const fileContentModel = useVModel(props, "fileContent", emit)

const {
  isLoading,
  zipContent,
  currentPath,
  selectedFile,
  fileContent,
  envFiles,
  currentDirContent,
  navigateTo,
  handleItemClick,
  resetPreview,
  handleFileChange: innerHandleFileChange,
} = useZipContent()

const errorLines = ref<number[]>([])

const { isTextFile, isImageFile, isProtocolFile, isCsvFile } = useFileType(selectedFile)
const { formatFileSize } = useFileUtils()

const filePreviewRef = ref<HTMLDivElement | null>(null)
// Add upload ref
const uploadRef = ref<UploadInst | null>(null)

// Add new ref for max upload limit
const maxUploadLimit = ref<number | undefined>(undefined)

function handleClose() {
  resetPreview()
  fileModel.value = null
  fileContentModel.value = null
  emit("closed:preview")
}

// Add the handleFileListUpdate function
async function handleFileListUpdate(fileList: UploadFileInfo[]) {
  if (!fileList.length)
    return

  const firstFile = fileList[0]

  try {
    // Check if it's a directory upload first
    if (fileList.length > 1 || firstFile.fullPath?.endsWith("/")) {
      // Handle directory upload
      const files = fileList.map(f => ({
        name: f.name,
        path: f.fullPath || f.name,
        file: f.file as File,
        size: f.file?.size,
        lastModified: f.file?.lastModified,
      }))

      fileModel.value = null
      fileContentModel.value = { files }
      emit("selected:file", null)
      emit("loaded:content", { type: "directory", files, updated: false })
      return
    }

    // Handle ZIP file
    const uploadedFile = firstFile.file as File
    if (!uploadedFile)
      return

    fileModel.value = uploadedFile
    emit("selected:file", uploadedFile)
    await innerHandleFileChange({
      file: firstFile,
      fileList,
    })
    fileContentModel.value = fileContent.value
    emit("loaded:content", { type: "zip", content: zipContent.value, updated: false })
  }
  catch (error) {
    message.error((error as Error).message)
    reset()
  }
}

function formatDate(date: Date | number | undefined) {
  if (!date)
    return "--"
  return formatDateBase(date, "date-time-minute")
}

// Update the handleBeforeUpload function
async function handleBeforeUpload({ file, fileList }: { file: UploadFileInfo, fileList: UploadFileInfo[] }): Promise<boolean> {
  const uploadedFile = file.file as File
  if (!uploadedFile)
    return false

  if (props.maxFileSize && uploadedFile.size > props.maxFileSize * 1024 * 1024) {
    message.error(`File size exceeds ${props.maxFileSize}MB limit`)
    return false
  }

  // Check if it's a directory upload or ZIP file
  const isZip = uploadedFile.name.endsWith(".zip")
  const isDirectory = file.fullPath?.includes("/")

  if (!isZip && !isDirectory) {
    message.error("Please upload either a directory or a ZIP file")
    return false
  }

  return true
}

// Update reset function to clear upload instance
function reset() {
  fileModel.value = null
  fileContentModel.value = null
  maxUploadLimit.value = undefined
  errorLines.value = []
  resetPreview()

  // Clear upload instance
  if (uploadRef.value)
    uploadRef.value.clear()

  emit("selected:file", null)
  emit("loaded:content", null)
}

function highlightLine(line: number) {
  if (!errorLines.value.includes(line)) {
    errorLines.value.push(line)
  }
}

async function openPreview(fileName?: string) {
  // If a fileName is provided, check if it matches the current file
  if (fileName) {
    // Find the file in zipContent or current directory
    const file = zipContent.value.items.find(f => f.name === fileName)
    if (!file) {
      return
    }
    // Handle the file click to show its preview
    await handleItemClick(file)
  }

  await nextTick()

  // Find the preview content element and scroll to it
  if (selectedFile.value) {
    const previewElement = filePreviewRef.value?.querySelector(".shiki-viewer")
    previewElement?.scrollIntoView({ behavior: "smooth", block: "start" })
  }
}

// Expose methods for parent components
defineExpose({
  openPreview,
  highlightLine,
  envFiles,
})
</script>

<style lang="sass" scoped>
@use "@styles/sass/drag-area" as *

.file-preview
  width: 100%
  min-height: 200px
.preview-card
  max-height: 500px
  overflow: auto

:deep(.n-list-item)
  height: 48px!important
</style>
