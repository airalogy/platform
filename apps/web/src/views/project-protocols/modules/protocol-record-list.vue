<template>
  <n-spin :show="loading" class="min-h-60">
    <div v-if="recordList.length > 0" class="record-collection mt-4">
      <template v-if="activeView === 'table'">
        <aimd-record-table
          v-model:selected-record-keys="selectedRecordKeys"
          v-model:field-keys="visibleFieldKeys"
          v-model:metadata-column-keys="visibleMetadataColumnKeys"
          :aimd="protocolInfo.aimd"
          :records="recordList"
          :metadata-columns="metadataColumns"
          :record-key="getRecordKey"
          :record-label="getRecordLabel"
          :locale="locale"
          :selection-limit="0"
          @open-record="handleOpenRecord"
          @update:selected-record-keys="handleSelectedRecordKeysUpdate"
        >
          <template #toolbar>
            <div v-if="selectedRecords.length > 0" class="record-selection-actions">
              <div v-if="selectedRecords.length === 1" class="record-compare-hint" role="status">
                <n-icon size="16">
                  <icon-tabler-arrows-diff />
                </n-icon>
                <span>{{ $t("page.protocol.records.selectOneMoreToCompare") }}</span>
              </div>
              <n-button v-else-if="selectedRecords.length <= 4" type="primary" size="small" @click="handleOpenComparison">
                <template #icon>
                  <n-icon size="16">
                    <icon-tabler-arrows-diff />
                  </n-icon>
                </template>
                {{ $t("page.protocol.records.compareSelected", { count: selectedRecords.length }) }}
              </n-button>
              <div v-else class="record-compare-hint record-compare-hint--warning" role="status">
                <n-icon size="16">
                  <icon-tabler-alert-triangle />
                </n-icon>
                <span>{{ $t("page.protocol.records.compareSelectionLimit") }}</span>
              </div>

              <div class="record-batch-actions">
                <n-button
                  secondary
                  size="small"
                  :disabled="selectedRecordsNotInChat.length === 0"
                  @click="handleAddSelectedToChat"
                >
                  <template #icon>
                    <n-icon size="16">
                      <icon-tabler-message-plus />
                    </n-icon>
                  </template>
                  {{ $t("page.protocol.records.addSelectedToChat", { count: selectedRecordsNotInChat.length }) }}
                </n-button>

                <n-dropdown
                  :options="jsonExportOptions"
                  trigger="click"
                  placement="bottom-end"
                  @select="handleSelectedJsonExport"
                >
                  <n-button size="small">
                    <template #icon>
                      <n-icon size="16">
                        <icon-mdi-code-json />
                      </n-icon>
                    </template>
                    {{ $t("page.protocol.records.exportSelectedJson", { count: selectedRecords.length }) }}
                  </n-button>
                </n-dropdown>
              </div>
            </div>
          </template>

          <template #actions="{ record, index }">
            <div class="record-row-actions">
              <n-tooltip v-if="isItemInChatContext(getRecordKey(record, index))" trigger="hover">
                {{ $t("page.protocol.timeline.removeFromChat") }}
                <template #trigger>
                  <n-button
                    quaternary
                    circle
                    size="small"
                    type="error"
                    :disabled="isItemInChatContextDisabled(getRecordKey(record, index))"
                    @click="emit('removeFromChat', toTimelineItem(record, index))"
                  >
                    <template #icon>
                      <n-icon size="16">
                        <icon-local-delete />
                      </n-icon>
                    </template>
                  </n-button>
                </template>
              </n-tooltip>
              <n-tooltip v-else trigger="hover">
                {{ $t("page.protocol.timeline.addToChat") }}
                <template #trigger>
                  <n-button quaternary circle size="small" @click="emit('addToChat', toTimelineItem(record, index))">
                    <template #icon>
                      <n-icon size="16">
                        <icon-tabler-message-plus />
                      </n-icon>
                    </template>
                  </n-button>
                </template>
              </n-tooltip>

              <n-dropdown
                :options="jsonExportOptions"
                trigger="click"
                placement="bottom-start"
                @select="(key: string) => handleJsonExport(key, record)"
              >
                <span class="inline-flex">
                  <tooltip-button quaternary size="small" circle>
                    <template #tooltip>
                      {{ $t("page.protocol.timeline.exportJsonData") }}
                    </template>
                    <template #icon>
                      <n-icon size="16">
                        <icon-mdi-code-json />
                      </n-icon>
                    </template>
                  </tooltip-button>
                </span>
              </n-dropdown>

              <n-tooltip trigger="hover">
                {{ $t("common.id") }}
                <template #trigger>
                  <copy-to-clip-component
                    :text="getRecordAiraId(record)"
                    :show-text="false"
                    :show-success="true"
                    :button-props="{ quaternary: true, circle: true, size: 'small' }"
                    :icon-props="{ size: 16 }"
                  />
                </template>
              </n-tooltip>

              <tooltip-button quaternary size="small" circle @click="handleOpenRecord(record, index)">
                <template #tooltip>
                  {{ $t("page.protocol.timeline.viewReport") }}
                </template>
                <template #icon>
                  <n-icon size="16">
                    <icon-tabler-eye />
                  </n-icon>
                </template>
              </tooltip-button>

              <n-tooltip v-if="canDeleteByRole(record)" :disabled="!getDeleteBlockedReason(record)">
                <template #trigger>
                  <span class="inline-flex">
                    <n-button
                      type="error"
                      quaternary
                      circle
                      size="small"
                      :disabled="deleting || !!getDeleteBlockedReason(record)"
                      @click="handleDeleteClick(record)"
                    >
                      <template #icon>
                        <n-icon size="16">
                          <icon-tabler-trash />
                        </n-icon>
                      </template>
                    </n-button>
                  </span>
                </template>
                {{ getDeleteBlockedReason(record) }}
              </n-tooltip>
            </div>
          </template>
        </aimd-record-table>
      </template>

      <template v-else>
        <header class="record-compare-header">
          <n-button quaternary size="small" @click="handleReturnToTable">
            <template #icon>
              <n-icon size="16">
                <icon-tabler-arrow-left />
              </n-icon>
            </template>
            {{ $t("page.protocol.records.backToTableSelection") }}
          </n-button>

          <div class="record-compare-heading">
            <n-icon size="20">
              <icon-tabler-arrows-diff />
            </n-icon>
            <span>{{ $t("page.protocol.records.comparingSelected", { count: selectedRecords.length }) }}</span>
            <span class="record-compare-labels">{{ selectedRecordLabels }}</span>
          </div>
        </header>

        <aimd-record-compare
          v-model:show-only-differences="showOnlyDifferences"
          :aimd="protocolInfo.aimd"
          :records="selectedRecords"
          :max-default-columns="compareMaxDefaultColumns"
          :record-key="getRecordKey"
          :record-label="getRecordLabel"
          :locale="locale"
          @open-record="handleOpenRecord"
        />
      </template>
    </div>

    <div v-else-if="!loading" class="my-10 select-none text-center">
      <img
        src="/images/empty_placeholder.svg"
        alt="placeholder"
        class="pointer-events-none h-40 w-full object-contain"
      >
    </div>

    <n-pagination
      v-if="total > 0 && activeView === 'table'"
      class="my-5 w-full justify-center"
      :page="currentPage"
      :page-size="currentPageSize"
      :page-count="pageCount"
      :page-sizes="recordPageSizeOptions"
      show-size-picker
      @update:page="handlePageChange"
      @update:page-size="handlePageSizeChange"
    />
  </n-spin>

  <n-modal
    v-model:show="showPreviewModal"
    preset="card"
    :title="$t('page.protocol.timeline.jsonPreviewTitle', { name: previewJsonFilename })"
    class="max-w-6xl w-4/5"
    content-class="max-h-[70vh] overflow-auto"
    @after-leave="previewJsonData = ''"
  >
    <shiki-code-viewer
      :code="previewJsonData"
      language="json"
      theme="github-dark"
      :max-height="600"
      :show-line-numbers="true"
    />
  </n-modal>

  <delete-confirmation-modal
    :show="showDeleteModal"
    :entity-name="$t('common.record')"
    :item-name="deleteItemName"
    :delete-confirmation-text="deleteConfirmationText"
    :is-delete-confirmation-valid="isDeleteConfirmationValid"
    :deleting="deleting"
    :extra-warning="deleteAdminWarning || undefined"
    @update:delete-confirmation-text="deleteConfirmationText = $event"
    @confirm="confirmDelete"
    @cancel="handleCancelDelete"
  />
