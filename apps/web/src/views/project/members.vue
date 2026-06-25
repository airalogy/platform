<template>
  <loading-list-wrapper ref="wrapperRef" :fetcher="fetcher" :immediate="!!projectInfo">
    <template #default="{ data }">
      <global-member-list
        v-if="projectInfo?.id"
        :id="projectInfo.id"
        :list="data"
        type="project"
        :can-assign-roles="canAssignRoles"
        @update:role="reloadInfo"
      />
    </template>
    <template #empty>
      <div class="absolute-center text-6">
        No members
      </div>
    </template>
  </loading-list-wrapper>
</template>

<script setup lang="ts">
import type { FetchData, FetchPayload } from "@/components/common/loading-list-wrapper.vue"
import GlobalMemberList from "@/components/common/global-member-list.vue"
import LoadingListWrapper from "@/components/common/loading-list-wrapper.vue"
import { useProjectPermissions } from "@/composables/useProjectPermissions"
import { fetchProjectMembers } from "@/service/api/projects"
import { useClosableMessage } from "@airalogy/composables"
import { useOrProvideProjectInfoStore } from "../project-protocols/hooks/useProjectInfoStore"

defineOptions({
  name: "ProjectMembers",
})

const wrapperRef = ref<{ reload: () => void }>()
const message = useClosableMessage()
const { projectInfo } = useOrProvideProjectInfoStore(null)
const { canAssignRoles } = useProjectPermissions(projectInfo)

async function fetcher(params: FetchPayload): Promise<FetchData> {
  const { id } = projectInfo.value || {}
  if (!id) {
    return null
  }

  try {
    const { currentPage, currentPageSize, requestId } = params
    const { data } = await fetchProjectMembers(id, {
      page: currentPage,
      pageSize: currentPageSize,
    }, requestId)
    if (data && Array.isArray(data.users)) {
      const { users, total_count } = data
      return { list: users, total: total_count }
    }
  }
  catch (e) {
    message.error((e as Error).message)
  }
  return { list: [], total: 0 }
}

async function reloadInfo() {
  await wrapperRef.value?.reload()
}
</script>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *
</style>
