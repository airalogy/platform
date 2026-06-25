<!-- eslint-disable vue/no-v-html -->
<template>
  <global-search
    class="h-full w-full md:w-60%"
    :input-props="{
      iconPosition: 'right',
      inputStyle: { '--n-height': '2.5rem' },
      inputClass: '!h-10',
      maxlength: 200,
    }"
    :on-submit="handleSubmitSearch"
    @search:result="handleSearchResult"
  >
    <template #result>
      <div
        v-for="(item, idx) in listWithUser"
        :key="idx"
        class="mb-4 border rounded-md bg-white p-4 shadow"
      >
        <h3 class="text-lg font-semibold">
          <router-link
            :to="{ name: 'protocol-discussion-detail', params: { questionId: item.uuid } }"
            class="!hover:router-link"
          >
            {{ item.title }}
          </router-link>
        </h3>

        <div v-if="item.headline" class="mt-2 text-gray-600" v-html="item.headline" />
        <div
          v-else-if="item.q_headline && item.q_headline === '#'"
          class="line-clamp-3 mt-2 text-gray-600"
          v-html="item.content"
        />
        <div v-else-if="item.q_headline" class="mt-2 text-gray-600" v-html="item.q_headline" />
        <div v-else-if="item.a_headline" class="mt-2 text-gray-600" v-html="item.a_headline" />
        <div v-if="item.user" class="mt-2 flex items-center text-gray-500">
          <n-avatar size="small" :src="item.user.avatar_url" class="mr-2" />
          <router-link
            :to="{ name: 'user-profile', params: { username: item.user.username } }"
            class="!hover:router-link"
          >
            @{{ item.user.name }}
          </router-link>
          <span class="mx-2">·</span>
          <n-time :time="new Date(item.created_at)" />
          <!-- <span class="mx-2">·</span> -->
          <!-- <router-link
            :to="{ name: 'protocol-discussion-detail', params: { questionId: item.id } }"
            class="text-blue-600 hover:underline"
          >
            {{ item.answers_count }}
          </router-link> -->
        </div>
      </div>
    </template>
  </global-search>
</template>

<script setup lang="ts">
// eslint-disable-next-line ts/ban-ts-comment
// @ts-nocheck

import GlobalSearch from "@/layouts/modules/global-search/index.vue"
import { getSearchResearchNode } from "@/service/api/search"

import { getUserInfoById } from "@/service/api/users"
import { useClosableMessage } from "@airalogy/composables"

import { useProtocolInfoStore } from "../../hooks/useProtocolInfoStore"

const { protocolInfo } = useProtocolInfoStore()!

const message = useClosableMessage()

const handleSubmitSearch: (
  val: string,
) => Promise<Api.GetResponse<Api.Search.DiscussionSearchItem> | null> = async (query: string) => {
  const info = unref(protocolInfo)
  if (!info) {
    message.error("Please select a research first")
    return null
  }

  const data = await getSearchResearchNode({
    id: info.id,
    type: "question",
    query,
    page: 1,
    pageSize: 9999,
  })

  if (data) {
    return { data: data.result, total_count: data.total_count }
  }

  return null
}
type ListWithUser = ((Api.Search.DiscussionSearchItem | Api.Search.ProtocolSearchItem | Api.Search.RecordSearchItem) & { user?: Api.Profile.User | null, user_id?: number })
const list = ref<ListWithUser[]>([])

const total = ref<number>(0)
function handleSearchResult(data: Api.GetResponse<any>) {
  list.value = data.data
  total.value = data.total_count
}

const listWithUser = computedAsync<ListWithUser[]>(async () => {
  const result = await Promise.allSettled(
    list.value.map(item => (item.user_id ? getUserInfoById(item.user_id) : null)),
  )

  return list.value.map((item, index): any => {
    const res = result[index]
    if (res.status === "fulfilled") {
      return { ...item, user: res.value?.data }
    }

    return { ...item, user: null }
  })
}, list.value)
</script>

<style scoped lang="sass">
.border
  border: 1px solid #d0d7de

:deep(em)
  font-style: italic
  font-weight: bold
  color: #0070f3
</style>
