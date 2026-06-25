<template>
  <loading-list-wrapper ref="wrapperRef" :fetcher="fetcher">
    <template #default="{ data }">
      <project-list
        :list="data"
        :pinned-map="pinnedMap"
        :pinning-keys="pinningKeys"
        @togglePin="handleTogglePin"
      />
    </template>
    <template #empty>
      <div class="absolute-center">
        <create-project-modal @modal:new-project="handleAddProject" />
      </div>
    </template>
  </loading-list-wrapper>
</template>

<script setup lang="ts">
import type { FetchData, FetchPayload } from "@/components/common/loading-list-wrapper.vue"
import LoadingListWrapper from "@/components/common/loading-list-wrapper.vue"
import { useRouterPush } from "@/composables/useRouterPush"
import { createPinnedItem, deletePinnedItem, getPinnedItems, type PinnedItem, PinnedResourceType } from "@/service/api/pinned-items"
import { fetchUserProjects } from "@/service/api/users"
import { useAuthStore } from "@/store/modules/auth"
import { useClosableMessage } from "@airalogy/composables"
import CreateProjectModal from "./modules/create-project-modal.vue"
import ProjectList from "./modules/project-list.vue"

defineOptions({
  name: "ProjectDashboard",
})

const wrapperRef = ref<{ reload: () => void }>()
const message = useClosableMessage()
const authStore = useAuthStore()
const pinnedItems = ref<PinnedItem[]>([])
const pinnedRequest = ref<Promise<void> | null>(null)
const pinningKeys = ref(new Set<string>())

const pinnedMap = computed(() => {
  const map = new Map<string, PinnedItem>()
  pinnedItems.value.forEach((item) => {
    map.set(`${item.resource_type}:${item.resource_id}`, item)
  })
  return map
})

async function ensurePinnedItems() {
  if (!pinnedRequest.value) {
    pinnedRequest.value = (async () => {
      try {
        const { data } = await getPinnedItems()
        pinnedItems.value = data?.items || []
      }
      catch {
        pinnedItems.value = []
      }
    })()
  }
  await pinnedRequest.value
}

async function handleTogglePin(payload: { resourceType: PinnedResourceType, resourceId: string }) {
  const { resourceType, resourceId } = payload
  if (!resourceId) {
    return
  }
  const key = `${resourceType}:${resourceId}`
  if (pinningKeys.value.has(key)) {
    return
  }
  pinningKeys.value.add(key)
  try {
    const existing = pinnedMap.value.get(key)
    if (existing) {
      await deletePinnedItem(existing.id)
    }
    else {
      await createPinnedItem({ resource_type: resourceType, resource_id: resourceId })
    }
    pinnedRequest.value = null
    await ensurePinnedItems()
    await wrapperRef.value?.reload()
  }
  finally {
    pinningKeys.value.delete(key)
  }
}

function getPinnedProjects() {
  return pinnedItems.value
    .filter(item => item.resource_type === PinnedResourceType.Project && item.resource)
    .map(item => item.resource as Api.Project.MyProjectInfo)
}

async function fetcher(params: FetchPayload): Promise<FetchData> {
  const { currentPage, currentPageSize, requestId } = params
  try {
    await ensurePinnedItems()
    const data = await fetchUserProjects(authStore.userInfo.id, {
      page: currentPage,
      pageSize: currentPageSize,
    }, requestId)
    if (data) {
      const { projects, total_count } = data
      const pinnedProjects = getPinnedProjects()
      if (pinnedProjects.length === 0) {
        return { list: projects, total: total_count }
      }

      const pinnedIds = new Set(pinnedProjects.map(item => item.id))
      if (currentPage === 1) {
        const merged = [...pinnedProjects, ...projects.filter(item => !pinnedIds.has(item.id))]
        return { list: merged.slice(0, currentPageSize), total: total_count }
      }

      return { list: projects.filter(item => !pinnedIds.has(item.id)), total: total_count }
    }
  }
  catch (e) {
    message.error((e as Error).message)
  }
  return null
}

const { routerPushByKey } = useRouterPush()
async function handleAddProject(val: Api.Project.MyProjectInfo) {
  const { lab_uid, uid } = val

  if (!lab_uid || !uid) {
    return
  }

  await routerPushByKey("project-protocols", { params: { labUid: lab_uid, projectUid: uid } })
}
</script>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *
</style>
