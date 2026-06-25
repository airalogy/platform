<template>
  <div>
    <tab-search-input active-tab="discussion" @submit:search="handleDiscussionSearch" @update:filters="handleFilterUpdate" />

    <discussion-result-list :list="discussionResults" />
  </div>
</template>

<script setup lang="ts">
import { getSearchResearchNode, mockExpertiseResults } from "@/service/api/search"
import { useClosableMessage } from "@airalogy/composables"
import DiscussionResultList from "./components/discussion-result-list.vue"
import TabSearchInput from "./components/tab-search-input.vue"

const message = useClosableMessage()
const discussionResults = ref<Api.Search.DiscussionSearchItem[]>(mockExpertiseResults)

async function handleDiscussionSearch(query: string) {
  try {
    const data = await getSearchResearchNode({
      id: "discussion",
      type: "discussion",
      query,
      page: 1,
      pageSize: 20,
    })
    if (data?.data) {
      discussionResults.value = data.data as any
    }
  }
  catch (e) {
    message.error((e as Error).message)
  }
  return null
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
