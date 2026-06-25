<template>
  <loading-list-wrapper ref="wrapperRef" :fetcher="fetcher">
    <template #default="{ data }">
      <project-research-list :list="data" />
    </template>
    <template #empty>
      <div class="absolute-center text-6">
        <add-protocol-modal
          :compact="false" show-icon :trigger="$t('common.newProtocol')" :show-select="false" :lab="labInfo"
          :project="projectInfo" @modal:new-protocol="handleAddResearch"
        />
      </div>
    </template>
  </loading-list-wrapper>
</template>

<script setup lang="ts">
import type { FetchData, FetchPayload } from "@/components/common/loading-list-wrapper.vue"
import LoadingListWrapper from "@/components/common/loading-list-wrapper.vue"
import { useRouterPush } from "@/composables/useRouterPush"
import { fetchGroupsProjectList } from "@/service/api/groups"
import { $t } from "@airalogy/shared/locales"
import { useOrProvideProjectInfoStore } from "../project-protocols/hooks/useProjectInfoStore"
import AddProtocolModal from "../project-protocols/modules/add-protocol-modal.vue"
import { useOrProvideLabInfoStore } from "./hooks/useLabsInfoStore"

defineOptions({
  name: "GroupInfo",
})

const wrapperRef = ref<{ reload: () => void }>()
const route = useRoute()
const { labInfo } = useOrProvideLabInfoStore(null)
const { projectInfo } = useOrProvideProjectInfoStore(null)

async function fetcher(params: FetchPayload): Promise<FetchData> {
  const { groupId } = route.params
  if (!groupId || Array.isArray(groupId)) {
    return { list: [], total: 0 }
  }

  try {
    const { currentPage, currentPageSize, requestId } = params
    const data = await fetchGroupsProjectList(groupId, {
      page: currentPage,
      pageSize: currentPageSize,
    }, requestId)

    if (data) {
      const { projects, total_count } = data
      return { list: projects, total: total_count }
    }
  }
  catch (e) {
    // NOPE
  }
  return { list: [], total: 0 }
}

const { routerPushByKey } = useRouterPush()

function handleAddResearch(payload: {
  id: string
  uid: string
  labUid: string
  labId: string
  projectUid: string
  name: string
}) {
  const { uid, projectUid, labUid } = payload
  void routerPushByKey("protocol-info", {
    params: {
      labUid,
      protocolUid: uid,
      projectUid,
    },
  })
}
</script>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *
</style>
