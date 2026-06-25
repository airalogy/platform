<template>
  <n-upload
    ref="uploadRef"
    v-bind="{
      ...$attrs,
      ...props.uploadProps,
      ...computedUploadProps,
      onPreview: props.showPreview ? handlePreview : undefined,
    }"
    v-model:file-list="mergedFileList"
    :action="props.endpoint"
    :disabled="props.disabled"
    :show-preview-button="props.showPreviewButton"
    :show-remove-button="props.showRemoveButton"
    :should-use-thumbnail-url="checkShouldUseThumbnailUrl"
    :list-type="props.listType"
    :default-upload="props.defaultUpload"
    :default-file-list="defaultFileList"
    :max="props.max"
    :show-trigger="mergedFileList.length < props.max"
    :custom-request="customRequest"
    class="!max-w-50vw !min-w-fit"
    :class="{
      'upload__wrapper--show-name': showName,
      'upload__wrapper--no-actions': isNoActions,
      'upload__wrapper--has-file': mergedFileList.length > 0,
      'upload__wrapper--image-card-lg': isStandaloneImageCard,
    }"
    :style="props.maxWidth ? { maxWidth: props.maxWidth } : {}"
    :theme-overrides="themeOverrides"
    @change="handleChange"
  >
    <slot>
      <file-type-icon v-if="props.fileType" :type="props.fileType" size="24" color="var(--n-color)">
        <div class="absolute size-fit -bottom-2.5 -right-2.5">
          <n-icon v-if="props.type === 'dependent'" :component="CloudUpload" :size="14" color="#333" />
          <n-icon v-else-if="props.type === 'assigner'" :component="CloudPending" :size="14" color="#333" />
        </div>
      </file-type-icon>
      <template v-else>
        <n-icon v-if="props.type === 'dependent'" :component="CloudUpload" :size="12" />
        <n-icon v-else-if="props.type === 'assigner'" :component="CloudPending" :size="12" />
      </template>
    </slot>
  </n-upload>
  <template v-if="showName && mergedFileList.length > 0">
    <slot name="action">
      <teleport
        v-for="(file, idx) in mergedFileList"
        :key="file.id"
        :to="`#${$attrs.id} .n-upload-file-info:nth-child(${idx + 1}) .n-upload-file-info__name`"
      >
        <n-form-item
          :ref="(el: Element | ComponentPublicInstance | null) => (formItemRecord[file.id] = el)"
          :show-label="false"
          :rule="{
            trigger: ['change', 'blur'],
            required: true,
            message: fileText.nameRequired,
            validator: () => validateFileName(fileNameRecord[file.id]?.trim?.()),
          }"
        >
          <n-input-group class="items-stretch b-t-1">
            <n-input
              v-model:value="fileNameRecord[file.id]"
              class="max-w-4xl w-full b-r-1"
              size="tiny"
              autosize
              :theme-overrides="{ paddingTiny: '0', borderRadius: '0 6px', border: '0' }"
              :disabled="loading"
              :allow-input="(value: string) => !value.startsWith(' ') && !value.endsWith(' ')"
            />
            <n-button
              size="tiny"
              ghost
              :theme-overrides="{ border: '0 0', borderRadiusTiny: '6px 0' }"
              :disabled="loading"
              @click="() => handleRename(file)"
            >
              <template #icon>
                <icon-local-edit-alt />
              </template>
            </n-button>
          </n-input-group>
        </n-form-item>
      </teleport>
    </slot>
  </template>
  <slot name="preview" />
</template>

<script setup lang="ts">
import type { FormItemInst, UploadCustomRequestOptions } from "naive-ui"
import type { UploadFileInfo, UploadInst, UploadProps } from "naive-ui/es/upload"
import type { OnPreview } from "naive-ui/es/upload/src/interface"
import { useLoading } from "@/composables"
import { $t } from "@/locales"
import { putRenameAssets } from "@/service/api/project-protocols"
import { request } from "@/service/request"
import { getUploadProps } from "@/utils/fileType"
import { FileTypeIcon } from "@airalogy/components"
import { useClosableMessage } from "@airalogy/composables"
import { fileTypes, getFileType, type IFileType } from "@airalogy/shared/utils"
import CloudPending from "~icons/local/cloud-pending"
import CloudUpload from "~icons/local/cloud-upload"

