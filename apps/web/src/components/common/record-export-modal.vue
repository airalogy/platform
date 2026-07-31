<template>
  <n-button data-testid="record-export-trigger" type="primary" secondary @click="show = true">
    <template #icon>
      <n-icon><icon-mdi-archive-arrow-down-outline /></n-icon>
    </template>
    {{ $t("page.recordExport.trigger") }}
  </n-button>

  <n-modal
    v-model:show="show"
    data-testid="record-export-modal"
    preset="card"
    class="record-export-modal"
    :title="$t('page.recordExport.title')"
    :bordered="false"
  >
    <n-tabs v-model:value="activeTab" type="line" animated>
      <n-tab-pane name="create" :tab="$t('page.recordExport.newExport')">
        <n-alert type="info" :bordered="false" class="mb-4">
          {{ scopeDescription }}
          <div class="mt-2 flex flex-wrap gap-2">
            <n-tag v-for="filter in activeFilterLabels" :key="filter" size="small" round>
              {{ filter }}
            </n-tag>
          </div>
        </n-alert>

        <n-spin :show="previewLoading">
          <div class="record-export-modal__stats">
            <div>
              <strong>{{ preview?.record_count ?? 0 }}</strong>
              <span>{{ $t("page.recordExport.records") }}</span>
            </div>
            <div>
              <strong>{{ preview?.protocol_count ?? 0 }}</strong>
              <span>{{ $t("page.recordExport.protocols") }}</span>
            </div>
            <div>
              <strong>{{ preview?.attachment_count ?? 0 }}</strong>
              <span>{{ $t("page.recordExport.attachments") }}</span>
            </div>
            <div>
              <strong>{{ formatBytes(preview?.attachment_bytes ?? 0) }}</strong>
              <span>{{ $t("page.recordExport.attachmentSize") }}</span>
            </div>
          </div>
        </n-spin>

        <n-form label-placement="top" class="mt-5">
          <n-form-item :label="$t('page.recordExport.format')">
            <n-radio-group v-model:value="exportFormat" data-testid="record-export-format">
              <n-space>
                <n-radio-button value="aira">.aira</n-radio-button>
                <n-radio-button value="jsonl">JSONL</n-radio-button>
                <n-radio-button v-if="scopeType === 'protocol'" value="csv">CSV</n-radio-button>
              </n-space>
            </n-radio-group>
            <template #feedback>
              {{ formatHint }}
            </template>
          </n-form-item>

          <n-form-item
            v-if="exportFormat === 'csv' && availableProtocolVersions.length > 1"
            :label="$t('page.recordExport.protocolVersion')"
          >
            <n-select
              v-model:value="selectedProtocolVersion"
              :options="availableProtocolVersions.map(version => ({ label: version, value: version }))"
              :placeholder="$t('page.recordExport.selectProtocolVersion')"
            />
          </n-form-item>

          <div class="record-export-modal__option">
            <div>
              <div class="font-medium">{{ $t("page.recordExport.revisionHistory") }}</div>
              <div class="text-sm text-gray-500">{{ $t("page.recordExport.revisionHistoryHint") }}</div>
            </div>
            <n-switch
              v-model:value="includeRevisionHistory"
              data-testid="record-export-revisions"
              :disabled="exportFormat === 'csv'"
            />
          </div>

          <div v-if="exportFormat === 'aira'" class="record-export-modal__option">
            <div>
              <div class="font-medium">{{ $t("page.recordExport.includeAttachments") }}</div>
              <div class="text-sm text-gray-500">{{ $t("page.recordExport.includeAttachmentsHint") }}</div>
            </div>
            <n-switch v-model:value="includeAttachments" data-testid="record-export-attachments" />
          </div>
        </n-form>

        <n-alert v-if="preview?.warnings.length" type="warning" class="mt-4">
          {{ $t("page.recordExport.previewWarnings", { count: preview.warnings.length }) }}
        </n-alert>

        <div class="mt-6 flex justify-end gap-3">
          <n-button @click="show = false">{{ $t("common.cancel") }}</n-button>
          <n-button
            data-testid="record-export-start"
            type="primary"
            :loading="creating"
            :disabled="!canCreate"
            @click="handleCreate"
          >
            {{ $t("page.recordExport.start") }}
          </n-button>
        </div>
      </n-tab-pane>

      <n-tab-pane name="history" :tab="$t('page.recordExport.history')">
        <n-spin :show="historyLoading">
          <n-empty v-if="!history.length" :description="$t('page.recordExport.noHistory')" class="py-10" />
          <div v-else class="record-export-modal__history">
            <article
              v-for="item in history"
              :key="item.id"
              data-testid="record-export-history-item"
              class="record-export-modal__history-item"
            >
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-2">
                  <strong>{{ item.output_filename || exportLabel(item) }}</strong>
                  <n-tag size="small" :type="statusType(item.status)">
                    {{ statusLabel(item.status) }}
                  </n-tag>
                </div>
                <div class="mt-1 text-sm text-gray-500">
                  {{ formatDateTime(item.created_at) }} · {{ item.record_count }} {{ $t("page.recordExport.records") }}
                  <template v-if="item.output_size_bytes"> · {{ formatBytes(item.output_size_bytes) }}</template>
                </div>
                <div v-if="item.expires_at && item.download_available" class="mt-1 text-xs text-gray-500">
                  {{ $t("page.recordExport.expiresAt", { time: formatDateTime(item.expires_at) }) }}
                </div>
                <n-popover v-if="item.warnings.length" trigger="hover" placement="bottom-start">
                  <template #trigger>
                    <n-tag class="mt-2" size="small" type="warning">
                      {{ $t("page.recordExport.warningCount", { count: item.warnings.length }) }}
                    </n-tag>
                  </template>
                  <pre class="record-export-modal__warnings">{{ formatWarnings(item.warnings) }}</pre>
                </n-popover>
                <n-progress
                  v-if="item.status === 'pending' || item.status === 'running'"
                  class="mt-2"
                  type="line"
                  :percentage="item.progress_percent"
                  :show-indicator="false"
                  processing
                />
                <div v-if="item.error" class="mt-2 text-sm text-red-500">
                  {{ item.error }}
                </div>
              </div>
              <div class="flex shrink-0 gap-2">
                <n-button
                  v-if="item.status !== 'pending' && item.status !== 'running'"
                  size="small"
                  secondary
                  :loading="regeneratingId === item.id"
                  @click="handleRegenerate(item)"
                >
                  {{ $t("page.recordExport.regenerate") }}
                </n-button>
                <n-button
                  v-if="item.download_available"
                  size="small"
                  type="primary"
                  @click="handleDownload(item)"
                >
                  {{ $t("common.download") }}
                </n-button>
                <n-popconfirm @positive-click="handleDelete(item)">
                  <template #trigger>
                    <n-button size="small" quaternary type="error">
                      {{ item.status === "pending" || item.status === "running" ? $t("common.cancel") : $t("common.delete") }}
                    </n-button>
                  </template>
                  {{ $t("page.recordExport.deleteConfirm") }}
                </n-popconfirm>
              </div>
            </article>
          </div>
        </n-spin>
      </n-tab-pane>
    </n-tabs>
  </n-modal>