</template>

<script setup lang="ts">
import type {
  AimdRecordMetadataColumn,
  AimdRecordViewKey,
} from "@airalogy/aimd-renderer/vue"
import type { ProtocolModels } from "@airalogy/shared/types"
import type { ITimelineItem } from "../types"
import { DeleteConfirmationModal, useDeleteConfirmation } from "@/components/common/settings"
import { usePagination, useProjectPermissions } from "@/composables"
import { deleteResearchRecord } from "@/service/api/project-protocols"
import { useAuthStore } from "@/store/modules/auth"
import { AimdRecordCompare, AimdRecordTable } from "@airalogy/aimd-renderer/vue"
import CopyToClipComponent from "@airalogy/components/copy-to-clip.vue"
import ShikiCodeViewer from "@airalogy/components/file-preview/code-preview/shiki-code-viewer.vue"
import TooltipButton from "@airalogy/components/tooltip-button.vue"
import { useClosableMessage } from "@airalogy/composables"
import { copyToClip, downloadAs, formatDate } from "@airalogy/shared/utils"
import dayjs from "dayjs"
import { useI18n } from "vue-i18n"
import { useProjectInfoStore } from "../hooks/useProjectInfoStore"
import {
  getRecordFieldKeysPreference,
  getRecordMetadataColumnKeysPreference,
  RECORD_PAGE_SIZE_OPTIONS,
  setRecordFieldKeysPreference,
  setRecordMetadataColumnKeysPreference,
  setRecordPageSizePreference,
} from "../record-view-preferences"
import { createProtocolRecordData } from "../utils"

