<template>
  <split-layout
    :chat-props="{
      contextSelectOptions,
      chatId: undefined,
      source: 'record',
      airalogyId,
      role: ChatType.RECORDS,
    }"
    default-selected-tab="ai-assistant"
  >
    <section>
      <div
        v-if="protocolInfo && protocolInfo.lab && protocolInfo.project && protocolInfo.uid"
        class="px-4"
      >
        <div class="flex flex-col gap-3 xl:flex-row xl:items-center">
          <search-input
            v-model:value="searchInputVal"
            class="min-w-64 flex-1"
            icon-position="right"
            :placeholder="$t('page.protocol.records.searchContentPlaceholder')"
            @submit:search="handleSearch"
            @clear="handleSearch"
          />

          <div class="flex flex-wrap items-center justify-end gap-3">
            <n-button
              quaternary
              type="primary"
              :loading="loadingState.search"
              :aria-expanded="showAdvancedSearch"
              @click="showAdvancedSearch = !showAdvancedSearch"
            >
              <template #icon>
                <n-icon>
                  <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M3 4H21V6H3V4ZM9 11V13H15V11H9ZM6 18V16H18V18H6Z" fill="currentColor" />
                  </svg>
                </n-icon>
              </template>
              {{ $t("page.protocol.records.advancedSearch") }}
            </n-button>

            <bulk-import-records-modal
              v-if="canSubmitDataToOthers"
              :protocol-id="protocolInfo.id"
              @imported="handleRecordsImported"
            />

            <add-log-modal
              v-if="canSubmitDataToOthers"
              :lab-uid="protocolInfo.lab.uid"
              :project-uid="protocolInfo.project.uid"
              :protocol-uid="protocolInfo.uid"
              :loading="loadingState.create"
              @modal:new-record="handleCreateRecord"
            />
          </div>
        </div>

        <n-collapse-transition :show="showAdvancedSearch">
          <div class="mt-3 border-y border-gray-200 py-4">
            <div class="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-4">
              <div v-if="authStore.isLogin">
                <label class="mb-2 block text-sm text-gray-700 font-medium">
                  {{ $t("page.protocol.records.submittedBy") }}
                </label>
                <global-add-member
                  v-model:value="selectedUserId"
                  class="w-full"
                  size="medium"
                  :multiple="false"
                  :filter-user="false"
                  :placeholder="$t('page.protocol.records.submitterSearchPlaceholder')"
                  :theme-overrides="selectThemeOverrides"
                />
              </div>

              <div>
                <label class="mb-2 block text-sm text-gray-700 font-medium">
                  {{ $t("page.protocol.records.searchRecordNumber") }}
                </label>
                <n-input-number
                  v-model:value="recordNumberInput"
                  class="w-full"
                  :placeholder="$t('page.protocol.records.recordNumberPlaceholder')"
                  :min="1"
                  @keydown.enter="handleSearch"
                />
              </div>

              <div>
                <label class="mb-2 block text-sm text-gray-700 font-medium">
                  {{ $t("page.protocol.records.searchRecordVersion") }}
                </label>
                <n-input-number
                  v-model:value="recordVersionInput"
                  class="w-full"
                  :placeholder="$t('page.protocol.records.recordVersionPlaceholder')"
                  :min="1"
                  @keydown.enter="handleSearch"
                />
              </div>

              <global-sort-selector
                v-model="protocolVersionOption"
                :options="protocolVersionOptions"
                :loading="loadingState.versions"
                :label="$t('page.protocol.records.protocolVersionLabel')"
                class="w-full"
                @update:show="fetchProtocolVersions"
              />
            </div>

            <div class="mt-4 flex gap-2">
              <n-button
                type="primary"
                :loading="loadingState.search"
                @click="handleSearch"
              >
                {{ $t("page.protocol.records.applyFilters") }}
              </n-button>
              <n-button :loading="loadingState.search" @click="handleClearFilters">
                {{ $t("page.protocol.records.clearAll") }}
              </n-button>
            </div>
          </div>
        </n-collapse-transition>
      </div>
      <protocol-record-list
        v-if="protocolInfo"
        :loading="loadingState.records"
        :record-list="recordList"
        :protocol-info="protocolInfo"
        :total="total"
        :latest-record-number="latestRecordNumber"
        :delete-grace-days="deleteGraceDays"
        :initial-page-size="preferredRecordPageSize"
        :is-item-in-chat-context="isItemInChatContext"
        :is-item-in-chat-context-disabled="isItemInChatContextDisabled"
        @add-to-chat="handleAddToChat"
        @add-selected-to-chat="handleAddSelectedToChat"
        @remove-from-chat="handleRemoveFromChat"
        @show-report="handleShowReport"
        @fetch-records="handleFetchRecords"
        @record-deleted="handleRecordDeleted"
      />
      <show-report-modal :record="currentRecordData" :aimd="protocolInfo?.aimd" @update:show="handleUpdateShow" />
    </section>
  </split-layout>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types"