import { environmentSupportFile } from "naive-ui/es/upload/src/utils"

defineOptions({ inheritAttrs: false })

const props = withDefaults(defineProps<IProps>(), {
  label: "Upload",
  defaultFileList: () => [],
  uploadProps: () => ({}),
  defaultUpload: true,
  max: 1,
  listType: "image-card",
  endpoint: "/attachments/",
  showName: false,
  showPreview: false,
  showPreviewButton: true,
  fileList: undefined,
  onPreview: undefined,
  type: undefined,
  protocolId: undefined,
  showRemoveButton: true,
  // Default event handlers
  onRemove: undefined,
  onError: undefined,
  onFinish: undefined,
  onBeforeUpload: undefined,
  onDownload: undefined,
  onExceed: undefined,
})

const emit = defineEmits<IEmits>()

const fileText = computed(() => ({
  nameRequired: $t("form.file.nameRequired"),
  nameInvalid: $t("form.file.nameInvalid"),
  nameStartsDot: $t("form.file.nameStartsDot"),
  nameMissing: $t("form.file.nameMissing"),
  typeInvalid: $t("form.file.typeInvalid"),
  validationFailed: $t("form.file.validationFailed"),
  renameSuccess: $t("form.file.renameSuccess"),
  invalidFile: $t("form.file.invalidFile"),
}))

export interface IProps {
  label?: string
  defaultFileList?: UploadFileInfo[]
  defaultUpload?: boolean
  uploadProps?: UploadProps | null
  max?: number
  listType?: UploadProps["listType"]
  endpoint?: string
  showName?: boolean
  showPreview?: boolean
  showPreviewButton?: boolean
  showRemoveButton?: boolean
  fileList?: UploadFileInfo[]
  onPreview?: OnPreview
  type?: "field" | "dependent" | "assigner"
  fileType?: IFileType
  protocolId?: string
  info?: any
  disabled?: boolean
  maxWidth?: string
  // Additional event handlers
  onRemove?: (file: UploadFileInfo) => void | boolean | Promise<boolean>
  onError?: (file: UploadFileInfo) => void
  onFinish?: (file: UploadFileInfo) => void
  onBeforeUpload?: (file: UploadFileInfo) => boolean | Promise<boolean>
  onDownload?: (file: UploadFileInfo) => void
  onExceed?: (files: UploadFileInfo[]) => void
}

const message = useClosableMessage()
const mergedFileList = ref(props.defaultFileList || [])
const isTableContext = computed(() => props.info?.group !== undefined && props.info?.row !== undefined)
const isStandaloneImageCard = computed(() => props.fileType === "image" && props.listType === "image-card" && !isTableContext.value)

interface IEmits {
  (
    e: "update:file",
    info: {
      file: UploadFileInfo
      fileList: Array<UploadFileInfo>
      event?: Event
    },
  ): void
  (e: "uploaded:file", fileInfo: Api.Attachment.AttachmentItem, rawFile: UploadFileInfo): void
  (e: "renamed:file", payload: { id: string, filename: string, url: string }): void
}

// Computed property to get upload props with preview support
const computedUploadProps = computed(() => {
  const baseProps: Record<string, any> = props.fileType
    ? getUploadProps(props.fileType, {
      canEdit: !props.disabled,
      onRemove: handleRemove,
      onError: handleError,
      onFinish: handleFinish,
      onBeforeUpload: handleBeforeUpload,
      onDownload: handleDownload,
      onExceed: handleExceed,
      onPreview: handlePreview,
    })
    : {}

  // Ensure accept is a string, not an object
  if (props.uploadProps?.accept) {
    const acceptValue = props.uploadProps.accept
    baseProps.accept = typeof acceptValue === "string" ? acceptValue : "*"
  }

  return baseProps
})