</template>

<script setup lang="ts">
import type {
  RecordExportFormat,
  RecordExportItem,
  RecordExportPreview,
  RecordExportRequest,
  RecordExportScope,
  RecordExportStatus,
} from "@/service/api/record-exports"
import {
  createRecordExport,
  deleteRecordExport,
  fetchRecordExportDownload,
  fetchRecordExports,
  previewRecordExport,
} from "@/service/api/record-exports"
import { downloadAsUrl } from "@airalogy/shared/utils"
import dayjs from "dayjs"
import { type TagProps, useMessage } from "naive-ui"
import { useI18n } from "vue-i18n"

defineOptions({ name: "RecordExportModal" })

const props = defineProps<{
  scopeType: RecordExportScope
  labId: string
  projectId?: string
  protocolId?: string
  dateFrom?: string
  dateTo?: string
  submitterUserId?: string
  protocolVersion?: string
  recordNumber?: number
  recordVersion?: number
  query?: string
}>()

const emit = defineEmits<{ created: [item: RecordExportItem] }>()
const { t } = useI18n()
const message = useMessage()
const show = ref(false)
const activeTab = ref<"create" | "history">("create")
const exportFormat = ref<RecordExportFormat>("aira")
const includeRevisionHistory = ref(false)
const includeAttachments = ref(true)
const selectedProtocolVersion = ref<string>()
const preview = ref<RecordExportPreview>()
const previewLoading = ref(false)
const creating = ref(false)
const regeneratingId = ref<string>()
const historyLoading = ref(false)
const history = ref<RecordExportItem[]>([])
let previewSerial = 0
let pollTimer: ReturnType<typeof setInterval> | undefined

