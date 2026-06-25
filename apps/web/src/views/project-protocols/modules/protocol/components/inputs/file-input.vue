<template>
  <div>
    <!-- Image type: existing file - show custom preview card -->
    <div v-if="isImageType && currentFile" class="file-card image-file-card">
      <div class="file-card__header">
        <file-type-icon :type="fileType || 'file'" :size="20" class="file-card__icon" />
        <span class="file-card__name" :title="currentFile.name">{{ currentFile.name }}</span>
        <n-tag size="small" type="info" class="file-card__type">
          {{ fileType?.toUpperCase() || $t("common.file") }}
        </n-tag>
      </div>
      <div class="file-card__actions">
        <n-button
          text
          type="error"
          size="small"
          @click="handleRemove"
        >
          <template #icon>
            <n-icon><icon-delete /></n-icon>
          </template>
          {{ $t("common.delete") }}
        </n-button>
        <n-button
          text
          type="primary"
          size="small"
          @click="handleDownload(currentFile)"
        >
          <template #icon>
            <n-icon><icon-download /></n-icon>
          </template>
          {{ $t("common.download") }}
        </n-button>
        <n-button
          v-if="currentFile.url"
          text
          size="small"
          @click="handleOpenInTab(currentFile)"
        >
          <template #icon>
            <n-icon><icon-open /></n-icon>
          </template>
          Open in Tab
        </n-button>
      </div>
      <div class="image-file-card__preview" @click="handlePreview(currentFile)">
        <img
          v-if="currentFile.url"
          :src="currentFile.url"
          :alt="currentFile.name"
          class="image-file-card__image"
        >
      </div>

      <n-modal
        v-model:show="showImagePreview"
        preset="card"
        :title="previewImageName"
        class="max-w-90vw"
        :bordered="false"
        size="huge"
      >
        <div class="flex items-center justify-center">
          <img :src="previewImageUrl" :alt="previewImageName" class="max-h-70vh max-w-full">
        </div>
      </n-modal>
    </div>

    <!-- Image type: no file - show uploader -->
    <form-upload-file
      v-else-if="isImageType"
      :ref="handleUploadRef"
      v-bind="{ ...uploadCommonProps, ...componentProps }"
      :file-list="targetFileList"
      :input-type="rawType"
      :show-trigger="targetFileList.length < (componentProps.max || 1)"
      class="w-full" :class="[isTableContext ? 'table-file-upload' : 'image-file-upload']"
      @update:file="options => handleFileChange(scopeName, prop, options, props.info)"
      @uploaded:file="(attachmentInfo, fileInfo) => handleUploadFile({ scope: scopeName, prop, type: model.type, fileInfo, attachmentInfo, info, assigner, dependent })"
    />

    <!-- Non-image: Has file - show file card -->
    <div v-else-if="currentFile" class="file-card">
      <div class="file-card__header">
        <file-type-icon :type="fileType || 'file'" :size="20" class="file-card__icon" />
        <span class="file-card__name" :title="currentFile.name">{{ currentFile.name }}</span>
        <n-tag size="small" type="info" class="file-card__type">
          {{ fileType?.toUpperCase() || $t("common.file") }}
        </n-tag>
      </div>
      <div class="file-card__actions">
        <n-button
          v-if="fileType === 'csv' || fileType === 'pdf'"
          text
          size="small"
          @click="handlePreviewClick"
        >
          <template #icon>
            <n-icon><icon-preview /></n-icon>
          </template>
          {{ $t("common.preview") }}
        </n-button>
        <n-button
          text
          type="primary"
          size="small"
          @click="handleDownload(currentFile)"
        >
          <template #icon>
            <n-icon><icon-download /></n-icon>
          </template>
          {{ $t("common.download") }}
        </n-button>
        <n-button
          text
          type="error"
          size="small"
          @click="handleRemove"
        >
          <template #icon>
            <n-icon><icon-delete /></n-icon>
          </template>
          {{ $t("common.delete") }}
        </n-button>
      </div>

      <!-- Modals inside file-card -->
      <n-modal
        v-if="fileType === 'csv'"
        v-model:show="showCsvPreview"
        preset="card"
        :title="currentFile?.name || $t('common.csvPreview')"
        class="max-w-90vw"
        :bordered="false"
        size="huge"
        aria-modal="true"
      >
        <csv-preview
          :file-url="currentFile?.url || undefined"
          :show-card="false"
          :show-actions="true"
          class="h-70vh"
        />
      </n-modal>

      <n-modal
        v-if="fileType === 'pdf'"
        v-model:show="showPdfPreview"
        preset="card"
        :title="currentFile?.name || $t('common.pdfPreview')"
        class="max-w-90vw"
        :bordered="false"
        size="huge"
        aria-modal="true"
      >
        <iframe
          v-if="currentFile?.url"
          :src="currentFile.url"
          class="h-70vh w-full"
          type="application/pdf"
        />
      </n-modal>

      <n-modal
        v-model:show="showImagePreview"
        preset="card"
        :title="previewImageName"
        class="max-w-90vw"
        :bordered="false"
        size="huge"
      >
        <div class="flex items-center justify-center">
          <img :src="previewImageUrl" :alt="previewImageName" class="max-h-70vh max-w-full">
        </div>
      </n-modal>
    </div>

    <!-- Non-image: No file - show upload button -->
    <n-button
      v-else
      size="small"
      class="upload-btn"
      @click="triggerUpload"
    >
      <template #icon>
        <file-type-icon v-if="fileType && fileType !== 'file'" :type="fileType" :size="16" />
      </template>
      {{ $t("common.upload") }}
    </n-button>

    <!-- Hidden upload component (position absolute to not affect layout) -->
    <div v-if="!isImageType" class="hidden-upload">
      <form-upload-file
        :ref="handleUploadRef"
        v-bind="{ ...uploadCommonProps, ...componentProps }"
        :file-list="targetFileList"
        :input-type="rawType"
        :show-trigger="true"
        @update:file="options => handleFileChange(scopeName, prop, options, props.info)"
        @uploaded:file="(attachmentInfo, fileInfo) => handleUploadFile({ scope: scopeName, prop, type: model.type, fileInfo, attachmentInfo, info, assigner, dependent })"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { IProps as IUploadFileProps } from "@/components/common/form-upload-file.vue"
