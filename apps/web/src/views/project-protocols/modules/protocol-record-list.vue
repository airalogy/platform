<template>
  <n-spin :show="loading" class="min-h-60">
    <n-tabs
      v-if="recordList.length > 0"
      v-model:value="activeView"
      type="segment"
      animated
      class="record-view-tabs mt-4"
    >
      <n-tab-pane name="table">
        <template #tab>
          <div class="flex items-center gap-2">
            <icon-tabler-table />
            <span>{{ $t("page.protocol.records.tableView") }}</span>
          </div>
        </template>

        <aimd-record-table
          v-model:selected-record-keys="selectedRecordKeys"
          v-model:field-keys="visibleFieldKeys"
          :aimd="protocolInfo.aimd"
          :records="recordList"
          :metadata-columns="metadataColumns"
          :record-key="getRecordKey"
          :record-label="getRecordLabel"
          :locale="locale"
          :selection-limit="4"
          @open-record="handleOpenRecord"
          @update:selected-record-keys="handleSelectedRecordKeysUpdate"
        >
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
      </n-tab-pane>

      <n-tab-pane name="compare" :disabled="selectedRecords.length < 2">
        <template #tab>
          <div class="flex items-center gap-2">
            <icon-tabler-arrows-diff />
            <span>{{ $t("page.protocol.records.compareView", { count: selectedRecords.length }) }}</span>
          </div>
        </template>

        <aimd-record-compare
          v-model:show-only-differences="showOnlyDifferences"
          :aimd="protocolInfo.aimd"
          :records="selectedRecords"
          :field-keys="visibleFieldKeys"
          :record-key="getRecordKey"
          :record-label="getRecordLabel"
          :locale="locale"
          @open-record="handleOpenRecord"
        />
      </n-tab-pane>
    </n-tabs>

    <div v-else-if="!loading" class="my-10 select-none text-center">
      <img
        src="/images/empty_placeholder.svg"
        alt="placeholder"
        class="pointer-events-none h-40 w-full object-contain"
      >
    </div>

    <n-pagination
      v-if="total > 0"
      class="my-5 w-full justify-center"
      :page="currentPage"
      :page-size="currentPageSize"
      :page-count="pageCount"
      @update:page="handlePageChange"
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
import { createProtocolRecordData } from "../utils"

interface Props {
  loading: boolean
  recordList: ProtocolModels.RecordInfo[]
  protocolInfo: ProtocolModels.ProjectProtocolInfo
  total: number
  latestRecordNumber?: number | null
  deleteGraceDays?: number
  isItemInChatContext: (id: string | number) => boolean
  isItemInChatContextDisabled: (id: string | number) => boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: "addToChat", item: ITimelineItem): void
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
const selectedRecordKeys = ref<AimdRecordViewKey[]>([])
const selectedRecordMap = shallowReactive(new Map<AimdRecordViewKey, ProtocolModels.RecordInfo>())
const showOnlyDifferences = ref(false)

const { currentPage, currentPageSize, handlePageChange, pageCount } = usePagination({
  options: { page: 1, pageSize: 10, total: computed(() => props.total) },
  fetchData: (payload) => {
    emit("fetchRecords", payload)
    return Promise.resolve()
  },
})

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

function handleJsonExport(key: string, value: unknown) {
  const record = value as ProtocolModels.RecordInfo
  const jsonData = JSON.stringify(record, null, 2)
  if (key === "download") {
    downloadAs(jsonData, `${getFilename(record)}.json`)
    message.success(t("page.protocol.timeline.downloadSuccess"))
  }
  else if (key === "copy") {
    copyToClip(jsonData)
    message.success(t("page.protocol.timeline.copySuccess"))
  }
  else if (key === "preview") {
    previewJsonData.value = jsonData
    previewJsonFilename.value = getFilename(record)
    showPreviewModal.value = true
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
.record-view-tabs :deep(.n-tabs-nav) {
  max-width: 420px;
  margin-bottom: 14px;
}

.record-row-actions {
  display: flex;
  align-items: center;
  gap: 2px;
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
  .record-view-tabs :deep(.n-tabs-nav) {
    max-width: none;
  }
}
</style>