const availableProtocolVersions = computed(() => preview.value?.protocol_versions || [])
const activeFilterLabels = computed(() => {
  const filters: string[] = []
  if (props.dateFrom || props.dateTo) {
    filters.push(t("page.recordExport.dateFilter", {
      from: props.dateFrom || "…",
      to: props.dateTo || "…",
    }))
  }
  if (props.submitterUserId)
    filters.push(t("page.recordExport.submitterFilter"))
  const version = selectedProtocolVersion.value || props.protocolVersion
  if (version)
    filters.push(t("page.recordExport.protocolVersionFilter", { version }))
  if (props.recordNumber)
    filters.push(t("page.recordExport.recordNumberFilter", { number: props.recordNumber }))
  if (props.recordVersion)
    filters.push(t("page.recordExport.recordVersionFilter", { version: props.recordVersion }))
  if (props.query?.trim())
    filters.push(t("page.recordExport.queryFilter", { query: props.query.trim() }))
  return filters.length ? filters : [t("page.recordExport.noFilters")]
})
const scopeDescription = computed(() => ({
  lab: t("page.recordExport.labScopeHint"),
  project: t("page.recordExport.projectScopeHint"),
  protocol: t("page.recordExport.protocolScopeHint"),
}[props.scopeType]))
const formatHint = computed(() => ({
  aira: t("page.recordExport.airaHint"),
  jsonl: t("page.recordExport.jsonlHint"),
  csv: t("page.recordExport.csvHint"),
}[exportFormat.value]))
const canCreate = computed(() => {
  if (previewLoading.value || !preview.value?.record_count)
    return false
  if (exportFormat.value === "csv")
    return preview.value.csv_eligible || Boolean(selectedProtocolVersion.value)
  return true
})

function requestPayload(): RecordExportRequest {
  return {
    scope_type: props.scopeType,
    lab_id: props.labId,
    project_id: props.projectId,
    protocol_id: props.protocolId,
    export_format: exportFormat.value,
    include_revision_history: exportFormat.value === "csv" ? false : includeRevisionHistory.value,
    include_attachments: exportFormat.value === "aira" ? includeAttachments.value : false,
    date_from: props.dateFrom,
    date_to: props.dateTo,
    submitter_user_id: props.submitterUserId,
    protocol_version: selectedProtocolVersion.value || props.protocolVersion,
    record_number: props.recordNumber,
    record_version: props.recordVersion,
    query: props.query?.trim() || undefined,
  }
}

async function loadPreview() {
  const serial = ++previewSerial
  previewLoading.value = true
  try {
    const { data } = await previewRecordExport(requestPayload())
    if (serial === previewSerial && data)
      preview.value = data
  }
  catch {
    if (serial === previewSerial) {
      preview.value = undefined
      message.error(t("page.recordExport.previewFailed"))
    }
  }
  finally {
    if (serial === previewSerial)
      previewLoading.value = false
  }
}

async function loadHistory(silent = false) {
  if (!silent)
    historyLoading.value = true
  try {
    const { data } = await fetchRecordExports({ pageSize: 50 })
    history.value = data?.items || []
  }
  catch {
    if (!silent)
      message.error(t("page.recordExport.historyFailed"))
  }
  finally {
    if (!silent)
      historyLoading.value = false
  }
}

async function handleCreate() {
  creating.value = true
  try {
    const { data } = await createRecordExport({
      ...requestPayload(),
      idempotency_key: crypto.randomUUID(),
    })
    if (!data)
      return
    message.success(t("page.recordExport.started"))
    emit("created", data)
    activeTab.value = "history"
    await loadHistory()
  }
  finally {
    creating.value = false
  }
}

