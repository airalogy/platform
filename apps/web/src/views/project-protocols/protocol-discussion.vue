<template>
  <split-layout
    :chat-props="{ source: 'discussion', airalogyId, role: ChatType.NORMAL }"
    content-class="pl-4 flex flex-col"
    default-selected-tab="ai-assistant"
  >
    <n-flex class="mb-4 w-full" justify="space-between">
      <search-result />
      <ask-question-model v-if="protocolInfo?.id" :id="protocolInfo?.id" @modal:new-question="handleNewQuestion" />
    </n-flex>

    <loading-list-wrapper
      ref="wrapperRef"
      :fetcher="fetcher"
    >
      <template #default="{ data }">
        <discussion-list :list="data" :protocol-id="protocolInfo!.id" />
      </template>
      <template #empty>
        <div class="absolute-center">
          <ask-question-model v-if="protocolInfo?.id" :id="protocolInfo?.id" @modal:new-question="handleNewQuestion" />
        </div>
      </template>
    </loading-list-wrapper>
  </split-layout>
</template>

<script setup lang="ts">
import type { FetchData, FetchPayload } from "@/components/common/loading-list-wrapper.vue"
import LoadingListWrapper from "@/components/common/loading-list-wrapper.vue"
import { useRouterPush } from "@/composables/useRouterPush"
import { getQuestions } from "@/service/api/discussion"
import { ChatType } from "@airalogy/shared/enum"
import { useProtocolInfoStore } from "./hooks/useProtocolInfoStore"
import SplitLayout from "./layout/split-layout.vue"
import AskQuestionModel from "./modules/discussion/ask-question-model.vue"
import DiscussionList from "./modules/discussion/protocol-discussion-list.vue"
import SearchResult from "./modules/discussion/search-result.vue"

const wrapperRef = ref<{ reload: () => void }>()
const { protocolInfo, airalogyId, protocolId } = useProtocolInfoStore()! || {}
const { routerPushByKey } = useRouterPush()

async function fetcher(params: FetchPayload): Promise<FetchData> {
  const { currentPage, currentPageSize, requestId } = params
  if (!protocolId.value) {
    return null
  }

  const data = await getQuestions({
    id: protocolId.value,
    page: currentPage,
    pageSize: currentPageSize,
  }, requestId)

  if (data) {
    const { questions, total_count } = data
    return { list: questions, total: total_count }
  }
  return null
}

function handleNewQuestion(payload: Api.Discussion.CreateQuestionResponse) {
  const { id, protocol_id } = payload

  void routerPushByKey("protocol-discussion-detail", {
    params: {
      protocolId: protocol_id,
      questionId: id,
    },
  })
}
</script>

<style scoped lang="sass">
.result__wrapper
  padding: 24px

em
  font-weight: bold
</style>
