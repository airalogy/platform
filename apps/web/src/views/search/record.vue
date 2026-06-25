<template>
  <div>
    <tab-search-input active-tab="record" @submit:search="handleRecordSearch" @update:filters="handleFilterUpdate" />

    <record-result-list :list="recordResults" />
  </div>
</template>

<script setup lang="ts">
import type { ICustomSelectOption } from "../../components/common/global-add-member.vue"
import { getSearchResearchNode, mockRecordResults } from "@/service/api/search"
import { useClosableMessage } from "@airalogy/composables"
import RecordResultList from "./components/record-result-list.vue"
import TabSearchInput from "./components/tab-search-input.vue"

const message = useClosableMessage()
const activeTab = ref<"protocol" | "record" | "discussion">("record")

// Record search
const recordResults = ref<Api.Search.RecordSearchItem[]>(mockRecordResults)
const recordDateRange = ref<[number, number] | null>(null)
const selectedMembers = ref<ICustomSelectOption[]>([])

async function handleRecordSearch(query: string) {
  try {
    const data = await getSearchResearchNode({
      id: "record",
      type: "record",
      query,
      page: 1,
      pageSize: 20,
      filters: {
        dateRange: recordDateRange.value,
        userIds: selectedMembers.value.map(m => m.value),
      },
    })
    if (data?.data) {
      return data.data
    }
  }
  catch (e) {
    message.error((e as Error).message)
  }
  return null
}

function handleRecordResult(data: { data: Api.Search.RecordSearchItem[] }) {
  recordResults.value = data.data
}

function handleFilterUpdate(filters: {
  dateRange?: [number, number] | null
  userIds?: string[]
  tags?: string[]
}) {
}
</script>

<style scoped>
</style>
