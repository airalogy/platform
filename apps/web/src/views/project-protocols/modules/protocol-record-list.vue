<template>
  <n-spin :show="loading" class="min-h-60">
    <protocol-timeline-list
      v-if="timelineList.length > 0"
      :list="timelineList"
      :collapsed-item="collapsedItem"
      :latest-record-number="props.latestRecordNumber"
      :delete-grace-days="props.deleteGraceDays"
      :is-item-in-chat-context="isItemInChatContext"
      :is-item-in-chat-context-disabled="isItemInChatContextDisabled"
      @add-to-chat="$emit('addToChat', $event)"
      @remove-from-chat="$emit('removeFromChat', $event)"
      @show-report="$emit('showReport', $event)"
      @record-deleted="$emit('recordDeleted')"
    />
    <div v-else-if="!loading" class="my-10 select-none text-center">
      <img
        src="/images/empty_placeholder.svg" alt="placeholder"
        class="pointer-events-none h-40 w-full object-contain"
      >
    </div>
    <n-pagination
      v-if="total > 0" class="my-5 w-full justify-center"
      :page="currentPage"
      :page-size="currentPageSize"
      :page-count="pageCount"
      @update:page="handlePageChange"
    />
  </n-spin>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types"
import type { ITimelineItem } from "../types"
import { usePagination } from "@/composables"
import { formatDate } from "@airalogy/shared/utils"
import { createProtocolRecordData } from "../utils"

import ProtocolTimelineList from "./protocol-timeline-list.vue"

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

const emit = defineEmits<Emits>()

interface Emits {
  (e: "addToChat", item: ITimelineItem): void
  (e: "removeFromChat", item: ITimelineItem): void
  (e: "showReport", item: ITimelineItem): void
  (e: "update:page", page: number): void
  (e: "fetchRecords", payload: { currentPage: number, currentPageSize: number }): void
  (e: "recordDeleted"): void
}

const collapsedItem = ref<Record<string | number, boolean>>({})

const { currentPage, currentPageSize, handlePageChange, pageCount } = usePagination({
  options: { page: 1, pageSize: 10, total: computed(() => props.total) },
  fetchData: (payload) => {
    emit("fetchRecords", payload)
    return Promise.resolve()
  },
})

function getRecordOrder(item: ProtocolModels.RecordInfo, index: number) {
  const recordNumber = item.metadata.record_num
  if (typeof recordNumber === "number") {
    return recordNumber
  }

  const pageOffset = (currentPage.value - 1) * currentPageSize.value
  return Math.max(props.total - pageOffset - index, 1)
}

const timelineList = computed((): ITimelineItem[] => {
  if (!props.protocolInfo)
    return []

  const list = props.recordList

  return list.reduce(
    (
      acc,
      item,
      idx,
    ): ITimelineItem[] => {
      const { airalogy_record_id, metadata, data, record_id, record_version } = item
      const { protocol_id, record_current_version_submission_user_id, protocol_version } = metadata

      const convertedData = createProtocolRecordData(data)
      // const parentItem = acc.find(it => it.recordId === record_id)

      const timelineItem: ITimelineItem = {
        id: airalogy_record_id,
        recordId: record_id,
        operator: record_current_version_submission_user_id,
        operatorId: record_current_version_submission_user_id,
        operatorUsername: record_current_version_submission_user_id,
        // order: parentItem ? `${parentItem.order}-${record_version}` : props.total - idx,
        order: getRecordOrder(item, idx),
        field: convertedData,
        protocolId: protocol_id,
        record: item,
        protocolVersion: protocol_version,
        recordVersion: record_version,
        time: formatDate(metadata.record_current_version_submission_time, "date-time"),
      }

      acc.push(timelineItem)
      return acc
    },
    [] as ITimelineItem[],
  )
})

watch(timelineList, (list) => {
  const previous = collapsedItem.value
  collapsedItem.value = list.reduce(
    (acc, item) => {
      const { id } = item
      acc[id] = id in previous ? previous[id] : true

      return acc
    },
    {} as Record<string | number, boolean>,
  )
}, { immediate: true })
</script>

<style scoped lang="sass">
:deep(.n-timeline-item-timeline__circle)
  background-color: #1A79FF
  border: 3px solid #EDF4FF!important
  outline: 4px solid #FFFFFF
  box-shadow: 0 0 0 6px #E7EFFF
  position: relative
  &::before
    content: ''
    position: absolute
    top: var(--item-top, -7px)
    left: calc(50% - 1px)
    bottom: var(--item-bottom, -7px)
    width: 2px
    background-color: rgba(26, 121, 255, 0.3)
    box-shadow: 0 0 5px 0px rgba(26, 121, 255, 1)

:deep(.n-timeline-item-timeline__line)
  top: calc(var(--n-icon-size) + 4px)!important
:deep(.n-timeline .n-timeline-item:last-child .n-timeline-item-timeline .n-timeline-item-timeline__line)
  border-radius: 0 0 50% 50%
  background: linear-gradient(to bottom, #1A79FF, transparent)
  display: block

:deep(.n-descriptions-table-header)
  width: 30%
</style>
