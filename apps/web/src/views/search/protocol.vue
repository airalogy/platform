<template>
  <div>
    <tab-search-input active-tab="protocol" @submit:search="handleProtocolSearch" @update:filters="handleFilterUpdate" />
    <protocol-result-list :list="protocolResults" />
  </div>
</template>

<script setup lang="ts">
import { getSearchResearchNode, mockProtocolResults } from "@/service/api/search"
import { useClosableMessage } from "@airalogy/composables"
import ProtocolResultList from "./components/protocol-result-list.vue"
import TabSearchInput from "./components/tab-search-input.vue"

const message = useClosableMessage()
const activeTab = ref<"protocol" | "record" | "discussion">("protocol")

const protocolResults = ref<Api.Search.ProtocolSearchItem[]>(mockProtocolResults)
async function handleProtocolSearch(query: string) {
  try {
    const data = await getSearchResearchNode({
      id: "protocol",
      type: "protocol",
      query,
      page: 1,
      pageSize: 20,
    })
    if (data?.data) {
      return { data: data.data.data, total_count: data.data.total_count }
    }
  }
  catch (e) {
    message.error((e as Error).message)
  }
  return null
}

function handleProtocolResult(data: { data: Api.Search.ProtocolSearchItem[] }) {
  protocolResults.value = data.data
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
