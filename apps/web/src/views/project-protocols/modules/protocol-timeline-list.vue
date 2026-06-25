<template>
  <base-timeline-list
    v-model:collapsed-item="collapsedItem"
    :list="list"
    class="mt-5 min-h-[375px] pl-20"
    content-class="-mt-2.5"
    @show-detail="emit('showReport', $event)"
  >
    <template #actions="{ item }">
      <n-tooltip v-if="isItemInChatContext(item.recordId!)" trigger="hover">
        {{ $t("page.protocol.timeline.removeFromChat") }}
        <template #trigger>
          <n-button class="h-8 w-8" type="error" :disabled="isItemInChatContextDisabled(item.recordId!)" @click="emit('removeFromChat', item)">
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
          <n-button class="h-8 w-8" @click="emit('addToChat', item)">
            <template #icon>
              <n-icon size="16">
                <icon-ion-add-outline />
              </n-icon>
            </template>
          </n-button>
        </template>
      </n-tooltip>
    </template>

    <template #content="{ item }">
      <timeline-list-item :item="item" :protocol-id="protocolInfo?.id" class="relative" :mode="recordMode">
        <template #header-suffix>
          <n-dropdown
            :options="jsonExportOptions"
            trigger="click"
            placement="bottom-start"
            @select="(key: string) => handleJsonExport(key, item)"
          >
            <div class="ml-auto">
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
            </div>
          </n-dropdown>
          <tooltip-button quaternary size="small" circle>
            <template #tooltip>
              <copy-to-clip-component :text="item.id" :button-props="{ color: 'white' }" show-success />
            </template>
            {{ $t("common.id") }}
          </tooltip-button>
          <n-button type="primary" quaternary @click="emit('showReport', item)">
            {{ $t("page.protocol.timeline.viewReport") }}
          </n-button>
          <n-button type="primary" quaternary @click="recordMode = 'preview'">
            {{ recordModeLabel }}
          </n-button>
          <n-tooltip v-if="canDeleteByRole(item)" :disabled="!getDeleteBlockedReason(item)">
            <template #trigger>
              <span class="inline-flex">
                <n-button
                  type="error"
                  quaternary
                  size="small"
                  :disabled="deleting || !!getDeleteBlockedReason(item)"
                  :class="{ 'opacity-50 cursor-not-allowed': !!getDeleteBlockedReason(item) }"
                  @click="handleDeleteClick(item)"
                >
                  <template #icon>
                    <n-icon size="16">
                      <icon-tabler-trash />
                    </n-icon>
                  </template>
                </n-button>
              </span>
            </template>
            {{ getDeleteBlockedReason(item) }}
          </n-tooltip>
        </template>
      </timeline-list-item>
    </template>
  </base-timeline-list>

  <!-- JSON Preview Modal -->
  <n-modal v-model:show="showPreviewModal" preset="card" :title="$t('page.protocol.timeline.jsonPreviewTitle', { name: previewJsonFilename })" class="max-w-6xl w-4/5" content-class="max-h-[70vh] overflow-auto" @after-leave="previewJsonData = ''">
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
import type { ITimelineItem } from "../types"
import BaseTimelineList from "@/components/common/base-timeline-list.vue"
import TimelineListItem from "@/components/common/protocol-timeline/timeline-list-item.vue"
import { DeleteConfirmationModal, useDeleteConfirmation } from "@/components/common/settings"
import { useProjectPermissions } from "@/composables"
import { deleteResearchRecord } from "@/service/api/project-protocols"
import { useAuthStore } from "@/store/modules/auth"
import CopyToClipComponent from "@airalogy/components/copy-to-clip.vue"
import ShikiCodeViewer from "@airalogy/components/file-preview/code-preview/shiki-code-viewer.vue"
import TooltipButton from "@airalogy/components/tooltip-button.vue"
import { useClosableMessage } from "@airalogy/composables"
import { copyToClip, downloadAs } from "@airalogy/shared/utils"
import dayjs from "dayjs"
import { useI18n } from "vue-i18n"
import { useProjectInfoStore } from "../hooks/useProjectInfoStore"
import { useProtocolInfoStore } from "../hooks/useProtocolInfoStore"

interface Props {
  list: ITimelineItem[]
  collapsedItem: Record<string | number, boolean>
  latestRecordNumber?: number | null
  deleteGraceDays?: number
  isItemInChatContext: (id: string | number) => boolean
  isItemInChatContextDisabled: (id: string | number) => boolean
}

const props = defineProps<Props>()

const emit = defineEmits<Emits>()

const message = useClosableMessage()
const { t, locale } = useI18n()

interface Emits {
  (e: "addToChat", item: ITimelineItem): void
  (e: "removeFromChat", item: ITimelineItem): void
  (e: "showReport", item: ITimelineItem): void
  (e: "update:collapsedItem", value: Record<string | number, boolean>): void
  (e: "recordDeleted"): void
}

const { protocolInfo } = useProtocolInfoStore()!
const { projectInfo } = useProjectInfoStore()
const authStore = useAuthStore()
const { canDeleteOthersRecords, canDeleteOwnRecords } = useProjectPermissions(projectInfo)
const collapsedItem = useVModel(props, "collapsedItem", emit)

// Preview modal state
const showPreviewModal = ref(false)
const previewJsonData = ref("")
const previewJsonFilename = ref("")