import type { SelectOption } from "naive-ui"
import type { ITimelineItem } from "./types"
import GlobalAddMember from "@/components/common/global-add-member.vue"
import GlobalSortSelector from "@/components/common/global-sort-selector.vue"
import SearchInput from "@/components/common/search-input.vue"
import { useProjectPermissions } from "@/composables"
import { useRouterPush } from "@/composables/useRouterPush"
import { getProtocolVersions } from "@/service/api/protocol"
import { useAppStore } from "@/store/modules/app"
import { useAuthStore } from "@/store/modules/auth"
import { getRecordDeleteGraceDays } from "@/utils/env"

import { useOrProvideChatInfoStore } from "@airalogy/components/chat/composables/useChatInfoStore"

import { useClosableMessage, useLoading } from "@airalogy/composables"
import { ChatType } from "@airalogy/shared/enum"
import { formatDate } from "@airalogy/shared/utils"
import { useI18n } from "vue-i18n"
import { useFetchProtocolRecords } from "./hooks/index"
import { useOrProvideProjectInfoStore } from "./hooks/useProjectInfoStore"
import { useOrProvideProtocolInfoStore } from "./hooks/useProtocolInfoStore"
import SplitLayout from "./layout/split-layout.vue"
import AddLogModal from "./modules/add-log-modal.vue"
import BulkImportRecordsModal from "./modules/bulk-import-records-modal.vue"
import ProtocolRecordList from "./modules/protocol-record-list.vue"
import ShowReportModal from "./modules/show-report-modal.vue"
import { getRecordPageSizePreference } from "./record-view-preferences"

defineOptions({ inheritAttrs: false })

const { protocolInfo, airalogyId, protocolId } = useOrProvideProtocolInfoStore(null)
const { projectInfo } = useOrProvideProjectInfoStore(null)
const authStore = useAuthStore()

const { fetchProtocolRecords } = useFetchProtocolRecords()
const { canSubmitDataToOthers } = useProjectPermissions(projectInfo)
const { reloadPage } = useAppStore()

// Initialize loading states for different operations
const { loadingState, startTargetLoading, endTargetLoading } = useLoading(false, [
  "records",
  "versions",
  "search",
  "create",
  "chat",
])

const message = useClosableMessage()
const { t, locale } = useI18n()

const recordList = ref<ProtocolModels.RecordInfo[]>([])
const total = ref<number>(0)
const latestRecordNumber = ref<number | null>(null)
const preferredRecordPageSize = computed(() => getRecordPageSizePreference(authStore.userInfo.id))
const lastFetchPayload = ref<{ currentPage: number, currentPageSize: number }>({
  currentPage: 1,
  currentPageSize: preferredRecordPageSize.value,
})

const deleteGraceDays = computed(() => getRecordDeleteGraceDays())

const currentRecordData = ref<ProtocolModels.RecordInfo | null>(null)
const { routerPushByKey } = useRouterPush()

const selectThemeOverrides = {
  peers: {
    InternalSelection: {
      heightMedium: "36px",
      fontSizeMedium: "14px",
      borderRadius: "8px",
      paddingMedium: "0 12px",
      color: "transparent",
    },
    InternalSelectMenu: {
      borderRadius: "6px",
    },
  },
}
// Search functionality variables
const searchInputVal = ref("")
const protocolVersionOption = ref<string>("all")
const selectedUserId = ref<string | null>(null)
const recordNumberInput = ref<number | null>(null)
const recordVersionInput = ref<number | null>(null)

const protocolVersions = ref<string[]>([])
const protocolVersionOptions = computed<SelectOption[]>(() => {
  const options: SelectOption[] = [{ label: t("common.allVersions"), value: "all" }]
  protocolVersions.value.forEach((version) => {
    options.push({
      label: t("common.versionWithNumber", { version }),
      value: version,
    })
  })
  return options
})