interface Props {
  loading: boolean
  recordList: ProtocolModels.RecordInfo[]
  protocolInfo: ProtocolModels.ProjectProtocolInfo
  total: number
  latestRecordNumber?: number | null
  deleteGraceDays?: number
  initialPageSize?: number
  isItemInChatContext: (id: string | number) => boolean
  isItemInChatContextDisabled: (id: string | number) => boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: "addToChat", item: ITimelineItem): void
  (e: "addSelectedToChat", items: ITimelineItem[]): void
  (e: "removeFromChat", item: ITimelineItem): void
  (e: "showReport", item: ITimelineItem): void
  (e: "update:page", page: number): void
  (e: "fetchRecords", payload: { currentPage: number, currentPageSize: number }): void
  (e: "recordDeleted"): void
}>()

const { t, locale } = useI18n()
const authStore = useAuthStore()
const message = useClosableMessage()
const { projectInfo } = useProjectInfoStore()
const { canDeleteOthersRecords, canDeleteOwnRecords } = useProjectPermissions(projectInfo)

const activeView = ref<"table" | "compare">("table")
const visibleFieldKeys = ref<string[]>([])
const visibleMetadataColumnKeys = ref<string[] | undefined>(undefined)
const selectedRecordKeys = ref<AimdRecordViewKey[]>([])
const selectedRecordMap = shallowReactive(new Map<AimdRecordViewKey, ProtocolModels.RecordInfo>())
const showOnlyDifferences = ref(false)
// Keep comparisons complete while Platform is compatible with renderer 2.11.
const compareMaxDefaultColumns = Number.MAX_SAFE_INTEGER
const recordPageSizeOptions = [...RECORD_PAGE_SIZE_OPTIONS]

watch(
  [() => authStore.userInfo.id, () => props.protocolInfo.id],
  ([userId, protocolId]) => {
    visibleFieldKeys.value = getRecordFieldKeysPreference(userId, protocolId)
    visibleMetadataColumnKeys.value = getRecordMetadataColumnKeysPreference(userId, protocolId)
  },
  { immediate: true },
)

