<template>
  <loading-list-wrapper ref="wrapperRef" :fetcher="fetcher">
    <template #default="{ data }">
      <global-member-list
        :id="labId" :list="data" type="lab"
        @update:role="handleUpdateRole"
      />
    </template>
    <template #empty>
      <div class="absolute-center">
        No members
      </div>
    </template>
  </loading-list-wrapper>
</template>

<script setup lang="ts">
import type { FetchData, FetchPayload } from "@/components/common/loading-list-wrapper.vue"
import GlobalMemberList from "@/components/common/global-member-list.vue"
import LoadingListWrapper from "@/components/common/loading-list-wrapper.vue"
import { useRouterPush } from "@/composables/useRouterPush"
import { fetchLabMemberList } from "@/service/api/labs"
import { useOrProvideLabInfoStore } from "./hooks/useLabsInfoStore"

defineOptions({
  name: "LabsMembers",
})

const wrapperRef = ref<{ reload: () => void }>()

const route = useRoute()

const { labInfo, fetchLabInfoByUid } = useOrProvideLabInfoStore(null)

const labId = computed(() => {
  return String(labInfo.value?.id ?? "")
})

const { routerPushByKey } = useRouterPush()

async function fetcher(params: FetchPayload): Promise<FetchData> {
  if (!labId.value) {
    return null
  }

  try {
    const { currentPage, currentPageSize, requestId } = params
    const data = await fetchLabMemberList(labId.value, {
      page: currentPage,
      pageSize: currentPageSize,
    }, requestId)
    if (data && Array.isArray(data.users)) {
      const { users, total_count } = data
      return { list: users, total: total_count }
    }
  }
  catch (e) {
    // TODO
  }
  finally {
    routerPushByKey.bind(null, "lab-not-found")
  }
  return null
}

async function handleUpdateRole() {
  wrapperRef.value?.reload()
}

onMounted(async () => {
  if (!labInfo.value) {
    const { labUid } = route.params
    await fetchLabInfoByUid(labUid as string, routerPushByKey.bind(null, "not-found"))
  }
})

watch(() => labInfo.value?.id, async () => {
  await wrapperRef.value?.reload()
}, { immediate: true })
</script>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *
</style>
