<template>
  <loading-list-wrapper ref="wrapperRef" :fetcher="fetcher">
    <template #default="{ data }">
      <lab-group-list :list="data" :show-actions="canManageGroup" @delete:group="handleDeleteGroup" />
    </template>
    <template #empty>
      <div v-if="canManageGroup" class="absolute-center text-6">
        <create-group-modal :lab-info="labInfo" :show-select="false" @modal:new-group="handleCreateGroup" />
      </div>
      <custom-empty v-else description="No group in this lab" />
    </template>
  </loading-list-wrapper>
</template>

<script setup lang="ts">
import type { FetchData, FetchPayload } from "@/components/common/loading-list-wrapper.vue"
import LoadingListWrapper from "@/components/common/loading-list-wrapper.vue"
import { useLabPermissions } from "@/composables/useLabPermissions"
import { useRouterPush } from "@/composables/useRouterPush"
import { fetchGroupsList } from "@/service/api/groups"
import { useOrProvideLabInfoStore } from "./hooks/useLabsInfoStore"
import CreateGroupModal from "./modules/group/create-group-modal.vue"
import LabGroupList from "./modules/group/lab-group-list.vue"

defineOptions({
  name: "LabInfoGroups",
})

const wrapperRef = ref<{ reload: () => void }>()
const route = useRoute()

const { labInfo } = useOrProvideLabInfoStore(null)
const { canManageGroup } = useLabPermissions(labInfo)

async function fetcher(params: FetchPayload): Promise<FetchData> {
  const { id: labId } = labInfo.value || {}
  if (!labId && !route.params.labUid) {
    return null
  }

  try {
    const { currentPage, currentPageSize, requestId } = params
    const data = await fetchGroupsList({
      labId,
      labUid: labId ? undefined : route.params.labUid as string,
      page: currentPage,
      pageSize: currentPageSize,
    }, requestId)
    if (data && Array.isArray(data.groups)) {
      const { groups, total_count } = data

      return { list: groups, total: total_count }
    }
  }
  catch (e) {
    // NOPE
  }
  return null
}

const { routerPushByKey } = useRouterPush()
async function handleCreateGroup(val: Api.Groups.MyGroupsInfo) {
  const { lab_id, id, lab_uid: labUid } = val
  const labIdStr = String(lab_id)
  const groupId = String(id)

  if (!labIdStr || !groupId) {
    return
  }

  await routerPushByKey("lab-group-projects", { params: { labUid, groupId } })
}

async function handleDeleteGroup() {
  wrapperRef.value?.reload()
}
</script>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *
</style>
