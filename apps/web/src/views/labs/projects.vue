<template>
  <loading-list-wrapper
    ref="wrapperRef"
    :fetcher="handleFetchProjectList"
    class="flex-1"
  >
    <template #header>
      <div class="mb-3 flex items-center gap-3">
        <search-input
          v-model:value="searchQuery"
          icon-position="right"
          :placeholder="$t('page.labs.searchProjectsPlaceholder')"
          class="mr-3 max-w-40%"
          @submit:search="handleSearch('input')"
          @clear="handleSearch('clear')"
        />
        <global-sort-selector
          v-model="filterOption"
          :options="filterOptions"
          :label="$t('common.searchBy')"
          class="ml-auto"
          @update:value="handleSearch('filter')"
        />
        <global-sort-selector
          v-model="sortOption"
          :options="sortOptions"
          class="w-60!"
          @update:value="handleSearch('sort')"
        />
      </div>
    </template>
    <template #default="{ data }">
      <lab-project-list
        :list="data"
        :lab-info="labInfo"
        @delete:project="handleDeleteProject"
      />
    </template>
    <template #empty>
      <custom-empty :description="emptyDescription">
        <create-project-modal
          v-if="userLabRole === LabRole.OWNER || userLabRole === LabRole.MANAGER"
          :lab-info="labInfo"
          :show-select="false"
          @modal:new-project="handleAddProject"
        />
      </custom-empty>
    </template>
  </loading-list-wrapper>
</template>

<script setup lang="ts">
import type { FetchData, FetchPayload } from "@/components/common/loading-list-wrapper.vue"
import type { SelectOption } from "naive-ui"
import LoadingListWrapper from "@/components/common/loading-list-wrapper.vue"
import { useRouterPush } from "@/composables/useRouterPush"
import { LabRole } from "@/enum"
import { fetchProjectList } from "@/service/api/projects"
import { useAppStore } from "@/store/modules/app"
import CreateProjectModal from "@/views/projects/modules/create-project-modal.vue"
import { $t } from "@airalogy/shared/locales"
import { useLabInfoStore } from "./hooks/useLabsInfoStore"
import LabProjectList from "./modules/project/lab-project-list.vue"

defineOptions({
  name: "LabInfoProjects",
})

const emit = defineEmits<IEmits>()

interface IEmits {
  (e: "modal:show"): void
}

const { labInfo, userLabRole } = useLabInfoStore()!
const searchQuery = ref("")
const wrapperRef = ref<any>()
const params = reactive({
  searchQuery: "",
  filterOption: "name",
  sortOption: "mostStars",
})

const filterOptions = computed<SelectOption[]>(() => [
  { label: $t("page.project.protocolsFilter.id"), value: "id" },
  { label: $t("page.project.protocolsFilter.name"), value: "name" },
])
const filterOption = ref<"id" | "name">("name")
const sortOptions = computed<SelectOption[]>(() => [
  { label: $t("page.project.protocolsSort.stars"), value: "mostStars" },
  { label: $t("page.project.protocolsSort.popular"), value: "popular" },
  { label: $t("page.project.protocolsSort.updated"), value: "recentlyUpdated" },
])
const sortOption = ref("mostStars")
const emptyDescription = computed(() => {
  const { searchQuery, filterOption } = params
  if (!searchQuery) {
    return "There are no projects in this lab"
  }
  if (filterOption === "id") {
    return `No project ID "${searchQuery}" found in this lab`
  }
  return `No project Name "${searchQuery}" found in this lab`
})

const route = useRoute()
async function handleFetchProjectList(p: FetchPayload): Promise<FetchData> {
  const { id: labId } = labInfo.value || {}
  const { labUid } = route.params as { labUid: string }

  if (!labId && !labUid) {
    return null
  }

  const { currentPage, currentPageSize, requestId } = p
  const data = await fetchProjectList({
    labUid,
    labId,
    name: filterOption.value === "name" ? searchQuery.value : undefined,
    uid: filterOption.value === "id" ? searchQuery.value : undefined,
    page: currentPage,
    pageSize: currentPageSize,
  }, requestId)

  if (data) {
    const { projects, total_count } = data
    return { list: projects, total: total_count }
  }

  return null
}

const { reloadPage } = useAppStore()
async function handleDeleteProject() {
  await reloadPage(10)
}

async function handleSearch(source: "input" | "sort" | "filter" | "clear") {
  if (source === "filter" && !searchQuery.value) {
    return
  }
  await wrapperRef.value?.reload()
}

const { routerPushByKey } = useRouterPush()
async function handleAddProject(val: Api.Project.MyProjectInfo) {
  const { uid, lab_uid } = val

  if (!lab_uid || !uid) {
    return
  }

  await routerPushByKey("project-protocols", { params: { labUid: lab_uid, projectUid: uid } })
}
</script>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *
</style>
