<template>
  <div v-if="fileType === 'image' && currentFile" class="file-card image-file-card">
    <div class="file-card__header">
      <file-type-icon :type="fileType" :size="20" class="file-card__icon" />
      <span class="file-card__name" :title="currentFile.name">{{ currentFile.name }}</span>
      <n-tag size="small" type="info" class="file-card__type">
        {{ fileType.toUpperCase() }}
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

  <form-upload-file
    v-else
    v-bind="uploadProps"
    :ref="(el: any) => handleRef(`${props.scope}_${props.prop}`, el, props.type, {}, true)"
    :info="props.info"
    :file-type="fileType"
    :any-of-schemas="anyOfSchemas"
    :show-preview-button="false"
    :show-remove-button="false"
    :show-download-button="false"
    @update:file="fileInfo => handleFileChange({ scope: props.scope, prop: props.prop, fileInfo, id: props.id, info: props.info })"
    @uploaded:file="(file, rawFile) => handleUploadFile({ scope: props.scope, prop: props.prop, type: props.type, file, rawFile, assigner: props.assigner, dependent: props.dependent, info: props.info })"
    @renamed:file="file => handleRename(props.scope, props.prop, file, props.info)"
    @schema-change="handleSchemaChange"
  >
    <template
      v-if="(fileType === 'csv' || fileType === 'pdf')
        && (previewFileRecord[props.id]?.file || previewFileRecord[props.id]?.content)" #preview
    >
      <n-modal
        v-model:show="previewFileRecord[props.id].visible" preset="card" :title="props.info?.name" class="max-w-90vw"
        :bordered="false" size="huge" aria-modal="true"
      >
        <csv-preview
          v-if="fileType === 'csv'" :file="previewFileRecord[props.id].file"
          :content="previewFileRecord[props.id].content" :show-card="false" :show-actions="true" class="h-70vh"
        />
        <object
          v-else-if="fileType === 'pdf' && previewFileRecord[props.id]?.url"
          :data="previewFileRecord[props.id].url!" type="application/pdf" width="100%" height="100%" class="h-70vh w-full"
        >
          <p>
            {{ $t("common.pdfNotSupported") }}
            <a :href="previewFileRecord[props.id].url!">{{ $t("common.downloadPdf") }}</a>
          </p>
        </object>
      </n-modal>
    </template>
  </form-upload-file>
</template>

<script setup lang="ts">
import type { IFileType } from "@airalogy/shared/utils"
import type { UploadFileInfo } from "naive-ui"
import type { JsonSchema } from "../../types/aimd-types"
import type { IAIMDInputProps } from "../../types/props"
import { getCachedAttachment } from "@/service/api/attachments"
import { FileTypeIcon } from "@airalogy/components"
import CsvPreview from "@airalogy/components/file-preview/csv-preview.vue"
import { getFileExtensionFromBasename, getMIMEByExtension } from "@airalogy/shared/utils"
import IconDownload from "~icons/ion/download-outline"
import IconOpen from "~icons/ion/open-outline"
import IconDelete from "~icons/ion/trash-outline"
import { useInputProps } from "../../composables/useInputProps"

const props = defineProps<IAIMDInputProps>()

const emit = defineEmits<IEmits>()
interface IEmits {
  (e: "schemaChange", schema: JsonSchema): void
}

const { effectiveType, uploadProps, previewFileRecord, handleFileChange, handleUploadFile, handleRename, handleRef, handleSchemaChange: innerHandleSchemaChange, anyOfSchemas } = useInputProps(props)
const fileType = computed(() => effectiveType.value as IFileType)
const currentFile = computed(() => uploadProps.value.fileList?.[0] as UploadFileInfo | undefined)
const showImagePreview = ref(false)
const previewImageUrl = ref("")
const previewImageName = ref("")

function handleSchemaChange(schema: JsonSchema) {
  innerHandleSchemaChange(schema)
  emit("schemaChange", schema)
}

function handleRemove() {
  if (!currentFile.value) {
    return
  }

  const removedFile = { ...currentFile.value, status: "removed" as const }
  handleFileChange({
    scope: props.scope,
    prop: props.prop,
    fileInfo: { file: removedFile, fileList: [] },
    id: props.id,
    info: props.info,
  })
}

function handleDownload(file: UploadFileInfo) {
  if (!file.url) {
    return
  }

  const link = document.createElement("a")
  link.href = file.url
  link.download = file.name || "download"
  link.target = "_blank"
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

function handleOpenInTab(file: UploadFileInfo) {
  if (file.url) {
    window.open(file.url, "_blank")
  }
}

function handlePreview(file: UploadFileInfo) {
  if (file.url) {
    previewImageUrl.value = file.url
    previewImageName.value = file.name || "Image Preview"
    showImagePreview.value = true
  }
}

// Handle string value (airalogy_file_id) - load file info from cache/API
watchEffect(async () => {
  const { scope, prop, model, info } = props
  const modelValue = model.value

  // Check if the value is a string (airalogy_file_id)
  let fileAiralogyId: string | undefined

  if (typeof modelValue === "string" && modelValue.startsWith("airalogy.id.file.")) {
    fileAiralogyId = modelValue
  }
  else if (typeof modelValue === "object" && modelValue?.airalogy_file_id) {
    // Already have file object, check if it needs URL
    if (modelValue.url) {
      return // Already have complete file info
    }
    fileAiralogyId = modelValue.airalogy_file_id
  }

  if (!fileAiralogyId) {
    return
  }

  // Check if file is already in the fileList
  const existingFile = uploadProps.value.fileList?.find((file: any) =>
    file.airalogy_file_id === fileAiralogyId || file.url,
  )
  if (existingFile) {
    return
  }

  // Load file info from cache/API
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
    id: airalogy_file_id,
    name: filename,
    airalogy_file_id,
    type: mime,
  }

  // Update file list through handleFileChange
  handleFileChange({
    scope,
    prop,
    fileInfo: { file: fileInfoData, fileList: [fileInfoData] },
    id: props.id,
    info,
  })
})
</script>

<style scoped lang="sass">
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