// Advanced search state
const showAdvancedSearch = ref(false)

async function fetchLatestRecordNumber() {
  if (!protocolInfo.value?.id) {
    return
  }
  try {
    const data = await fetchProtocolRecords(protocolInfo.value.id, { page: 1, pageSize: 1 })
    const latest = data?.records?.[0]?.metadata?.record_num
    latestRecordNumber.value = typeof latest === "number" ? latest : null
  }
  catch {
    latestRecordNumber.value = null
  }
}

function handleUpdateShow(show: boolean) {
  if (!show) {
    currentRecordData.value = null
  }
}

async function handleShowReport(item: ITimelineItem) {
  const record = item.record
  const metadata = record?.metadata
  const recordId = item.recordId || record?.record_id
  const recordVersion = item.recordVersion || record?.record_version || 1
  const protocolVersion = item.protocolVersion || metadata?.protocol_version
  const protocolUid = protocolInfo.value?.uid || metadata?.protocol_id || metadata?.airalogy_protocol_id
  const labUid = protocolInfo.value?.lab?.uid || metadata?.lab_id
  const projectUid = protocolInfo.value?.project?.uid || metadata?.project_id

  if (!protocolUid || !labUid || !projectUid || !recordId || !protocolVersion) {
    if (record) {
      currentRecordData.value = record
    }
    return
  }

  try {
    await routerPushByKey("protocol-record-report", {
      params: {
        recordId,
        recordVersion: String(recordVersion),
        protocolUid,
        labUid,
        projectUid,
        protocolVersion,
      },
    })
  }
  catch (error) {
    console.error("Failed to open record report:", error)
    if (record) {
      currentRecordData.value = record
    }
  }
}

async function handleCreateRecord() {
  startTargetLoading("create")
  try {
    await reloadPage(10)
  }
  finally {
    endTargetLoading("create")
  }
}

async function handleSearch() {
  startTargetLoading("search")
  try {
    // Reset to first page when searching
    await handleFetchRecords({
      currentPage: 1,
      currentPageSize: lastFetchPayload.value.currentPageSize,
    })
  }
  finally {
    endTargetLoading("search")
  }
}

function handleClearFilters() {
  searchInputVal.value = ""
  protocolVersionOption.value = "all"
  selectedUserId.value = null
  showAdvancedSearch.value = false
  recordNumberInput.value = null
  recordVersionInput.value = null

  // Trigger search with cleared filters
  handleSearch()
}

async function handleFetchRecords(payload: { currentPage: number, currentPageSize: number }) {
  if (!protocolInfo.value || !protocolInfo.value.id) {
    return
  }

  lastFetchPayload.value = payload
  startTargetLoading("records")
  try {
    const { currentPage, currentPageSize } = payload

    // Build search parameters with only supported options
    const searchParams: {
      page: number
      pageSize: number
      protocolVersion?: string
      number?: number
      version?: string
      userId?: string
      q?: string
    } = {
      page: currentPage,
      pageSize: currentPageSize,
    }

    // Add protocol version filter
    if (protocolVersionOption.value !== "all") {
      searchParams.protocolVersion = protocolVersionOption.value
    }

    // Add record number search
    if (recordNumberInput.value) {
      searchParams.number = recordNumberInput.value
    }

    if (searchInputVal.value.trim()) {
      searchParams.q = searchInputVal.value.trim()
    }

    // Add record version search from advanced panel
    if (recordVersionInput.value) {
      searchParams.version = String(recordVersionInput.value)
    }

    // Add submitter filter
    if (selectedUserId.value) {
      searchParams.userId = selectedUserId.value
    }

    const data = await fetchProtocolRecords(protocolInfo.value.id, searchParams)
    if (data && Array.isArray(data.records)) {
      const { records, total_count } = data

      recordList.value = records
      total.value = total_count
    }
    void fetchLatestRecordNumber()
  }
  catch (e) {
    // NOPE
    message.error((e as Error).message)
  }
  finally {
    endTargetLoading("records")
  }
}

async function handleRecordDeleted() {
  await fetchLatestRecordNumber()
  await handleFetchRecords(lastFetchPayload.value)
}

async function handleRecordsImported() {
  await fetchLatestRecordNumber()
  await handleFetchRecords(lastFetchPayload.value)
}