watch(visibleFieldKeys, (fieldKeys) => {
  setRecordFieldKeysPreference(authStore.userInfo.id, props.protocolInfo.id, fieldKeys)
}, { deep: true })

watch(visibleMetadataColumnKeys, (metadataColumnKeys) => {
  setRecordMetadataColumnKeysPreference(
    authStore.userInfo.id,
    props.protocolInfo.id,
    metadataColumnKeys,
  )
}, { deep: true })

const { currentPage, currentPageSize, handlePageChange, pageCount } = usePagination({
  options: { page: 1, pageSize: props.initialPageSize || 10, total: computed(() => props.total) },
  fetchData: (payload) => {
    emit("fetchRecords", payload)
    return Promise.resolve()
  },
})

function handlePageSizeChange(pageSize: number) {
  setRecordPageSizePreference(authStore.userInfo.id, pageSize)
  currentPageSize.value = pageSize
}

function getRecordKey(record: unknown, _index = 0): AimdRecordViewKey {
  return (record as ProtocolModels.RecordInfo).record_id
}

function getRecordLabel(record: unknown): string {
  const item = record as ProtocolModels.RecordInfo
  return `#${item.metadata.record_num}`
}

function getRecordAiraId(record: unknown): string {
  return String((record as ProtocolModels.RecordInfo).airalogy_record_id)
}

function toTimelineItem(record: unknown, index = 0): ITimelineItem {
  const item = record as ProtocolModels.RecordInfo
  const metadata = item.metadata
  return {
    id: item.airalogy_record_id,
    recordId: item.record_id,
    operator: metadata.record_current_version_submission_user_id,
    operatorId: metadata.record_current_version_submission_user_id,
    operatorUsername: metadata.record_current_version_submission_user_id,
    order: metadata.record_num ?? Math.max(props.total - index, 1),
    field: createProtocolRecordData(item.data),
    protocolId: metadata.protocol_id,
    record: item,
    protocolVersion: metadata.protocol_version,
    recordVersion: item.record_version,
    time: formatDate(metadata.record_current_version_submission_time, "date-time"),
  }
}

function handleOpenRecord(record: unknown, index = 0) {
  emit("showReport", toTimelineItem(record, index))
}

function handleSelectedRecordKeysUpdate(keys: AimdRecordViewKey[]) {
  selectedRecordKeys.value = keys
  const selectedSet = new Set(keys)

  for (const key of selectedRecordMap.keys()) {
    if (!selectedSet.has(key)) {
      selectedRecordMap.delete(key)
    }
  }
  for (const record of props.recordList) {
    const key = getRecordKey(record)
    if (selectedSet.has(key)) {
      selectedRecordMap.set(key, record)
    }
  }
}

const selectedRecords = computed(() => selectedRecordKeys.value
  .map(key => selectedRecordMap.get(key))
  .filter((record): record is ProtocolModels.RecordInfo => Boolean(record)))
const selectedRecordLabels = computed(() => selectedRecords.value
  .map(record => getRecordLabel(record))
  .join(" · "))

const selectedRecordsNotInChat = computed(() => selectedRecords.value.filter(record => (
  !props.isItemInChatContext(getRecordKey(record))
)))

function handleOpenComparison() {
  if (selectedRecords.value.length >= 2 && selectedRecords.value.length <= 4) {
    activeView.value = "compare"
  }
}

function handleReturnToTable() {
  activeView.value = "table"
}

function handleAddSelectedToChat() {
  const items = selectedRecordsNotInChat.value.map(record => toTimelineItem(record))
  if (items.length > 0) {
    emit("addSelectedToChat", items)
  }
}

watch(() => props.recordList, (records) => {
  const selectedSet = new Set(selectedRecordKeys.value)
  for (const record of records) {
    const key = getRecordKey(record)
    if (selectedSet.has(key)) {
      selectedRecordMap.set(key, record)
    }
  }
})

watch(selectedRecords, (records) => {
  if (records.length < 2 && activeView.value === "compare") {
    activeView.value = "table"
  }
})

