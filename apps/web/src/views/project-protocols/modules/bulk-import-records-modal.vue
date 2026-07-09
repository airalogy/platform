<template>
  <n-button secondary type="primary" :disabled="!protocolId" @click="showModal = true">
    <template #icon>
      <icon-local-file-csv />
    </template>
    {{ $t("page.protocol.records.bulkImport") }}
  </n-button>

  <n-modal
    v-model:show="showModal"
    preset="card"
    :title="$t('page.protocol.records.bulkImportTitle')"
    class="w-[calc(100vw-32px)] max-w-[560px]"
    :mask-closable="!loading"
    @after-leave="resetState"
  >
    <n-upload
      :file-list="fileList"
      :default-upload="false"
      :max="1"
      accept=".csv,.tsv,.json,.jsonl,.aira"
      @before-upload="handleBeforeUpload"
      @update:file-list="handleFileListUpdate"
    >
      <n-upload-dragger>
        <div class="flex flex-col items-center gap-2 py-5">
          <n-icon size="34" class="text-primary">
            <icon-local-cloud-upload />
          </n-icon>
          <div class="text-sm font-medium">
            {{ $t("page.protocol.records.bulkImportDropText") }}
          </div>
          <div class="max-w-[420px] text-center text-xs text-gray-500 leading-5">
            {{ $t("page.protocol.records.bulkImportSupportHint") }}
          </div>
        </div>
      </n-upload-dragger>
    </n-upload>

    <n-alert
      v-if="errorMessage || importErrors.length"
      class="mt-4"
      type="error"
      :title="$t('page.protocol.records.bulkImportErrorTitle')"
    >
      <div v-if="importErrors.length" class="max-h-56 overflow-auto pr-1">
        <div v-for="(error, index) in importErrors" :key="index" class="text-xs leading-5">
          {{ formatImportError(error) }}
        </div>
      </div>
      <span v-else>{{ errorMessage }}</span>
    </n-alert>

    <template #footer>
      <div class="flex justify-end gap-2">
        <n-button :disabled="loading" @click="showModal = false">
          {{ $t("common.cancel") }}
        </n-button>
        <n-button type="primary" :disabled="!getSelectedFile()" :loading="loading" @click="handleImport">
          {{ $t("page.protocol.records.bulkImportSubmit") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type { ImportProtocolRecordsResponse } from "@/service/api/project-protocols"
import type { UploadFileInfo } from "naive-ui"
import { postImportProtocolRecords } from "@/service/api/project-protocols"
import { useClosableMessage } from "@airalogy/composables"
import { useI18n } from "vue-i18n"

defineOptions({ name: "BulkImportRecordsModal" })

const props = defineProps<{
  protocolId?: string | number | null
}>()

const emit = defineEmits<{
  (e: "imported", result: ImportProtocolRecordsResponse): void
}>()

interface ImportErrorItem {
  row_number?: number
  column?: string | null
  message: string
}

const message = useClosableMessage()
const { t } = useI18n()

const showModal = ref(false)
const loading = ref(false)
const fileList = ref<UploadFileInfo[]>([])
const importErrors = ref<ImportErrorItem[]>([])
const errorMessage = ref("")

function resetState() {
  fileList.value = []
  importErrors.value = []
  errorMessage.value = ""
  loading.value = false
}

function handleBeforeUpload(options: { file: UploadFileInfo }) {
  const filename = options.file.name || ""
  if (!getInputFormat(filename)) {
    message.error(t("page.protocol.records.bulkImportSupportedOnly"))
    return false
  }

  return true
}

function handleFileListUpdate(nextFileList: UploadFileInfo[]) {
  fileList.value = nextFileList.slice(-1)
  importErrors.value = []
  errorMessage.value = ""
}

function getSelectedFile() {
  return fileList.value[0]?.file || null
}

function getErrorDetail(error: unknown) {
  return (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
}

function parseImportErrors(error: unknown): ImportErrorItem[] {
  const detail = getErrorDetail(error)
  if (
    detail
    && typeof detail === "object"
    && Array.isArray((detail as { errors?: unknown }).errors)
  ) {
    return (detail as { errors: unknown[] }).errors.filter(item => item && typeof item === "object").map((item) => {
      const value = item as Record<string, unknown>
      return {
        row_number: typeof value.row_number === "number" ? value.row_number : undefined,
        column: typeof value.column === "string" ? value.column : null,
        message:
            typeof value.message === "string"
              ? value.message
              : t("page.protocol.records.bulkImportUnknownError"),
      }
    })
  }

  return []
}

function parseErrorMessage(error: unknown) {
  const detail = getErrorDetail(error)
  if (typeof detail === "string") {
    return detail
  }
  if (
    detail
    && typeof detail === "object"
    && typeof (detail as { message?: unknown }).message === "string"
  ) {
    return (detail as { message: string }).message
  }
  if (error instanceof Error) {
    return error.message
  }

  return t("page.protocol.records.bulkImportUnknownError")
}

function formatImportError(error: ImportErrorItem) {
  return t("page.protocol.records.bulkImportRowError", {
    row: error.row_number ?? "-",
    column: error.column ? `, ${error.column}` : "",
    message: error.message,
  })
}

function getInputFormat(filename: string) {
  const extension = filename.toLowerCase().split(".").pop()
  if (extension === "csv" || extension === "tsv" || extension === "json" || extension === "jsonl" || extension === "aira") {
    return extension
  }
  return null
}

async function handleImport() {
  const protocolId = props.protocolId
  const file = getSelectedFile()

  if (!protocolId || !file) {
    message.warning(t("page.protocol.records.bulkImportNoFile"))
    return
  }

  loading.value = true
  importErrors.value = []
  errorMessage.value = ""

  try {
    const inputFormat = getInputFormat(file.name || "")
    const result = await postImportProtocolRecords(String(protocolId), {
      file,
      inputFormat: inputFormat || "auto",
    })
    message.success(t("page.protocol.records.bulkImportSuccess", { count: result.imported_count }))
    emit("imported", result)
    showModal.value = false
  }
  catch (error) {
    importErrors.value = parseImportErrors(error)
    errorMessage.value = importErrors.value.length ? "" : parseErrorMessage(error)
  }
  finally {
    loading.value = false
  }
}
</script>