function getFilename(item: ITimelineItem) {
  const { lab, project, name } = protocolInfo.value || {}
  const { time, record } = item
  const { lab_id, project_id, protocol_id, record_num } = record?.metadata || {}
  const filename = [
    lab?.name || lab_id,
    project?.name || project_id,
    name || protocol_id,
    record_num && record_num > 1 ? `v${record_num}` : "",
    time,
  ].filter(Boolean).join("-")
  return filename
}

// JSON export functionality
const jsonExportOptions = computed(() => {
  return [
    {
      label: t("page.protocol.timeline.downloadJson"),
      key: "download",
    },
    {
      label: t("page.protocol.timeline.copyToClipboard"),
      key: "copy",
    },
    {
      label: t("page.protocol.timeline.previewJson"),
      key: "preview",
    },
  ]
})

function handleJsonExport(key: string, item: ITimelineItem) {
  const jsonData = JSON.stringify(item.record, null, 2)

  if (key === "download") {
    downloadAs(jsonData, `${getFilename(item)}.json`)
    message.success(t("page.protocol.timeline.downloadSuccess"))
  }
  else if (key === "copy") {
    copyToClip(jsonData)
    message.success(t("page.protocol.timeline.copySuccess"))
  }
  else if (key === "preview") {
    previewJsonData.value = jsonData
    previewJsonFilename.value = getFilename(item)
    showPreviewModal.value = true
  }
}

const recordMode = ref<"timeline" | "preview">("preview")
const recordModeLabel = computed(() => {
  return recordMode.value === "timeline"
    ? t("page.protocol.timeline.modeTimeline")
    : t("page.protocol.timeline.modePreview")
})

const deleteGraceDays = computed(() => {
  if (Number.isFinite(props.deleteGraceDays) && (props.deleteGraceDays as number) > 0) {
    return props.deleteGraceDays as number
  }
  return 7
})

function canDeleteByRole(item: ITimelineItem) {
  if (canDeleteOthersRecords.value) {
    return true
  }
  if (canDeleteOwnRecords.value && item.record?.metadata?.record_current_version_submission_user_id === authStore.userInfo.id) {
    return true
  }

  return false
}

function hasNewerRecord(item: ITimelineItem) {
  const currentNumber = item.record?.metadata?.record_num
  const latestNumber = props.latestRecordNumber
  if (currentNumber == null || latestNumber == null) {
    return false
  }
  return currentNumber < latestNumber
}

function isDeleteGraceExpired(item: ITimelineItem) {
  if (canDeleteOthersRecords.value) {
    return false
  }
  const createdAt = item.record?.metadata?.record_current_version_submission_time
  if (!createdAt) {
    return false
  }
  return dayjs().isAfter(dayjs(createdAt).add(deleteGraceDays.value, "day"))
}

function getDeleteBlockedReason(item: ITimelineItem) {
  if (!canDeleteByRole(item)) {
    return ""
  }
  if (isDeleteGraceExpired(item)) {
    return t("page.protocol.records.deleteBlockedExpired", { days: deleteGraceDays.value })
  }
  if (props.latestRecordNumber == null) {
    return t("page.protocol.records.deleteBlockedLoading")
  }
  if (hasNewerRecord(item)) {
    return t("page.protocol.records.deleteBlockedLatest")
  }
  return ""
}

function getDeleteAdminWarning(item: ITimelineItem) {
  if (!canDeleteOthersRecords.value) {
    return ""
  }
  return t("page.protocol.records.deleteAdminWarning", { days: deleteGraceDays.value })
}

const pendingDeleteItem = ref<ITimelineItem | null>(null)
const deleteItemName = computed(() => {
  const recordNum = pendingDeleteItem.value?.record?.metadata?.record_num
  const recordId = pendingDeleteItem.value?.recordId
  if (recordNum) {
    return `Record #${recordNum}`
  }
  return recordId ? String(recordId) : "Record"
})

const {
  showDeleteModal,
  deleteConfirmationText,
  deleting,
  isDeleteConfirmationValid,
  handleDelete: openDeleteModal,
  cancelDelete,
  confirmDelete,
} = useDeleteConfirmation(handleDeleteRecord, "Record", handleDeleteSuccess)

const deleteAdminWarning = computed(() => {
  if (!pendingDeleteItem.value) {
    return ""
  }
  return getDeleteAdminWarning(pendingDeleteItem.value)
})

function handleDeleteClick(item: ITimelineItem) {
  if (deleting.value) {
    return
  }
  const reason = getDeleteBlockedReason(item)
  if (reason) {
    message.warning(reason)
    return
  }
  pendingDeleteItem.value = item
  openDeleteModal()
}

function handleCancelDelete() {
  pendingDeleteItem.value = null
  cancelDelete()
}

async function handleDeleteRecord() {
  const protocolId = protocolInfo.value?.id
  const recordId = pendingDeleteItem.value?.recordId
  const recordVersion = pendingDeleteItem.value?.recordVersion
  if (!protocolId || !recordId || !recordVersion) {
    return { data: null, error: new Error("Wrong params") }
  }

  const { data, error } = await deleteResearchRecord(String(protocolId), String(recordId), recordVersion)
  return { data, error }
}

function handleDeleteSuccess() {
  pendingDeleteItem.value = null
  emit("recordDeleted")
}
</script>

<style scoped lang="sass">
:deep(.n-descriptions-table-header)
  width: 30%
</style>