async function handleDownload(item: RecordExportItem) {
  const { data } = await fetchRecordExportDownload(item.id)
  if (data)
    downloadAsUrl(data.url, data.filename)
}

async function handleRegenerate(item: RecordExportItem) {
  regeneratingId.value = item.id
  try {
    const options = item.options || {}
    await createRecordExport({
      scope_type: item.scope_type,
      lab_id: item.lab_id,
      project_id: item.project_id || undefined,
      protocol_id: item.protocol_id || undefined,
      export_format: item.export_format,
      include_revision_history: item.include_revision_history,
      include_attachments: item.include_attachments,
      date_from: typeof options.date_from === "string" ? options.date_from : undefined,
      date_to: typeof options.date_to === "string" ? options.date_to : undefined,
      submitter_user_id: typeof options.submitter_user_id === "string" ? options.submitter_user_id : undefined,
      protocol_version: typeof options.protocol_version === "string" ? options.protocol_version : undefined,
      record_number: typeof options.record_number === "number" ? options.record_number : undefined,
      record_version: typeof options.record_version === "number" ? options.record_version : undefined,
      query: typeof options.query === "string" ? options.query : undefined,
      idempotency_key: crypto.randomUUID(),
    })
    message.success(t("page.recordExport.regenerated"))
    await loadHistory()
  }
  finally {
    regeneratingId.value = undefined
  }
}

async function handleDelete(item: RecordExportItem) {
  await deleteRecordExport(item.id)
  await loadHistory()
}

function statusType(status: RecordExportStatus): TagProps["type"] {
  return {
    pending: "default",
    running: "info",
    succeeded: "success",
    failed: "error",
    cancelled: "warning",
    expired: "default",
  }[status] as TagProps["type"]
}

function statusLabel(status: RecordExportStatus) {
  return t(`page.recordExport.status.${status}` as any)
}

function formatBytes(bytes: number) {
  if (!bytes)
    return "0 B"
  const units = ["B", "KB", "MB", "GB", "TB"]
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`
}

function formatDateTime(value: string) {
  return dayjs(value).format("YYYY-MM-DD HH:mm")
}

function exportLabel(item: RecordExportItem) {
  return `${item.scope_type.toUpperCase()} Records · ${item.export_format.toUpperCase()}`
}

function formatWarnings(warnings: RecordExportItem["warnings"]) {
  return warnings.map(warning => `${warning.code}: ${JSON.stringify(warning)}`).join("\n")
}

watch(show, async (value) => {
  if (!value)
    return
  selectedProtocolVersion.value = props.protocolVersion
  await Promise.all([loadPreview(), loadHistory()])
})
watch([exportFormat, includeRevisionHistory, includeAttachments, selectedProtocolVersion], () => {
  if (show.value)
    void loadPreview()
})
watch(exportFormat, (value) => {
  if (value === "csv")
    includeRevisionHistory.value = false
})

onMounted(() => {
  pollTimer = setInterval(() => {
    if (show.value && history.value.some(item => item.status === "pending" || item.status === "running"))
      void loadHistory(true)
  }, 2000)
})
onBeforeUnmount(() => {
  if (pollTimer)
    clearInterval(pollTimer)
})
</script>

<style scoped>
.record-export-modal {
  width: min(760px, calc(100vw - 32px));
}

.record-export-modal__stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.record-export-modal__stats > div {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 14px;
  border: 1px solid var(--n-border-color);
  border-radius: 8px;
}

.record-export-modal__stats strong {
  font-size: 20px;
}

.record-export-modal__stats span {
  color: #6b7280;
  font-size: 13px;
}

.record-export-modal__option,
.record-export-modal__history-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 0;
  border-bottom: 1px solid var(--n-border-color);
}

.record-export-modal__history {
  max-height: 520px;
  overflow-y: auto;
}

.record-export-modal__warnings {
  max-width: min(560px, calc(100vw - 64px));
  max-height: 240px;
  overflow: auto;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 640px) {
  .record-export-modal__stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .record-export-modal__history-item {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
