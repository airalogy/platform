<template>
  <div v-if="loading" class="h-full flex items-center justify-center">
    <n-spin size="medium" />
  </div>
  <div v-else-if="error" class="h-full flex items-center justify-center text-gray-500">
    {{ error }}
  </div>
  <div v-else-if="timelineList.length > 0" class="px-2 py-6 space-y-4">
    <base-timeline-list
      :list="timelineList"
      :collapsed-item="collapsedItem"
      class="min-h-[375px] pl-14"
      @show-detail="handleSelect"
    >
      <template #prefix="{ item }">
        <span class="mr-2">#</span>{{ item.order }}
      </template>

      <template #header="{ item }">
        <tooltip-button
          :tooltip="item.airalogy_id"
          class="absolute top-0.5"
          text
          type="default"
          size="tiny"
          :icon="CopyIcon"
          @click="handleCopy(item.airalogy_id)"
        />
        <n-popover trigger="click">
          <template #trigger>
            <n-button
              class="absolute-tr z-100 -top-2.5"
              type="primary"
              quaternary
              icon-placement="right"
              @click="handleSelect(item)"
            >
              <template #icon>
                <n-icon>
                  <icon-local-dropdown-outline />
                </n-icon>
              </template>
              {{ $t("common.more") }}
            </n-button>
          </template>
          <protocol-metadata-display :metadata="item.metadata" />
        </n-popover>
      </template>

      <template #content="{ item }">
        <div class="space-y-2">
          <div class="flex items-center gap-2">
            <span class="truncate text-sm text-gray-900 font-medium">
              {{ item.name || 'Untitled' }}
            </span>
            <n-tag size="tiny" :bordered="false">
              v{{ item.version }}
            </n-tag>
          </div>

          <div class="flex items-center gap-2 text-xs text-gray-500">
            <n-time :time="dayjs(item.created_at).toDate()" type="relative" />
            <!-- <span>by {{ item.user?.name || item.authorName }}</span> -->
            <span v-if="item.user">{{ $t("common.by") }} {{ item.user.name }}</span>
            <n-skeleton v-else class="w-10" />
          </div>
          <!--
            <div class="mt-2 flex items-center gap-2">
              <n-button
                size="small"
                @click.stop="handleRestore(item)"
              >
                Restore
              </n-button>
            </div> -->
        </div>
      </template>
    </base-timeline-list>
  </div>
  <div v-else class="h-full flex items-center justify-center text-gray-500">
    No history protocols
  </div>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types"
import BaseTimelineList from "@/components/common/base-timeline-list.vue"
import ProtocolMetadataDisplay from "@/components/protocol/protocol-metadata-display.vue"
import { usePagination } from "@/composables"
import { getProtocolHistory } from "@/service/api/protocol"
import TooltipButton from "@airalogy/components/tooltip-button.vue"
import { useClosableMessage } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import { copyToClip } from "@airalogy/shared/utils"
import CopyIcon from "~icons/tabler/copy"
import dayjs from "dayjs"
import { computed, ref } from "vue"
import { useProtocolInfoStore } from "../../hooks/useProtocolInfoStore"

interface ProtocolTimelineItem {
  id: string
  airalogy_id: string
  time: string | number
  order: number
  name: string
  version: string
  created_at: string
  authorName: string
  authors: ProtocolModels.ProtocolPerson[]
  metadata: ProtocolModels.ProtocolMetaData
  user: { name: string, username: string, id: string }
}

const { protocolInfo, memoizedGetProtocolInfo } = useProtocolInfoStore()!

const protocolId = computed(() => protocolInfo.value?.id || null)
const historyList = ref<ProtocolModels.ProtocolVersion[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const collapsedItem = ref<Record<string | number, boolean>>({})
const message = useClosableMessage()

const { currentPage, currentPageSize, offset } = usePagination({
  options: {
    pageSize: 10,
    onPageChange: fetchProtocolHistory,
  },
})
const userRecord = ref<Record<string, ProtocolTimelineItem["user"]>>(protocolInfo.value ? { [protocolInfo.value.id]: protocolInfo.value.user } : {})

const timelineList = computed<ProtocolTimelineItem[]>(() => {
  return historyList.value.map((item, index) => {
    const { id, version, created_at, meta_data, airalogy_id } = item

    return {
      id,
      airalogy_id,
      name: meta_data.name,
      version,
      created_at,
      time: dayjs(created_at).valueOf(),
      order: offset.value.start + index + 1,
      authorName: meta_data.authors?.[0].name,
      authors: meta_data.authors,
      metadata: meta_data,
      user: userRecord.value[id],
    } satisfies ProtocolTimelineItem
  })
})

function handleCopy(content: string) {
  if (!content) {
    return
  }
  copyToClip(content)
  message.success("Copied to clipboard")
}

async function fetchProtocolHistory({ currentPage: currPage, currentPageSize: currPageSize }: { currentPage: number, currentPageSize: number }) {
  if (!protocolId.value) {
    error.value = "Protocol ID is missing"
    return
  }

  loading.value = true
  error.value = null

  try {
    const res = await getProtocolHistory({ id: protocolId.value, page: currPage, pageSize: currPageSize })

    if (res?.versions) {
      historyList.value = res.versions
    }
  }
  catch (err) {
    console.error("Failed to fetch protocol history:", err)
    error.value = "Failed to load protocol history"
  }
  finally {
    loading.value = false
  }
}

function handleSelect(item: ProtocolTimelineItem) {
  // Handle selection
  console.log("Selected:", item)
}

function handleRestore(item: ProtocolTimelineItem) {
  // Handle restore
  console.log("Restore:", item)
}

watch(() => protocolId.value, async (id) => {
  if (!id) {
    return
  }

  await fetchProtocolHistory({ currentPage: currentPage.value, currentPageSize: currentPageSize.value })
}, { immediate: true })

watch(historyList, (val) => {
  if (!val || !val.length) {
    return
  }

  const record = userRecord.value
  val.forEach(async ({ id, protocol_id, version }) => {
    if (record[id]) {
      return
    }
    const res = await memoizedGetProtocolInfo(protocol_id, version)

    const info = res?.data
    if (info) {
      record[id] = info.user
    }
  })
})
</script>

<style scoped lang="sass">
:deep(.n-collapse-item__header)
  font-size: 14px
  font-weight: 500

:deep(.n-tag)
  background-color: var(--x-10)
  color: var(--wck-qds)
</style>
