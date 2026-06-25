<template>
  <loading-list-wrapper ref="wrapperRef" :fetcher="fetcher">
    <template #default="{ data }">
      <global-member-list
        :id="route.params.groupId" :list="data" type="group"
        :is-manager="isManager"
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
import { fetchGroupsMemberList } from "@/service/api/groups"
import { useAuthStore } from "@/store/modules/auth"
import { useGroupInfoStore } from "./hooks/useGroupInfoStore"

defineOptions({
  name: "GroupMembers",
})

const wrapperRef = ref<{ reload: () => void }>()
const { groupInfo } = useGroupInfoStore()!
const route = useRoute()

async function fetcher(params: FetchPayload): Promise<FetchData> {
  const groupId = groupInfo.value?.id
  if (!groupId) {
    return { list: [], total: 0 }
  }

  try {
    const { currentPage, currentPageSize, requestId } = params
    const data = await fetchGroupsMemberList(groupId, {
      page: currentPage,
      pageSize: currentPageSize,
    }, requestId)

    if (data && Array.isArray(data.users)) {
      const { users } = data
      return { list: users, total: users.length }
    }
  }
  catch (e) {
    // TODO
  }
  return { list: [], total: 0 }
}

const authStore = useAuthStore()

const isManager = computed(() => {
  const { id: userId } = authStore.userInfo
  if (!groupInfo.value || !userId) {
    return false
  }

  const { create_user_id } = groupInfo.value

  return userId === create_user_id
})

watch(() => groupInfo.value?.id, async () => {
  await wrapperRef.value?.reload()
})

async function handleUpdateRole() {
  await wrapperRef.value?.reload()
}
</script>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *
</style>