import type { UploadFileInfo, UploadProps } from "naive-ui"
import type { ComponentPublicInstance } from "vue"
import type { InputPropsOptions } from "../../types/input-props"
import FormUploadFile from "@/components/common/form-upload-file.vue"
import { getCachedAttachment } from "@/service/api/attachments"
import { FileTypeIcon } from "@airalogy/components"
import CsvPreview from "@airalogy/components/file-preview/csv-preview.vue"
import { getBaseUploadProps, getFileExtensionFromBasename, getFileType, getMIMEByExtension, type IFileType } from "@airalogy/shared/utils"
import IconDownload from "~icons/ion/download-outline"
import IconPreview from "~icons/ion/eye-outline"
import IconOpen from "~icons/ion/open-outline"
import IconDelete from "~icons/ion/trash-outline"
import { get as _get } from "lodash-es"
import { useInputProps } from "../../composables/useInputProps"

const props = defineProps<InputPropsOptions>()

const { model, scope: scopeName, prop, assigner, dependent, info, ajvInfo } = toRefs(props)

const id = ref<string | null>(null)
const uploadRef = ref<InstanceType<typeof FormUploadFile> | null>(null)
const rawType = computed(() => model.value.type)

function normalizeFileType(type: unknown): IFileType | undefined {
  if (typeof type !== "string" || !type) {
    return undefined
  }

  const knownTypes: IFileType[] = [
    "image",
    "video",
    "pdf",
    "word",
    "excel",
    "ppt",
    "zip",
    "audio",
    "exe",
    "csv",
    "code",
    "text",
    "file",
    "unknown",
  ]

  if (knownTypes.includes(type as IFileType)) {
    return type as IFileType
  }

  return getFileType(`file.${type}`)
}

const fileType = computed(() => normalizeFileType(rawType.value))

function triggerUpload() {
  uploadRef.value?.uploadRef?.openOpenFileDialog?.()
}

const { commonProps, imageFileList, imageFileListRecord, previewFileRecord, handleFileChange, handleUploadFile, createThumbnailUrl, handlePreviewFile, handleRef, protocolId } = useInputProps(props)

function handleUploadRef(el: Element | ComponentPublicInstance | null) {
  const instance = el as InstanceType<typeof FormUploadFile> | null
  uploadRef.value = instance
  handleRef(`${scopeName.value}_${prop.value}`, instance, true)
}

const uploadCommonProps = computed(() => {
  const { ref, ...rest } = commonProps.value
  return rest
})

const fileInfo = computed(() => id.value ? previewFileRecord.value[id.value] : null)

const acceptType = computed(() => {
  const { file_extension } = ajvInfo.value?.schema || {}
  if (file_extension) {
    return file_extension.startsWith(".") ? file_extension : `.${file_extension}`
  }

  return getBaseUploadProps(rawType.value)
})

const targetFileList = computed(() => {
  const result = info?.value?.group
    ? imageFileListRecord.value[`${info.value.group}_${info.value.row}_${info.value.col}_${prop.value}`] || []
    : imageFileList.value

  return result
})

// Check if we have a non-image file
const isImageType = computed(() => fileType.value === "image")
const isTableContext = computed(() => info?.value?.group !== undefined && info?.value?.row !== undefined)
const hasNonImageFile = computed(() => !isImageType.value && targetFileList.value.length > 0)
const currentFile = computed(() => {
  const file = targetFileList.value[0] as UploadFileInfo | undefined
  return file
})
const isDisabled = computed(() => commonProps.value.disabled || model.value?.disabled)

