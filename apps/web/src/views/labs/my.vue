<template>
  <loading-list-wrapper
    ref="wrapperRef"
    :fetcher="fetcher"
    :params="{
      name: filterOption === 'name' ? searchQuery : undefined,
      uid: filterOption === 'id' ? searchQuery : undefined,
    }"
  >
    <template #header>
      <div class="mb-3 flex items-center gap-3">
        <search-input
          v-model:value="searchQuery"
          icon-position="right"
          :placeholder="$t('page.labs.searchMyLabsPlaceholder')"
          class="mr-3 max-w-40%"
          @submit:search="handleSearch"
        />
        <global-sort-selector
          v-model="filterOption"
          :options="filterOptions"
          :label="$t('common.searchBy')"
          class="ml-auto"
        />
        <global-sort-selector
          v-model="sortOption"
          :options="sortOptions"
          class="w-60!"
        />
      </div>
    </template>
    <template #default="{ data }">
      <lab-list
        :list="data"
        :pinned-map="pinnedMap"
        :pinning-keys="pinningKeys"
        @togglePin="handleTogglePin"
      />
    </template>
    <template #empty>
      <custom-empty
        v-if="searchRouteQuery"
        :description="emptyDescription"
      />
      <div v-else class="absolute-center">
        <create-lab-modal @modal:new-lab="handleCreateLab" />
      </div>
    </template>
  </loading-list-wrapper>
</template>

<script setup lang="ts">
import type { FetchData, FetchPayload } from "@/components/common/loading-list-wrapper.vue"
import type { SelectOption } from "naive-ui"
import LoadingListWrapper from "@/components/common/loading-list-wrapper.vue"
import { useRouterPush } from "@/composables/useRouterPush"
import { createPinnedItem, deletePinnedItem, getPinnedItems, type PinnedItem, PinnedResourceType } from "@/service/api/pinned-items"
import { fetchUserLabs } from "@/service/api/users"
import { useAuthStore } from "@/store/modules/auth"
import { $t } from "@airalogy/shared/locales"
import { useRouteQuery } from "@vueuse/router"
import SearchInput from "../../components/common/search-input.vue"
import CreateLabModal from "./modules/lab/create-lab-modal.vue"
import LabList from "./modules/lab/lab-list.vue"

defineOptions({
  name: "LabsMyDashboard",
})

const wrapperRef = ref<{ reload: () => void }>()
const { userInfo } = useAuthStore()
const searchRouteQuery = useRouteQuery("q")
const searchQuery = ref("")
const filterOptions = computed<SelectOption[]>(() => [
  { label: $t("page.labs.searchLabIdLabel"), value: "id" },
  { label: $t("page.labs.searchLabNameLabel"), value: "name" },
])
const filterOption = useRouteQuery<"name" | "id">("type", "id")
const sortOptions = computed<SelectOption[]>(() => [
  { label: $t("page.project.protocolsSort.stars"), value: "mostStars" },
  { label: $t("page.project.protocolsSort.popular"), value: "popular" },
  { label: $t("page.project.protocolsSort.updated"), value: "recentlyUpdated" },
])

const sortOption = ref("mostStars")
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
const emptyDescription = computed(() => {
  if (filterOption.value === "id") {
    return $t("page.labs.searchEmptyById", { query: searchQuery.value })
  }
  return $t("page.labs.searchEmptyByName", { query: searchQuery.value })
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

function matchesLabQuery(item: Api.Lab.LabInfo, name?: string, uid?: string) {
  if (name) {
    const query = name.toLowerCase()
    return [item.name, item.uid].some(value => value?.toLowerCase().includes(query))
  }
  if (uid) {
    const query = uid.toLowerCase()
    return [item.uid, String(item.id)].some(value => value?.toLowerCase().includes(query))
  }
  return true
}

function getPinnedLabs(name?: string, uid?: string) {
  return pinnedItems.value
    .filter(item => item.resource_type === PinnedResourceType.Lab && item.resource)
    .map(item => item.resource as Api.Lab.LabInfo)
    .filter(item => matchesLabQuery(item, name, uid))
}

async function fetcher(params: FetchPayload): Promise<FetchData> {
  const { currentPage, currentPageSize, name, uid, requestId } = params
  try {
    await ensurePinnedItems()
    const data = await fetchUserLabs(userInfo.id, {
      name,
      uid,
      page: currentPage,
      pageSize: currentPageSize,
    }, requestId)
    if (data && Array.isArray(data.labs)) {
      const { labs, total_count } = data
      const pinnedLabs = getPinnedLabs(name, uid)
      if (pinnedLabs.length === 0) {
        return { list: labs, total: total_count }
      }

      const pinnedIds = new Set(pinnedLabs.map(item => item.id))
      if (currentPage === 1) {
        const merged = [...pinnedLabs, ...labs.filter(item => !pinnedIds.has(item.id))]
        return { list: merged.slice(0, currentPageSize), total: total_count }
      }

      return { list: labs.filter(item => !pinnedIds.has(item.id)), total: total_count }
    }
  }
  catch (e) {
    // NOPE
  }
  return { list: [], total: 0 }
}
const { routerPushByKey } = useRouterPush()

async function handleCreateLab(item: Api.Lab.LabInfo) {
  const { uid } = item

  await routerPushByKey("lab-projects", { params: { labUid: uid } })
}

async function handleSearch() {
  searchRouteQuery.value = searchQuery.value
  await wrapperRef.value?.reload()
}
</script>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *
</style>
