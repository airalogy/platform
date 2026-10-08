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
    class="max-w-[720px] w-[calc(100vw-32px)]"
    :content-style="{ maxHeight: '70vh', overflow: 'auto' }"
    :closable="!loading"
    :mask-closable="!loading"
    @after-leave="resetState"
  >
    <div class="mb-4 space-y-3">
      <p class="text-sm leading-6">
        {{ t("page.protocol.records.importGuide") }}
      </p>
      <n-button :disabled="!template || loading" :loading="templateLoading" @click="downloadTemplate">
        {{ t("page.protocol.records.importTemplate") }}
      </n-button>
      <p v-if="template" class="text-sm">
        {{ template.protocol_name }} · v{{ template.protocol_version }}
      </p>
      <n-collapse v-if="template">
        <n-collapse-item :title="t('page.protocol.records.importFields')" name="fields">
          <div class="overflow-x-auto">
            <n-table size="small" :single-line="false">
              <thead>
                <tr>
                  <th>{{ t("page.protocol.records.importColumn") }}</th>
                  <th>{{ t("page.protocol.records.importFieldName") }}</th>
                  <th>{{ t("page.protocol.records.importFieldRule") }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="field in template.fields" :key="field.id">
                  <td><code>var.{{ field.id }}</code></td>
                  <td>{{ field.title }}</td>
                  <td>
                    {{ importFieldType(field.schema) }} · {{ t(field.required ? "page.protocol.records.importRequired" : "page.protocol.records.importOptional") }}
                    <div v-if="field.schema.minimum !== undefined">
                      ≥ {{ field.schema.minimum }}
                    </div>
                    <div v-if="field.schema.maximum !== undefined">
                      ≤ {{ field.schema.maximum }}
                    </div>
                    <div v-if="field.schema.pattern" class="break-all">
                      {{ field.schema.pattern }}
                    </div>
                    <div v-if="field.schema.enum" class="break-all">
                      {{ field.schema.enum.join(", ") }}
                    </div>
                    <div v-if="field.schema.description">
                      {{ field.schema.description }}
                    </div>
                  </td>
                </tr>
              </tbody>
            </n-table>
          </div>
        </n-collapse-item>
      </n-collapse>
    </div>
    <n-upload
      :file-list="fileList"
      :default-upload="false"
      :max="1"
      :disabled="loading || templateLoading"
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
      :title="$t('page.protocol.records.importCheckFailed')"
    >
      <div v-if="importErrors.length" class="max-h-56 overflow-auto pr-1">
        <div v-for="(group, index) in groupedErrors" :key="index" class="mb-3 text-sm leading-6">
          <strong>{{ group.issue.column || t("page.protocol.records.importFile") }}</strong>：{{ issueMessage(group.issue) }}
          <div v-if="group.locations.length" class="text-xs">
            {{ t(group.physicalLines ? "page.protocol.records.importLines" : "page.protocol.records.importRows", { lines: group.locations.slice(0, 8).join(', '), count: group.count }) }}{{ group.locations.length > 8 ? " …" : "" }}
          </div>
        </div>
      </div>
      <span v-else>{{ errorMessage }}</span>
    </n-alert>

    <n-alert v-if="canConfirm" class="mt-4" type="success" :title="t('page.protocol.records.importCheckPassed')">
      {{ t("page.protocol.records.importDestination", { count: previewResult?.valid_count, name: previewResult?.protocol_name, version: previewResult?.protocol_version }) }}
    </n-alert>
    <n-checkbox v-if="canConfirm || isArchive" v-model:checked="acknowledged" class="mt-4" :disabled="loading">
      {{ t("page.protocol.records.importConfirmHint") }}
    </n-checkbox>

    <template #footer>
      <div class="flex flex-wrap justify-end gap-2">
        <n-button :disabled="loading" @click="showModal = false">
          {{ $t("common.cancel") }}
        </n-button>
        <n-button v-if="!isArchive" :disabled="!getSelectedFile() || loading" :loading="loading && !submitting" @click="handlePreview">
          {{ t("page.protocol.records.importCheck") }}
        </n-button>
        <n-button type="primary" :disabled="!acknowledged || (!isArchive && !canConfirm) || !getSelectedFile()" :loading="submitting" @click="handleImport">
          {{ t("page.protocol.records.importConfirm") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type { ImportProtocolRecordsResponse } from "@/service/api/project-protocols"
import type { RecordImportIssue, RecordImportPreview, RecordImportTemplate } from "@/service/api/record-import"
import type { UploadFileInfo } from "naive-ui"
import { postImportProtocolRecords } from "@/service/api/project-protocols"
import { canConfirmRecordImport, fetchRecordImportTemplate, groupImportIssues, importFieldType, previewRecordImport } from "@/service/api/record-import"
import { useClosableMessage } from "@airalogy/composables"
import { useI18n } from "vue-i18n"

defineOptions({ name: "BulkImportRecordsModal" })

const props = defineProps<{
  protocolId?: string | number | null
}>()

const emit = defineEmits<{
  (e: "imported", result: ImportProtocolRecordsResponse): void
}>()

const message = useClosableMessage()
const { t, te } = useI18n()

const showModal = ref(false)
const loading = ref(false)
const fileList = ref<UploadFileInfo[]>([])
const importErrors = ref<RecordImportIssue[]>([])
const errorMessage = ref("")
const template = ref<RecordImportTemplate | null>(null)
const templateLoading = ref(false)
const previewResult = ref<RecordImportPreview | null>(null)
const acknowledged = ref(false)
const submitting = ref(false)
const canConfirm = computed(() => canConfirmRecordImport(previewResult.value))
const groupedErrors = computed(() => groupImportIssues(importErrors.value))
const isArchive = computed(() => getInputFormat(getSelectedFile()?.name || "") === "aira")
let generation = 0

watch([showModal, () => props.protocolId], async ([open]) => {
  resetState()
  template.value = null
  if (!open || !props.protocolId)
    return
  const current = generation
  templateLoading.value = true
  try {
    const result = await fetchRecordImportTemplate(String(props.protocolId))
    if (current === generation)
      template.value = result
  }
  catch {
    if (current === generation)
      errorMessage.value = t("page.protocol.records.importTemplateFailed")
  }
  finally {
    if (current === generation)
      templateLoading.value = false
  }
})

function downloadTemplate() {
  if (!template.value)
    return
  const url = URL.createObjectURL(new Blob(["\uFEFF", template.value.csv], { type: "text/csv;charset=utf-8" }))
  const link = document.createElement("a")
  link.href = url
  link.download = `records-template-v${template.value.protocol_version}.csv`
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function clearPreview() {
  previewResult.value = null
  acknowledged.value = false
}

function resetState() {
  generation++
  clearPreview()
  fileList.value = []
  importErrors.value = []
  errorMessage.value = ""
  loading.value = false
  submitting.value = false
  templateLoading.value = false
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
  generation++
  clearPreview()
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

function parseImportErrors(error: unknown): RecordImportIssue[] {
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
        code: typeof value.code === "string" ? value.code : undefined,
        line_number: typeof value.line_number === "number" ? value.line_number : undefined,
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

function issueMessage(error: RecordImportIssue) {
  const key = `page.protocol.records.importErrors.${error.code}`
  return error.code && te(key) ? t(key) : error.message || t("page.protocol.records.bulkImportUnknownError")
}

async function handlePreview() {
  const file = getSelectedFile()
  if (!props.protocolId || !file || loading.value)
    return
  clearPreview()
  importErrors.value = []
  errorMessage.value = ""
  const current = generation
  loading.value = true
  try {
    const result = await previewRecordImport(String(props.protocolId), file, getInputFormat(file.name) || "auto")
    if (current !== generation)
      return
    previewResult.value = result
    importErrors.value = result.errors
  }
  catch (error) {
    if (current === generation) {
      importErrors.value = parseImportErrors(error)
      errorMessage.value = importErrors.value.length ? "" : parseErrorMessage(error)
    }
  }
  finally {
    if (current === generation)
      loading.value = false
  }
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
  if (loading.value || !acknowledged.value || (!isArchive.value && !canConfirm.value))
    return

  loading.value = true
  submitting.value = true
  importErrors.value = []
  errorMessage.value = ""

  try {
    const inputFormat = getInputFormat(file.name || "")
    const result = await postImportProtocolRecords(String(protocolId), {
      file,
      inputFormat: inputFormat || "auto",
      previewToken: previewResult.value?.preview_token || undefined,
    })
    message.success(t("page.protocol.records.bulkImportSuccess", { count: result.imported_count }))
    emit("imported", result)
    showModal.value = false
  }
  catch (error) {
    clearPreview()
    importErrors.value = parseImportErrors(error)
    errorMessage.value = importErrors.value.length ? "" : parseErrorMessage(error)
  }
  finally {
    loading.value = false
    submitting.value = false
  }
}
</script>
