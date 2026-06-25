<template>
  <section class="relative w-full">
    <header class="pt-5">
      <global-breadcrumb />
      <div class="my-6 flex items-center justify-start">
        <hub-icon class="mr-4" />
        <h2 class="mr-auto font-bold !text-6">
          Hub
        </h2>
        <search-input
          v-model:value="searchQuery"
          icon-position="right"
          placeholder="Search Airalogy Protocols"
          class="mr-3 max-w-40%"
          @submit:search="handleSearch('input')"
          @clear="handleSearch('clear')"
        />
        <global-sort-selector
          v-model="sortOption"
          :options="sortOptions"
          class="w-60!"
          @update:value="handleSearch('sort')"
        />
      </div>
    </header>

    <hub-split-layout class="w-full flex-1">
      <template #default>
        <loading-list-wrapper
          ref="wrapperRef"
          :fetcher="fetcher"
        >
          <template #default="{ data }">
            <protocol-card
              v-for="(item, idx) in data"
              :key="item.id"
              :protocol="item"
              :class="{ 'mt-4': idx !== 0 }"
              @apply="handleApplyProtocol"
            />
          </template>
          <template #empty>
            <n-empty description="No protocols found" class="flex-1 justify-center" />
          </template>
        </loading-list-wrapper>
      </template>
    </hub-split-layout>
  </section>
</template>

<script setup lang="ts">
import type { FetchData, FetchPayload } from "@/components/common/loading-list-wrapper.vue"
import type { SelectOption } from "naive-ui"
import LoadingListWrapper from "@/components/common/loading-list-wrapper.vue"
import SearchInput from "@/components/common/search-input.vue"
import ProtocolCard from "@/components/protocol/protocol-card.vue"
import { useRouterPush } from "@/composables/useRouterPush"
import { getFetchHubProtocols, SortEnum } from "@/service/api/hub"
import { useRouteStore } from "@/store/modules/route"
import HubSplitLayout from "./layout/split-layout.vue"

const wrapperRef = ref<{ reload: () => void }>()
const searchQuery = ref("")

const sortOptions = ref<(SelectOption & { value: SortEnum })[]>([
  { label: "Most Stars", value: SortEnum.StarsCount },
  { label: "Most Forks", value: SortEnum.ForksCount },
  { label: "Recently Updated", value: SortEnum.UpdatedAt },
])
const sortOption = ref<SortEnum>(SortEnum.StarsCount)

async function fetcher(params: FetchPayload): Promise<FetchData> {
  const { currentPage, currentPageSize, requestId } = params
  const data = await getFetchHubProtocols({
    page: currentPage,
    pageSize: currentPageSize,
    name: searchQuery.value || undefined,
    sort: sortOption.value || undefined,
  }, requestId)

  if (data) {
    const { protocols, total_count } = data
    return { list: protocols, total: total_count }
  }

  return null
}

async function handleSearch(source: "input" | "sort" | "filter" | "clear") {
  if (source === "filter" && !searchQuery.value) {
    return
  }
  await wrapperRef.value?.reload()
}
const { routerPushByKey } = useRouterPush()

function handleApplyProtocol(protocol: Api.Hub.Protocol) {
  routerPushByKey("protocol-detail", {
    params: {
      labUid: protocol.lab.uid,
      projectUid: protocol.project.uid,
      protocolUid: protocol.uid,
    },
  })
}

const { setDynamicBreadcrumbs } = useRouteStore()

onMounted(() => {
  setDynamicBreadcrumbs([{
    breadcrumbLabel: "Hub",
    key: "hub",
    label: "Hub",
    routeKey: "hub" satisfies App.Global.RouteKey,
    routePath: "hub",
  }, {
    breadcrumbLabel: "All protocols",
    key: "hub-list",
    label: "All protocols",
    routeKey: "hub-list" satisfies App.Global.RouteKey,
    routePath: "list",
  }])
})
</script>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *
</style>
