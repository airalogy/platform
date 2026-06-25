<template>
  <loading-list-wrapper ref="wrapperRef" :fetcher="fetcher">
    <template #default="{ data }">
      <lab-project-list
        :list="data"
        :group-info="groupInfo"
        :lab-info="labInfo"
        :fetch-count="false"
        type="group"
        @update:role="handleUpdateRole"
      />
    </template>
    <template #empty>
      <div v-if="groupInfo && canManageGroup" class="absolute-center text-6">
        <add-project-modal
          :id="groupInfo.id"
          :lab-info="labInfo"
          @modal:new-project="handleCreateProject"
        />
      </div>
    </template>
  </loading-list-wrapper>
</template>

<script setup lang="ts">
import type { FetchData, FetchPayload } from "@/components/common/loading-list-wrapper.vue"
import LoadingListWrapper from "@/components/common/loading-list-wrapper.vue"
import { useLabPermissions } from "@/composables/useLabPermissions"
import { fetchGroupsProjectList } from "@/service/api/groups"
import { useOrProvideLabInfoStore } from "@/views/labs/hooks/useLabsInfoStore"
import LabProjectList from "@/views/labs/modules/project/lab-project-list.vue"
import { useGroupInfoStore } from "./hooks/useGroupInfoStore"
import AddProjectModal from "./modules/add-project-modal.vue"

defineOptions({
  name: "GroupInfoProjects",
})

const wrapperRef = ref<{ reload: () => void }>()
const { labInfo } = useOrProvideLabInfoStore(null)
const { groupInfo } = useGroupInfoStore()!
const { canManageGroup } = useLabPermissions(labInfo)

async function fetcher(params: FetchPayload): Promise<FetchData> {
  if (!groupInfo.value || !groupInfo.value.id) {
    return null
  }

  try {
    const { currentPage, currentPageSize, requestId } = params
    const data = await fetchGroupsProjectList(groupInfo.value.id, {
      page: currentPage,
      pageSize: currentPageSize,
    }, requestId)

    if (data && Array.isArray(data.projects)) {
      const { projects, total_count } = data
      return { list: projects, total: total_count }
    }
  }
  catch (e) {
    // NOPE
  }
  return { list: [], total: 0 }
}

async function handleUpdateRole() {
  await wrapperRef.value?.reload()
}
async function handleCreateProject() {
  await wrapperRef.value?.reload()
}

watch(() => groupInfo.value?.id, async () => {
  await wrapperRef.value?.reload()
})
</script>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *
</style>