const metadataColumns = computed<AimdRecordMetadataColumn[]>(() => [
  {
    key: "submittedAt",
    label: t("page.protocol.records.submittedAt"),
    class: "record-metadata-column record-metadata-column--time",
    getValue: record => formatDate(
      (record as ProtocolModels.RecordInfo).metadata.record_current_version_submission_time,
      "date-time",
    ),
  },
  {
    key: "submittedBy",
    label: t("page.protocol.records.submittedBy"),
    class: "record-metadata-column record-metadata-column--user",
    getValue: record => `@${(record as ProtocolModels.RecordInfo).metadata.record_current_version_submission_user_id}`,
  },
  {
    key: "recordVersion",
    label: t("page.protocol.records.recordVersion"),
    class: "record-metadata-column record-metadata-column--version",
    getValue: record => `v${(record as ProtocolModels.RecordInfo).record_version}`,
  },
])

const jsonExportOptions = computed(() => [
  { label: t("page.protocol.timeline.downloadJson"), key: "download" },
  { label: t("page.protocol.timeline.copyToClipboard"), key: "copy" },
  { label: t("page.protocol.timeline.previewJson"), key: "preview" },
])

const showPreviewModal = ref(false)
const previewJsonData = ref("")
const previewJsonFilename = ref("")

function getFilename(record: ProtocolModels.RecordInfo) {
  const { lab, project, name } = props.protocolInfo
  const { lab_id, project_id, protocol_id, record_num } = record.metadata
  return [
    lab?.name || lab_id,
    project?.name || project_id,
    name || protocol_id,
    record_num ? `record-${record_num}` : record.record_id,
    `v${record.record_version}`,
  ].filter(Boolean).join("-")
}

function getSelectedRecordsFilename(records: ProtocolModels.RecordInfo[]) {
  const { lab, project, name } = props.protocolInfo
  const recordNumbers = records
    .map(record => record.metadata.record_num)
    .filter((recordNumber): recordNumber is number => typeof recordNumber === "number")
  const recordsLabel = recordNumbers.length === records.length
    ? `records-${recordNumbers.join("-")}`
    : `records-${records.length}`

  return [
    lab?.name,
    project?.name,
    name,
    recordsLabel,
  ].filter(Boolean).join("-")
}

function exportJson(key: string, value: unknown, filename: string) {
  const jsonData = JSON.stringify(value, null, 2)
  if (key === "download") {
    downloadAs(jsonData, `${filename}.json`)
    message.success(t("page.protocol.timeline.downloadSuccess"))
  }
  else if (key === "copy") {
    copyToClip(jsonData)
    message.success(t("page.protocol.timeline.copySuccess"))
  }
  else if (key === "preview") {
    previewJsonData.value = jsonData
    previewJsonFilename.value = filename
    showPreviewModal.value = true
  }
}

function handleJsonExport(key: string, value: unknown) {
  const record = value as ProtocolModels.RecordInfo
  exportJson(key, record, getFilename(record))
}

function handleSelectedJsonExport(key: string) {
  const records = selectedRecords.value
  if (records.length > 0) {
    exportJson(key, records, getSelectedRecordsFilename(records))
  }
}

const effectiveDeleteGraceDays = computed(() => {
  if (Number.isFinite(props.deleteGraceDays) && (props.deleteGraceDays as number) > 0) {
    return props.deleteGraceDays as number
  }
  return 7
})

function canDeleteByRole(record: unknown) {
  const item = record as ProtocolModels.RecordInfo
  return canDeleteOthersRecords.value
    || (canDeleteOwnRecords.value
      && item.metadata.record_current_version_submission_user_id === authStore.userInfo.id)
}

function hasNewerRecord(record: ProtocolModels.RecordInfo) {
  const currentNumber = record.metadata.record_num
  return currentNumber != null
    && props.latestRecordNumber != null
    && currentNumber < props.latestRecordNumber
}

function isDeleteGraceExpired(record: ProtocolModels.RecordInfo) {
  if (canDeleteOthersRecords.value) {
    return false
  }
  const createdAt = record.metadata.record_current_version_submission_time
  return Boolean(createdAt && dayjs().isAfter(dayjs(createdAt).add(effectiveDeleteGraceDays.value, "day")))
}