const { loading, startLoading, endLoading } = useLoading()
async function customRequest({
  file,
  data,
  headers,
  onFinish,
  onError,
  onProgress,
}: UploadCustomRequestOptions) {
  const formData = new FormData()
  if (data) {
    Object.keys(data).forEach((key) => {
      formData.append(key, data[key as keyof UploadCustomRequestOptions["data"]])
    })
  }

  formData.append("file", file.file as File)
  if (props.protocolId) {
    formData.append("protocol_id", props.protocolId as string)
  }

  try {
    startLoading()
    const { data: result, error } = await request<{ id: string, airalogy_file_id: string, url: string, filename: string }>({
      url: props.endpoint,
      method: "POST",
      headers: headers as Record<string, string>,
      data: formData,
      onUploadProgress: ({ progress }) => {
        onProgress({ percent: progress || 0 })
      },
    })

    if (error) {
      onError()
      return
    }

    onFinish()
    emit("uploaded:file", result, file)
  }
  catch (error) {
    message.error((error as Error).message)
    onError()
  }
  finally {
    endLoading()
  }
}

const uploadRef = ref<UploadInst | null>(null)
const formItemRecord = reactive<Record<string, Element | ComponentPublicInstance | null>>({})

defineExpose({
  uploadRef,
  fileList: mergedFileList,
  getRef: () => uploadRef,
})

function handleChange(option: {
  file: UploadFileInfo & { fileType?: string }
  fileList: Array<UploadFileInfo>
  event?: Event
}) {
  option.file.fileType = getFileType(option.file.name)
  mergedFileList.value = option.fileList
  emit("update:file", option)
}

function validateFileName(value: string) {
  if (!value) {
    return new Error(fileText.value.nameRequired)
  }

  const allowedFiles = fileTypes.map(([_, set]) => Array.from(set)).flat()
  const fileNamePattern = new RegExp(
    `^(?<startsDot>\\.)?(?<filename>[\\w\\s\\-\\.,!()\\[\\]{}@#$%^&+=\\u4e00-\\u9fa5]+)+(?<ext>${allowedFiles.join(
      "|",
    )})$`,
  )

  const match = value.match(fileNamePattern)
  if (!match || !match.groups) {
    return new Error(fileText.value.nameInvalid)
  }

  const { filename, ext, startsDot } = match.groups

  if (startsDot) {
    return new Error(fileText.value.nameStartsDot)
  }

  if (!filename) {
    return new Error(fileText.value.nameMissing)
  }

  if (!ext) {
    return new Error(fileText.value.typeInvalid)
  }

  return true
}

const fileNameRecord = reactive<Record<string, string>>({})

// Internal event handlers
function handleRemove(file: UploadFileInfo) {
  console.log("Removing file:", file.name)

  file.status = "removed"
  // Call the prop handler if provided
  if (props.onRemove) {
    const result = props.onRemove(file)
    if (result === false || result === Promise.resolve(false)) {
      return false // Prevent removal
    }
  }

  // Remove from fileNameRecord
  if (file.id && fileNameRecord[file.id]) {
    delete fileNameRecord[file.id]
  }

  // Remove from formItemRecord
  if (file.id && formItemRecord[file.id]) {
    delete formItemRecord[file.id]
  }

  const fileIndex = mergedFileList.value.findIndex(f => f.id === file.id)
  if (fileIndex === -1) {
    return false
  }

  mergedFileList.value.splice(fileIndex, 1)

  // Notify parent component of the file list change
  handleChange({
    file: file as UploadFileInfo & { fileType?: string },
    fileList: mergedFileList.value,
  })

  return true // Allow removal
}

function handleError(file: UploadFileInfo) {
  console.error("Upload error for file:", file.name)
  message.error($t("form.file.uploadFailed", { name: file.name }))

  // Call the prop handler if provided
  if (props.onError) {
    props.onError(file)
  }
}

function handleFinish(file: UploadFileInfo) {
  console.log("Upload finished for file:", file.name)

  // Call the prop handler if provided
  if (props.onFinish) {
    props.onFinish(file)
  }
}

