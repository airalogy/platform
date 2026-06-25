<template>
  <loading-list-wrapper ref="wrapperRef" :fetcher="fetcher">
    <template #default="{ data }">
      <lab-list :list="data" />
    </template>
    <template #empty>
      <div class="absolute-center">
        <create-lab-modal @modal:new-lab="handleCreateLab" />
      </div>
    </template>
  </loading-list-wrapper>
</template>

<script setup lang="ts">
import type { FetchData, FetchPayload } from "@/components/common/loading-list-wrapper.vue"
import LoadingListWrapper from "@/components/common/loading-list-wrapper.vue"
import { useRouterPush } from "@/composables/useRouterPush"
import { fetchLabList } from "@/service/api/labs"
import CreateLabModal from "./modules/lab/create-lab-modal.vue"
import LabList from "./modules/lab/lab-list.vue"

defineOptions({
  name: "LabsPublic",
})

const wrapperRef = ref<{ reload: () => void }>()

async function fetcher(params: FetchPayload): Promise<FetchData> {
  const { currentPage, currentPageSize, requestId } = params
  try {
    const { data } = await fetchLabList({ page: currentPage, pageSize: currentPageSize, type: 2 }, requestId)
    if (data && Array.isArray(data.data)) {
      const { data: list, total_count } = data
      return { list, total: total_count }
    }
  }
  catch (e) {
    // TODO
  }
  return { list: [], total: 0 }
}

const { routerPushByKey } = useRouterPush()

async function handleCreateLab(item: Api.Lab.LabInfo) {
  const { uid } = item

  await routerPushByKey("lab-projects", { params: { labUid: uid } })
}
</script>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *
</style>