function getDeleteBlockedReason(value: unknown) {
  const record = value as ProtocolModels.RecordInfo
  if (!canDeleteByRole(record)) {
    return ""
  }
  if (isDeleteGraceExpired(record)) {
    return t("page.protocol.records.deleteBlockedExpired", { days: effectiveDeleteGraceDays.value })
  }
  if (props.latestRecordNumber == null) {
    return t("page.protocol.records.deleteBlockedLoading")
  }
  if (hasNewerRecord(record)) {
    return t("page.protocol.records.deleteBlockedLatest")
  }
  return ""
}

const pendingDeleteRecord = ref<ProtocolModels.RecordInfo | null>(null)
const deleteItemName = computed(() => pendingDeleteRecord.value
  ? getRecordLabel(pendingDeleteRecord.value)
  : t("common.record"))

const {
  showDeleteModal,
  deleteConfirmationText,
  deleting,
  isDeleteConfirmationValid,
  handleDelete: openDeleteModal,
  cancelDelete,
  confirmDelete,
} = useDeleteConfirmation(handleDeleteRecord, "Record", handleDeleteSuccess)

const deleteAdminWarning = computed(() => pendingDeleteRecord.value && canDeleteOthersRecords.value
  ? t("page.protocol.records.deleteAdminWarning", { days: effectiveDeleteGraceDays.value })
  : "")

function handleDeleteClick(value: unknown) {
  const record = value as ProtocolModels.RecordInfo
  const reason = getDeleteBlockedReason(record)
  if (deleting.value || reason) {
    if (reason) {
      message.warning(reason)
    }
    return
  }
  pendingDeleteRecord.value = record
  openDeleteModal()
}

function handleCancelDelete() {
  pendingDeleteRecord.value = null
  cancelDelete()
}

async function handleDeleteRecord() {
  const record = pendingDeleteRecord.value
  if (!record) {
    return { data: null, error: new Error("Wrong params") }
  }
  return deleteResearchRecord(String(props.protocolInfo.id), record.record_id, record.record_version)
}

function handleDeleteSuccess() {
  const key = pendingDeleteRecord.value ? getRecordKey(pendingDeleteRecord.value) : null
  if (key != null) {
    selectedRecordKeys.value = selectedRecordKeys.value.filter(item => item !== key)
    selectedRecordMap.delete(key)
  }
  pendingDeleteRecord.value = null
  emit("recordDeleted")
}
</script>

<style scoped>
.record-row-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}

.record-selection-actions,
.record-batch-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.record-selection-actions {
  min-width: 0;
}

.record-compare-hint {
  min-height: 28px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border: 1px solid rgba(36, 122, 100, 0.18);
  border-radius: 5px;
  background: #eef8f4;
  color: #236451;
  font-size: 13px;
  white-space: nowrap;
}

.record-compare-hint--warning {
  border-color: rgba(196, 125, 28, 0.24);
  background: #fff8e8;
  color: #8a5716;
}

.record-batch-actions {
  white-space: nowrap;
}

.record-compare-header {
  display: flex;
  align-items: center;
  gap: 12px 18px;
  flex-wrap: wrap;
  padding: 0 12px 12px;
}

.record-compare-heading {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #253247;
  font-weight: 650;
}

.record-compare-labels {
  color: #607079;
  font-size: 12px;
  font-weight: 500;
}

:deep(.record-metadata-column--time) {
  min-width: 172px;
  white-space: nowrap;
}

:deep(.record-metadata-column--user) {
  min-width: 130px;
}

:deep(.record-metadata-column--version) {
  min-width: 74px;
  width: 74px;
}

@media (max-width: 640px) {
  .record-selection-actions {
    width: 100%;
  }

  .record-compare-hint,
  .record-batch-actions {
    white-space: normal;
  }

  .record-compare-header {
    align-items: flex-start;
    padding-inline: 10px;
  }

  .record-compare-heading {
    width: 100%;
    flex-wrap: wrap;
  }
}
</style>