const componentProps = computed((): IUploadFileProps & Partial<UploadProps> => {
  const hasFiles = targetFileList.value.length > 0

  return {
    endpoint: "/airalogy_files",
    uploadProps: {
      accept: acceptType.value,
      triggerClass: targetFileList.value.length === 0 ? "mt-2" : undefined,
      shouldUseThumbnailUrl: (file: Required<UploadFileInfo>) => isImageType.value,
    },
    listType: hasFiles && isImageType.value ? "image-card" : "text",
    createThumbnailUrl: fileType.value === "image" ? createThumbnailUrl : undefined,
    max: 1,
    showTrigger: !isDisabled.value && targetFileList.value.length === 0,
    defaultUpload: true,
    showDownloadButton: true,
    showRemoveButton: true,
    showPreview: true,
    protocolId: protocolId.value,
    onDownload: handleDownload,
    onPreview: handlePreview,
  }
})

// Preview states
const showImagePreview = ref(false)
const showCsvPreview = ref(false)
const showPdfPreview = ref(false)
const previewImageUrl = ref("")
const previewImageName = ref("")

function handlePreviewClick() {
  if (fileType.value === "csv") {
    showCsvPreview.value = true
  }
  else if (fileType.value === "pdf") {
    showPdfPreview.value = true
  }
}

function handleRemove() {
  // Emit file change with removed status
  if (currentFile.value) {
    const removedFile = { ...currentFile.value, status: "removed" as const }
    handleFileChange(scopeName.value, prop.value, { file: removedFile, fileList: [] }, info?.value)
  }
}

function handleDownload(file: UploadFileInfo) {
  if (file.url) {
    const link = document.createElement("a")
    link.href = file.url
    link.download = file.name || "download"
    link.target = "_blank"
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }
}

function handleOpenInTab(file: UploadFileInfo) {
  if (file.url) {
    window.open(file.url, "_blank")
  }
}

function handlePreview(file: UploadFileInfo) {
  // For images, show preview modal
  if (fileType.value === "image" && file.url) {
    previewImageUrl.value = file.url
    previewImageName.value = file.name || "Image Preview"
    showImagePreview.value = true
  }
  // For CSV/PDF, call the original preview handler
  else if ((fileType.value === "csv" || fileType.value === "pdf") && id.value) {
    handlePreviewFile(id.value, file as any)
  }
  // Default: open URL in new tab
  else if (file.url) {
    window.open(file.url, "_blank")
  }
}

watchEffect(async () => {
  const { scope, prop, info } = props
  const modelValue = props.model.value

  // Handle both object format and string format (Airalogy file ID)
  let fileAiralogyId: string | undefined
  let fileId: string | undefined

  if (typeof modelValue === "string" && modelValue.startsWith("airalogy.id.file.")) {
    // Direct Airalogy file ID string
    fileAiralogyId = modelValue
  }
  else if (typeof modelValue === "object" && modelValue) {
    // Object with airalogy_file_id or id field
    fileAiralogyId = _get(modelValue, ["airalogy_file_id"])
    fileId = _get(modelValue, ["id"])
  }

  const existingFile = targetFileList.value.find(file =>
    (file as any).airalogy_file_id === fileAiralogyId || (file as any).id === fileId,
  )

  if (!fileAiralogyId || existingFile) {
    return
  }

  const data = await getCachedAttachment(fileAiralogyId)
  if (!data) {
    return
  }

  const { filename, url, airalogy_file_id } = data
  const mime = getMIMEByExtension(getFileExtensionFromBasename(filename) || "")
  const fileInfoData: UploadFileInfo & { airalogy_file_id: string, thumbnailUrl?: string } = {
    status: "finished",
    url,
    thumbnailUrl: url,
    id: fileId || airalogy_file_id,
    name: filename,
    airalogy_file_id,
    type: mime,
  }

  handleFileChange(scope, prop, { file: fileInfoData, fileList: [fileInfoData] }, info)
})
</script>

<style scoped lang="sass">
.upload-btn
  flex-shrink: 0

.hidden-upload
  position: absolute
  width: 0
  height: 0
  overflow: hidden
  opacity: 0
  pointer-events: none

.file-card
  display: flex
  flex-direction: column
  gap: 8px
  padding: 12px
  border: 1px solid #e8e8ec
  border-radius: 8px
  background-color: #f8f8fa
  transition: all 0.2s ease
  width: 100%

  &:hover
    border-color: #d0d0d6
    background-color: #f0f0f4

.file-card__header
  display: flex
  align-items: center
  gap: 8px

.file-card__icon
  flex-shrink: 0
  color: #666

.file-card__name
  flex: 1
  font-size: 14px
  font-weight: 500
  color: #333
  overflow: hidden
  text-overflow: ellipsis
  white-space: nowrap

.file-card__type
  flex-shrink: 0

.file-card__actions
  display: flex
  align-items: center
  gap: 12px
  padding-top: 8px
  border-top: 1px solid #e8e8ec

.image-file-card__preview
  display: flex
  align-items: center
  justify-content: center
  min-height: 220px
  padding: 12px
  border-top: 1px solid #e8e8ec
  cursor: zoom-in

.image-file-card__image
  display: block
  max-width: 100%
  max-height: 420px
  width: auto
  height: auto
  object-fit: contain
</style>