function handleBeforeUpload(file: UploadFileInfo): boolean | Promise<boolean> {
  // Call the prop handler if provided
  if (props.onBeforeUpload) {
    return props.onBeforeUpload(file)
  }

  console.log("Before upload validation for file:", file.name)

  // Basic validation
  if (!file.file) {
    message.error(fileText.value.invalidFile)
    return false
  }

  // Check file size (10MB limit)
  const maxSize = 10 * 1024 * 1024 // 10MB
  if (file.file.size > maxSize) {
    message.error($t("form.file.sizeLimit", { size: 10 }))
    return false
  }

  return true
}

function handleDownload(file: UploadFileInfo) {
  console.log("Downloading file:", file.name)
  // Call the prop handler if provided
  if (props.onDownload) {
    props.onDownload(file)
    return
  }

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

function handleExceed(files: UploadFileInfo[]) {
  console.warn("File count exceeded. Max allowed:", props.max)
  message.warning($t("form.file.maxCount", { count: props.max }))

  // Call the prop handler if provided
  if (props.onExceed) {
    props.onExceed(files)
  }
}

async function handleRename(file: UploadFileInfo) {
  if (!file || !formItemRecord)
    return

  const { id } = file
  const name = fileNameRecord[id]

  startLoading()

  try {
    const formItem = formItemRecord[id]
    if (formItem) {
      await (formItem as unknown as FormItemInst).validate()
    }
    else if (!validateFileName(name)) {
      message.error(fileText.value.validationFailed)
      return
    }

    const res = await putRenameAssets(id, name)

    if (res.data) {
      message.success(fileText.value.renameSuccess)
      emit("renamed:file", res.data)
    }
    else if (res.error) {
      message.error(res.error.message)
    }
  }
  catch (e) {
    message.error((e as Error).message)
  }
  finally {
    endLoading()
  }
}

watch(
  () => props.fileList,
  (list) => {
    if (list) {
      mergedFileList.value = list || []
      if (Array.isArray(list)) {
        list.forEach(({ id, name }) => {
          fileNameRecord[id] = name
        })
      }
      else {
        //
      }
    }
    else {
      mergedFileList.value = props.defaultFileList || []
    }
  },
  { immediate: true },
)

function handlePreview(
  file: UploadFileInfo & { fileType?: string },
  detail: {
    event: MouseEvent
  },
) {
  if (props.onPreview) {
    props.onPreview(file as any, detail)
    return
  }

  if (!props.showPreview) {
    return
  }

  const { url } = file

  if (url) {
    window.open(url)
  }
}

const isNoActions = computed(() => !props.showPreviewButton && !props.showRemoveButton)
const themeOverrides = computed(() => {
  const overrides: UploadProps["themeOverrides"] = {}
  if (props.type === "field" || props.type === "assigner" || props.type === "dependent") {
    overrides.borderRadius = "0 0 6px 6px"
  }

  if (isNoActions.value) {
    overrides.itemColorHover = "transparent"
  }

  return overrides
})

function checkShouldUseThumbnailUrl(file: Required<UploadFileInfo>) {
  // Allow override from uploadProps
  if (props.uploadProps?.shouldUseThumbnailUrl) {
    return typeof props.uploadProps.shouldUseThumbnailUrl === "function"
      ? props.uploadProps.shouldUseThumbnailUrl(file)
      : props.uploadProps.shouldUseThumbnailUrl
  }

  const resolvedFileType = props.fileType || getFileType(file.name)
  const isImageFile = resolvedFileType === "image" || file.type?.startsWith?.("image/")
  const hasRemoteThumbnail = Boolean(file.thumbnailUrl || file.url)

  if (isImageFile && hasRemoteThumbnail) {
    return true
  }

  return !environmentSupportFile && props.showPreview
}
</script>

<style scoped lang="sass">
:deep(.upload__wrapper--has-file .n-upload-file-list .n-upload-file.n-upload-file--image-card-type)
  min-height: 90px

:deep(.n-upload-file-list .n-upload-file.n-upload-file--image-card-type)
  height: fit-content
  min-width: 90px
  max-width: 100%
  width: fit-content

// Override for table usage - constrain to exact width
.table-file-upload
  :deep(.n-upload-file-list)
    max-width: 100px !important

  :deep(.n-upload-file-list .n-upload-file.n-upload-file--image-card-type)
    width: 100px !important
    max-width: 100px !important
    min-width: 90px !important

:deep(.n-upload-file-info img)
  font-size: 12px

.upload__wrapper--show-preview
  :deep(.n-upload-file-info__thumbnail)
    opacity: 1!important
  :deep(.n-upload-file.n-upload-file--success-status.n-upload-file--image-card-type::hover .n-upload-file-info__action.n-upload-file-info__action--image-card-type)
    opacity: 1
  :deep(.n-upload-file.n-upload-file--success-status.n-upload-file--image-card-type:before)
    pointer-events: none
    background: transparent!important
  :deep(.n-upload-file-info__action.n-upload-file-info__action--image-card-type > button)
    pointer-events: all
    color: white
  :deep(.n-upload-file-info__action.n-upload-file-info__action--image-card-type)
    pointer-events: none
  :deep(.n-upload-file-info__thumbnail i)
    display: none
.upload__wrapper--show-name
  --action-height: 2rem
  --bottom-offset: 0px
  :deep(.n-upload-file-info)
    flex-direction: column
  :deep(.n-upload-file-list .n-upload-file .n-upload-file-info .n-upload-file-info__action.n-upload-file-info__action--image-card-type)
    height: auto
    bottom: var(--action-height, 0)
  :deep(.n-upload-file-list .n-upload-file.n-upload-file--image-card-type)
    &:before
      bottom: var(--action-height, 0)
  :deep(.n-input-wrapper)
    padding: 0 10px
  :deep(.n-form-item)
    display: flex
    flex-direction: column-reverse
    align-items: stretch
    top: 0
  :deep(.n-form-item-feedback-wrapper)
    position: relative
    padding: 0 6px
    height: fit-content
    min-height: fit-content
    top: 0

.upload__wrapper--no-actions
  :deep(.n-upload-file:before)
    display: none!important
  :deep(.n-upload-file-info__thumbnail)
    opacity: 1!important
  :deep(.n-upload-file-info__action)
    display: none!important

.upload__wrapper--image-card-lg
  :deep(.n-upload-file-list)
    width: 100%
    max-width: 100%
    min-width: 320px

  :deep(.n-upload-file-list .n-upload-file.n-upload-file--image-card-type)
    width: 100%
    max-width: 100%
    min-width: 100%
    min-height: 220px

  :deep(.n-upload-file-info)
    width: 100%

  :deep(.n-upload-file-info__thumbnail)
    display: flex
    align-items: center
    justify-content: center
    min-height: 220px
    width: 100%
    padding: 0

  :deep(.n-upload-file-info__name)
    display: none

  :deep(.n-upload-file-info__thumbnail img)
    max-width: 100% !important
    max-height: 320px !important
    width: auto !important
    height: auto !important
    object-fit: contain

:deep(.preview-container)
  display: flex
  justify-content: center

// Limit image size in image-card mode
:deep(.n-upload-file--image-card-type)
  align-items: center

  .n-upload-file-info__thumbnail
    display: flex
    align-items: center
    justify-content: center

  .n-upload-file-info__thumbnail img
    max-width: 90px
    max-height: 90px
    width: auto
    height: auto
    object-fit: contain

  audio, video, object
    max-width: 100%
    max-height: 100%

// Disable the overlay and action layer on image-card type to allow clicking content
:deep(.n-upload-file.n-upload-file--image-card-type)
  &::before
    display: none !important

  .n-upload-file-info__action.n-upload-file-info__action--image-card-type
    position: relative !important
    height: auto !important
    width: auto !important
    top: auto !important
    left: auto !important
    right: auto !important
    bottom: auto !important
    background: transparent !important
    pointer-events: none !important

    > *
      pointer-events: auto !important

// Prevent thumbnail from becoming transparent on hover
:deep(.n-upload-file-list .n-upload-file.n-upload-file--image-card-type:hover .n-upload-file-info .n-upload-file-info__thumbnail)
  opacity: 1 !important
</style>
