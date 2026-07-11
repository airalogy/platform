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
      <n-grid
        v-if="protocolInfo && protocolInfo.lab && protocolInfo.project && protocolInfo.uid"
        cols="12"
        :x-gap="16"
        :y-gap="8"
        class="px-4"
      >
        <n-grid-item :span="6">
          <div class="flex gap-3">
            <search-input
              v-model:value="searchInputVal"
              class="flex-1"
              icon-position="right"
              :placeholder="$t('page.protocol.records.searchContentPlaceholder')"
              @submit:search="handleSearch('input')"
              @clear="handleSearch('clear')"
            />
            <global-add-member
              v-if="authStore.isLogin"
              size="medium"
              :filter-user="false"
              :theme-overrides="selectThemeOverrides"
              @update:select="handleUserSelect"
            />
          </div>
        </n-grid-item>
        <n-grid-item :span="12" class="flex justify-end gap-4">
          <n-button
            quaternary
            type="primary"
            :loading="loadingState.search"
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
        </n-grid-item>
        <!-- Advanced Search Panel -->
        <n-grid-item :span="12">
          <n-collapse-transition :show="showAdvancedSearch">
            <div class="mb-4">
              <label class="mb-2 block text-sm text-gray-700 font-medium">
                {{ $t("page.protocol.records.searchRecordNumber") }}
              </label>
              <n-input-number
                v-model:value="recordNumberInput"
                :placeholder="$t('page.protocol.records.recordNumberPlaceholder')"
                :min="1"
                @keydown.enter="handleSearch('recordVersion')"
              />
            </div>
            <div class="mb-4">
              <label class="mb-2 block text-sm text-gray-700 font-medium">
                {{ $t("page.protocol.records.searchRecordVersion") }}
              </label>
              <n-input-number
                v-model:value="recordVersionInput"
                :placeholder="$t('page.protocol.records.recordVersionPlaceholder')"
                :min="1"
                @keydown.enter="handleSearch('recordVersion')"
              />
            </div>
            <global-sort-selector
              v-model="protocolVersionOption"
              :options="protocolVersionOptions"
              :loading="loadingState.versions"
              :label="$t('page.protocol.records.protocolVersionLabel')"
              class="w-full"
              @update:value="handleSearch('version')"
              @update:show="fetchProtocolVersions"
            />
            <div class="mt-4 flex gap-2">
              <n-button
                type="primary"
                :loading="loadingState.search"
                @click="handleSearch('apply')"
              >
                {{ $t("page.protocol.records.applyFilters") }}
              </n-button>
              <n-button :loading="loadingState.search" @click="handleClearFilters">
                {{ $t("page.protocol.records.clearAll") }}
              </n-button>
            </div>
          </n-collapse-transition>
        </n-grid-item>
      </n-grid>
      <protocol-record-list
        v-if="protocolInfo"
        :loading="loadingState.records"
        :record-list="recordList"
        :protocol-info="protocolInfo"
        :total="total"
        :latest-record-number="latestRecordNumber"
        :delete-grace-days="deleteGraceDays"
        :is-item-in-chat-context="isItemInChatContext"
        :is-item-in-chat-context-disabled="isItemInChatContextDisabled"
        @add-to-chat="handleAddToChat"
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
import type { ICustomSelectOption } from "@/components/common/global-add-member.vue"
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

defineOptions({ inheritAttrs: false })

const { protocolInfo, airalogyId, protocolId } = useOrProvideProtocolInfoStore(null)
const { projectInfo } = useOrProvideProjectInfoStore(null)
const authStore = useAuthStore()

const { endLoading, fetchProtocolRecords, loading } = useFetchProtocolRecords()
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
const lastFetchPayload = ref<{ currentPage: number, currentPageSize: number }>({
  currentPage: 1,
  currentPageSize: 10,
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
const selectedUsers = ref<ICustomSelectOption[]>([])
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

function handleShowReport(item: ITimelineItem) {
  const { recordId, recordVersion = 1, protocolVersion } = item

  const { uid, lab, project } = protocolInfo.value || {}
  if (!uid || !lab?.uid || !project?.uid || !recordId || !protocolVersion) {
    return
  }

  routerPushByKey("protocol-record-report", {
    params: {
      recordId,
      recordVersion: String(recordVersion),
      protocolUid: uid,
      labUid: lab.uid,
      projectUid: project.uid,
      protocolVersion,
    },
  })
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

async function handleSearch(
  source: "input" | "clear" | "version" | "apply" | "clearFilters" | "recordVersion",
) {
  startTargetLoading("search")
  try {
    // Reset to first page when searching
    await handleFetchRecords({ currentPage: 1, currentPageSize: 10 })
  }
  finally {
    endTargetLoading("search")
  }
}

function handleUserSelect(users: ICustomSelectOption[]) {
  selectedUsers.value = users
  // Trigger search when users are selected
  handleSearch("apply")
}

function handleClearFilters() {
  searchInputVal.value = ""
  protocolVersionOption.value = "all"
  selectedUsers.value = []
  showAdvancedSearch.value = false
  recordNumberInput.value = null
  recordVersionInput.value = null

  // Trigger search with cleared filters
  handleSearch("clear")
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

    // Add user ID filter from selected users
    if (selectedUsers.value.length > 0) {
      // For now, use the first selected user ID (API supports single userId)
      searchParams.userId = selectedUsers.value[0].value
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
    endLoading()
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

function handleAddToChat(item: ITimelineItem) {
  const { recordId, record } = item
  const target = record || recordList.value.find(it => it.record_id === recordId)

  if (!protocolInfo.value || !recordId || !target)
    return

  startTargetLoading("chat")
  try {
    const { lab, project, uid, name, id } = protocolInfo.value
    const recordKey = String(recordId)
    const newItem: Chat.ChatRecordContext = {
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
      id: recordKey,
      airalogyId: target.airalogy_record_id,
      isLocal: false,
      removable: true,
    }

    // Get current context and add new item if not already present
    const currentContext = toValue(context) || []
    if (currentContext.findIndex(item => String(item.id) === recordKey) === -1) {
      const newContext = [...currentContext, newItem]
      updateContext(newContext)
    }
  }
  finally {
    endTargetLoading("chat")
  }
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
      currentPageSize: 10,
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
