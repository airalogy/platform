<template>
  <loading-list-wrapper ref="wrapperRef" :fetcher="fetcher">
    <template #default="{ data }">
      <project-protocol-list
        :list="data"
        :pinned-map="pinnedMap"
        :pinning-keys="pinningKeys"
        @togglePin="handleTogglePin"
      />
    </template>
    <template #empty>
      <div class="absolute-center flex items-center gap-2">
        <import-aira-archive-modal @imported="handleImportArchive" />
        <add-protocol-modal @modal:new-protocol="handleCreateResearch" />
      </div>
    </template>
  </loading-list-wrapper>
</template>

<script setup lang="ts">
import type { FetchData, FetchPayload } from "@/components/common/loading-list-wrapper.vue"
import type { ImportAiraArchiveResponse } from "@/service/api/project-protocols"
import type { ProtocolModels } from "@airalogy/shared/types"
import LoadingListWrapper from "@/components/common/loading-list-wrapper.vue"
import { useRouterPush } from "@/composables/useRouterPush"
import { createPinnedItem, deletePinnedItem, getPinnedItems, type PinnedItem, PinnedResourceType } from "@/service/api/pinned-items"
import { getProtocolInfo } from "@/service/api/protocol"
import { fetchUserProtocols } from "@/service/api/users"
import { useAuthStore } from "@/store/modules/auth"
import ProjectProtocolList from "@/views/project/modules/project-protocol-list.vue"
import AddProtocolModal from "./modules/add-protocol-modal.vue"
import ImportAiraArchiveModal from "./modules/import-aira-archive-modal.vue"

defineOptions({
  name: "ProtocolsMyDashboard",
})

const wrapperRef = ref<{ reload: () => void }>()
const { userInfo } = useAuthStore()
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
        const items = data?.items || []
        const protocolItems = items.filter(item => item.resource_type === PinnedResourceType.Protocol)
        if (protocolItems.length > 0) {
          const results = await Promise.allSettled(
            protocolItems.map(item => getProtocolInfo(item.resource_id)),
          )
          results.forEach((result, index) => {
            if (result.status === "fulfilled" && result.value.data) {
              protocolItems[index]!.resource = result.value.data
            }
          })
        }
        pinnedItems.value = items
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

function getPinnedProtocols() {
  return pinnedItems.value
    .filter(item => item.resource_type === PinnedResourceType.Protocol && item.resource)
    .map(item => item.resource as ProtocolModels.ProjectProtocolInfo)
    .filter(item => item.lab && item.project)
}

async function fetcher(params: FetchPayload): Promise<FetchData> {
  const { currentPage, currentPageSize, requestId } = params
  await ensurePinnedItems()
  const data = await fetchUserProtocols(userInfo.id, { page: currentPage, pageSize: currentPageSize }, requestId)
  if (data && Array.isArray(data.protocols)) {
    const { protocols, total_count } = data
    const pinnedProtocols = getPinnedProtocols()
    if (pinnedProtocols.length === 0) {
      return { list: protocols, total: total_count }
    }

    const pinnedIds = new Set(pinnedProtocols.map(item => item.id))
    if (currentPage === 1) {
      const merged = [...pinnedProtocols, ...protocols.filter(item => !pinnedIds.has(item.id))]
      return { list: merged.slice(0, currentPageSize), total: total_count }
    }

    return { list: protocols.filter(item => !pinnedIds.has(item.id)), total: total_count }
  }
  return null
}

const { routerPushByKey } = useRouterPush()

async function handleCreateResearch(item: {
  id: string
  uid: string
  labUid: string
  labId: string
  projectUid: string
  name: string
}) {
  const { uid, labUid, projectUid } = item

  await routerPushByKey("protocol-info", {
    params: { labUid, projectUid, protocolUid: uid },
  })
}

async function handleImportArchive(result: ImportAiraArchiveResponse) {
  await wrapperRef.value?.reload()
  const importedProtocol = result.protocols[0]
  if (!importedProtocol) {
    return
  }

  await routerPushByKey("protocol-info", {
    params: {
      labUid: importedProtocol.lab_uid,
      projectUid: importedProtocol.project_uid,
      protocolUid: importedProtocol.uid,
    },
  })
}
</script>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *
</style>