function getRecordDisplayOrder(record: ProtocolModels.RecordInfo, index: number) {
  const recordNumber = record.metadata.record_num
  if (typeof recordNumber === "number") {
    return recordNumber
  }

  const pageOffset = (lastFetchPayload.value.currentPage - 1) * lastFetchPayload.value.currentPageSize
  return Math.max(total.value - pageOffset - index, 1)
}

const contextSelectOptions = computed((): SelectOption[] => {
  return recordList.value.map((record, index): SelectOption => {
    const { record_id } = record
    const order = getRecordDisplayOrder(record, index)
    const time = formatDate(record.metadata.record_current_version_submission_time, "date-time")

    return {
      label: `# ${order} (id: ${record_id}) - ${time}`,
      value: record_id,
      info: { raw: record, tag: `#${order} (id: ${record_id})` },
    }
  })
})

// const chatState = useChatState(chatProps, true)
// const { updateContext } = useChatMutations(chatState)
const { updateContext, context } = useOrProvideChatInfoStore(
  {
    contextSelectOptions,
    source: ref("record"),
    airalogyId,
    protocolId,
    role: ref(ChatType.RECORDS),
  },
  () => {},
)

function isItemInChatContext(id: string | number) {
  const contextValue = toValue(context)
  if (!Array.isArray(contextValue)) {
    return false
  }

  const targetId = String(id)
  return contextValue.some(item => String(item.id) === targetId)
}

function isItemInChatContextDisabled(id: string | number) {
  const contextValue = toValue(context)

  if (!Array.isArray(contextValue)) {
    return false
  }

  const targetId = String(id)
  const target = contextValue.find(item => String(item.id) === targetId)

  if (target?.removable) {
    return false
  }

  return true
}

function createRecordChatContext(item: ITimelineItem): Chat.ChatRecordContext | null {
  const { recordId, record } = item
  const target = record || recordList.value.find(it => it.record_id === recordId)

  if (!protocolInfo.value || !recordId || !target)
    return null

  const { lab, project, uid, name, id } = protocolInfo.value
  return {
    ...target,
    lab,
    project,
    protocol: {
      uid,
      name,
      id,
    },
    item: target,
    type: "record",
    id: String(recordId),
    airalogyId: target.airalogy_record_id,
    isLocal: false,
    removable: true,
  }
}

function handleAddSelectedToChat(items: ITimelineItem[]) {
  if (items.length === 0)
    return

  startTargetLoading("chat")
  try {
    const currentContext = toValue(context) || []
    const contextIds = new Set(currentContext.map(item => String(item.id)))
    const newItems: Chat.ChatRecordContext[] = []

    for (const item of items) {
      const newItem = createRecordChatContext(item)
      if (newItem && !contextIds.has(String(newItem.id))) {
        contextIds.add(String(newItem.id))
        newItems.push(newItem)
      }
    }

    if (newItems.length > 0) {
      updateContext([...currentContext, ...newItems])
    }
  }
  finally {
    endTargetLoading("chat")
  }
}

function handleAddToChat(item: ITimelineItem) {
  handleAddSelectedToChat([item])
}

function handleRemoveFromChat(item: ITimelineItem) {
  const { id, recordId } = item

  startTargetLoading("chat")
  try {
    // Get current context and remove the item
    const currentContext = toValue(context) || []
    const targetId = String(id ?? "")
    const targetRecordId = String(recordId ?? "")
    const newContext = currentContext.filter(
      it => String(it.id) !== targetId && String(it.id) !== targetRecordId,
    )
    updateContext(newContext)
  }
  finally {
    endTargetLoading("chat")
  }
}

watch(
  () => protocolInfo.value?.id,
  async (id) => {
    if (!id) {
      return
    }

    await handleFetchRecords({
      currentPage: 1,
      currentPageSize: lastFetchPayload.value.currentPageSize,
    })
  },
  { immediate: true },
)

// Fetch protocol versions from API
async function fetchProtocolVersions() {
  if (!protocolInfo.value?.id)
    return

  startTargetLoading("versions")
  try {
    const { data } = await getProtocolVersions(protocolInfo.value.id, { page: 1, pageSize: 100 })
    if (data?.versions) {
      protocolVersions.value = data.versions.map((version: any) => String(version.version))
    }
  }
  catch (error) {
    console.error("Failed to fetch protocol versions:", error)
  }
  finally {
    endTargetLoading("versions")
  }
}
</script>

<style scoped lang="sass"></style>
