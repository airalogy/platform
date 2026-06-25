<template>
  <loading-list-wrapper ref="wrapperRef" :fetcher="fetcher">
    <template #default="{ data }">
      <project-list :list="data" />
    </template>
    <template #empty>
      <div class="my-10 text-center">
        <img
          src="/images/empty_placeholder.svg"
          alt="placeholder"
          class="h-40 w-full object-contain"
        >
        <h3 class="mt-4 w-full whitespace-nowrap text-6 font-500">
          You don't have starred projects yet.
        </h3>
      </div>
    </template>
  </loading-list-wrapper>
</template>

<script setup lang="ts">
import type { FetchData, FetchPayload } from "@/components/common/loading-list-wrapper.vue"
import LoadingListWrapper from "@/components/common/loading-list-wrapper.vue"
import { fetchUserProjects } from "@/service/api/users"
import { useAuthStore } from "@/store/modules/auth"
import { useClosableMessage } from "@airalogy/composables"
import ProjectList from "./modules/project-list.vue"

defineOptions({
  name: "ProjectStarred",
})

const wrapperRef = ref<{ reload: () => void }>()
const authStore = useAuthStore()
const message = useClosableMessage()

async function fetcher(params: FetchPayload): Promise<FetchData> {
  const { currentPage, currentPageSize, requestId } = params
  try {
    const data = await fetchUserProjects(authStore.userInfo.id, {
      page: currentPage,
      pageSize: currentPageSize,
    }, requestId)
    if (data) {
      const { projects, total_count } = data
      return { list: projects, total: total_count }
    }
  }
  catch (e) {
    message.error((e as Error).message)
  }
  return { list: [], total: 0 }
}
</script>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *
</style>
