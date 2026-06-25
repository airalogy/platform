<template>
  <loading-list-wrapper
    ref="wrapperRef"
    :fetcher="fetcher"
  >
    <template #header>
      <div class="mb-3 flex items-center gap-3">
        <search-input
          v-model:value="searchInputVal"
          icon-position="right"
          :placeholder="$t('page.project.protocolsSearchPlaceholder')"
          class="mr-3 max-w-40%"
          @submit:search="handleSearch('input')"
          @clear="handleSearch('clear')"
        />
        <n-popselect v-model:value="folderFilter" :options="folderFilterOptions" @update:value="handleSearch('folder')">
          <n-button icon-placement="right" quaternary class="h-9">
            <span class="mr-2 text-sm">{{ $t("page.project.protocolFolders.filterLabel") }}:</span>
            <span class="text-sm font-semibold">{{ selectedFolderLabel }}</span>
            <template #icon>
              <n-icon size="16">
                <icon-carbon-chevron-down />
              </n-icon>
            </template>
          </n-button>
        </n-popselect>
        <n-button v-if="canManageFolders" quaternary class="h-9" @click="showFolderModal">
          <template #icon>
            <n-icon size="16">
              <icon-tabler-folder-plus />
            </n-icon>
          </template>
          {{ $t("page.project.protocolFolders.manageAction") }}
        </n-button>
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
      <project-protocol-list :list="data" :folders="folders" @folders-updated="handleFoldersUpdated" />
    </template>
    <template #empty>
      <custom-empty
        v-if="searchQuery || !canCreateProtocol"
        :description="emptyDescription"
        class="size-full"
      />
      <div v-else-if="canCreateProtocol" class="flex flex-col px-10">
        <div class="mb-8">
          <div class="text-2xl font-bold">
            Create Airalogy Protocol
          </div>
          <div class="mt-2 text-gray-500">
            Every project requires an Airalogy Protocol to function. Please follow the steps below to create one.
          </div>
        </div>
        <protocol-steps :protocol-info="protocolInfo" :project-info="projectInfo" :route-query="false" @cancel="handleCancel" />
      </div>
    </template>
  </loading-list-wrapper>
  <n-modal
    :show="isFolderModalShown"
    preset="card"
    size="large"
    class="w-40rem"
    header-class="border-b !py-4 !px-5"
    content-class="!px-5 !py-5"
    @update:show="setFolderModalStatus"
  >
    <template #header>
      {{ $t("page.project.protocolFolders.manageTitle") }}
    </template>
    <div class="space-y-4">
      <div class="rounded-lg bg-gray-50 px-3 py-2 text-xs text-gray-500 leading-5 space-y-1">
        <div>{{ $t("page.project.protocolFolders.helperHint") }}</div>
        <div>{{ $t("page.project.protocolFolders.manageHint") }}</div>
      </div>
      <div class="flex items-center gap-2">
        <n-input
          v-model:value="newFolderName"
          :placeholder="$t('page.project.protocolFolders.namePlaceholder')"
          clearable
          class="flex-1"
          @keyup.enter="handleCreateFolder"
        />
        <n-button type="primary" :disabled="!newFolderName" @click="handleCreateFolder">
          {{ $t("common.create") }}
        </n-button>
      </div>
      <div class="border-t border-gray-200 pt-4">
        <div v-if="foldersLoading" class="py-6 text-center text-sm text-gray-500">
          {{ $t("page.project.protocolFolders.loading") }}
        </div>
        <div v-else class="space-y-2">
          <div v-for="folder in folders" :key="folder.id" class="flex items-center gap-2">
            <template v-if="editingFolderId === folder.id">
              <n-input v-model:value="editingFolderName" class="flex-1" />
              <n-button size="small" type="primary" @click="handleUpdateFolder(folder)">
                {{ $t("common.save") }}
              </n-button>
              <n-button size="small" @click="cancelEditFolder">
                {{ $t("common.cancel") }}
              </n-button>
            </template>
            <template v-else>
              <div class="flex-1 truncate">
                {{ folder.name }}
              </div>
              <div class="text-xs text-gray-500">
                {{ $t("page.project.protocolFolders.protocolCount", { count: folder.protocols_count || 0 }) }}
              </div>
              <n-button size="small" quaternary @click="handleManageFolderProtocols(folder)">
                {{ $t("page.project.protocolFolders.manageProtocolsAction") }}
              </n-button>
              <n-button size="small" quaternary @click="startEditFolder(folder)">
                {{ $t("page.project.protocolFolders.renameAction") }}
              </n-button>
              <n-button size="small" quaternary type="error" @click="handleDeleteFolder(folder)">
                {{ $t("common.delete") }}
              </n-button>
            </template>
          </div>
          <div v-if="folders.length === 0" class="py-6 text-center text-sm text-gray-500">
            {{ $t("page.project.protocolFolders.empty") }}
          </div>
        </div>
      </div>
    </div>
  </n-modal>
  <n-modal
    :show="isFolderProtocolsModalShown"
    preset="card"
    size="huge"
    class="w-160"
    header-class="border-b !py-4 !px-5"
    content-class="!px-5 !py-5"
    :mask-closable="false"
    @update:show="setFolderProtocolsModalStatus"
  >
    <template #header>
      {{ $t("page.project.protocolFolders.manageProtocolsTitle", { name: activeFolderForProtocols?.name || "" }) }}
    </template>
    <div class="space-y-4">
      <div class="rounded-lg bg-gray-50 px-3 py-2 text-xs text-gray-500">
        {{ $t("page.project.protocolFolders.manageProtocolsHint") }}
      </div>
      <n-spin :show="folderProtocolsLoading">
        <n-empty
          v-if="!folderProtocolsLoading && protocolTransferOptions.length === 0"
          :description="$t('page.project.protocolFolders.noProtocols')"
        />
        <n-transfer
          v-else
          v-model:value="selectedProtocolIds"
          :options="protocolTransferOptions"
          :filter="filterTransferProtocols"
          filterable
        />
      </n-spin>
    </div>
    <template #footer>
      <div class="flex items-center justify-end gap-2">
        <n-button :disabled="folderProtocolsSaving" @click="closeFolderProtocolsModal">
          {{ $t("common.cancel") }}
        </n-button>
        <n-button type="primary" :loading="folderProtocolsSaving" @click="handleSaveFolderProtocols">
          {{ $t("common.save") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type { FetchData, FetchPayload } from "@/components/common/loading-list-wrapper.vue"
import type { ProtocolModels } from "@airalogy/shared/types"
import type { PaginationInfo, SelectOption, TransferOption } from "naive-ui"
import ProtocolSteps from "@/components/apply-steps/protocol-steps.vue"
import LoadingListWrapper from "@/components/common/loading-list-wrapper.vue"
import { useProjectPermissions, useShowModal } from "@/composables"
import { useRouterPush } from "@/composables/useRouterPush"
import { fetchProtocols } from "@/service/api/project-protocols"
import { deleteProtocolFolder, fetchProtocolFolders, postProtocolFolder, putFolderProtocols, putProtocolFolder } from "@/service/api/protocol-folders"
import { useAuthStore } from "@/store/modules/auth"
import { useClosableMessage } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import { useRouteQuery } from "@vueuse/router"
import { useDialog } from "naive-ui"
import { useOrProvideProjectInfoStore } from "../project-protocols/hooks/useProjectInfoStore"
import { useProvideProtocolInfoStore } from "../project-protocols/hooks/useProtocolInfoStore"
import ProjectProtocolList from "./modules/project-protocol-list.vue"

defineOptions({
  name: "ProjectInfoProtocols",
})

const wrapperRef = ref<{ reload: () => Promise<any>, pagination: PaginationInfo }>()

const searchInputVal = ref("")
const searchQuery = useRouteQuery("q")
const filterOptions = computed<SelectOption[]>(() => ([
  { label: $t("page.project.protocolsFilter.id"), value: "id" },
  { label: $t("page.project.protocolsFilter.name"), value: "name" },
]))

const filterOption = ref<"id" | "name">("name")
const sortOptions = computed<SelectOption[]>(() => ([
  { label: $t("page.project.protocolsSort.stars"), value: "stars_count" },
  { label: $t("page.project.protocolsSort.popular"), value: "forks_count" },
  { label: $t("page.project.protocolsSort.updated"), value: "updated_at" },
]))
const sortOption = ref<"stars_count" | "forks_count" | "updated_at">("updated_at")

const route = useRoute()
const { projectInfo } = useOrProvideProjectInfoStore(null)
const { canCreateProtocol, canShowSettings } = useProjectPermissions(projectInfo)
const authStore = useAuthStore()

const message = useClosableMessage()
const dialog = useDialog()
const { isShown: isFolderModalShown, showModal: showFolderModal, setModalStatus: setFolderModalStatus } = useShowModal()
const {
  isShown: isFolderProtocolsModalShown,
  showModal: showFolderProtocolsModal,
  hideModal: hideFolderProtocolsModal,
  setModalStatus: setFolderProtocolsModalStatus,
} = useShowModal()

const folders = ref<Api.ProtocolFolder.Folder[]>([])
const foldersLoading = ref(false)
const newFolderName = ref("")
const editingFolderId = ref<number | null>(null)
const editingFolderName = ref("")
const activeFolderForProtocols = ref<Api.ProtocolFolder.Folder | null>(null)
const folderProtocolsLoading = ref(false)
const folderProtocolsSaving = ref(false)
const selectedProtocolIds = ref<string[]>([])
const projectProtocols = ref<ProtocolModels.ProjectProtocolInfo[]>([])

const canManageFolders = computed(() => canShowSettings.value)
const folderFilter = ref<string | number>("all")
const folderFilterOptions = computed<SelectOption[]>(() => {
  const base = [
    { label: $t("page.project.protocolFolders.filterAll"), value: "all" },
    { label: $t("page.project.protocolFolders.filterUncategorized"), value: "none" },
  ]
  const folderOptions = folders.value.map(folder => ({
    label: folder.name,
    value: folder.id,
  }))
  return [...base, ...folderOptions]
})
const selectedFolderLabel = computed(() => {
  const selected = folderFilterOptions.value.find(opt => opt.value === folderFilter.value)
  return selected?.label || $t("page.project.protocolFolders.filterAll")
})
const protocolTransferOptions = computed<TransferOption[]>(() =>
  projectProtocols.value.map(protocol => ({
    label: `${protocol.name || protocol.uid} (${protocol.uid})`,
    value: protocol.id,
  })),
)

watch(
  [() => projectInfo.value?.id, () => canManageFolders.value, () => authStore.isLogin],
  async ([projectId, canManage, isLoggedIn]) => {
    if (!projectId || !canManage || !isLoggedIn) {
      folders.value = []
      return
    }
    await loadFolders(projectId)
  },
  { immediate: true },
)

watch(
  () => folders.value,
  () => {
    if (typeof folderFilter.value === "number" && !folders.value.find(folder => folder.id === folderFilter.value)) {
      folderFilter.value = "all"
    }
  },
)

watch(
  () => isFolderProtocolsModalShown.value,
  (shown) => {
    if (!shown) {
      folderProtocolsLoading.value = false
      folderProtocolsSaving.value = false
      activeFolderForProtocols.value = null
      selectedProtocolIds.value = []
      projectProtocols.value = []
    }
  },
)

const emptyDescription = computed(() => {
  if (searchQuery.value) {
    return `No protocols found for ${filterOption.value === "name" ? "name" : "id"} "${searchQuery.value}"`
  }
  return "No protocols found"
})

async function fetcher(params: FetchPayload): Promise<FetchData> {
  const { labUid, projectUid } = route.params
  const { currentPage, currentPageSize, requestId } = params
  if (!projectUid || Array.isArray(projectUid)) {
    return null
  }

  try {
    const folderId = typeof folderFilter.value === "number" ? folderFilter.value : undefined
    const folderEmpty = folderFilter.value === "none"
    const { data, error } = await fetchProtocols({
      labUid: labUid as string,
      projectUid: projectUid as string,
      page: currentPage,
      pageSize: currentPageSize,
      // Legacy parameters (keep for backward compatibility)
      name: filterOption.value === "name" ? searchInputVal.value : undefined,
      uid: filterOption.value === "id" ? searchInputVal.value : undefined,
      // New parameters
      search_by: searchInputVal.value ? filterOption.value : undefined,
      search_str: searchInputVal.value || undefined,
      sorted_by: sortOption.value,
      folderId,
      folderEmpty,
    }, requestId)

    if (data) {
      const { protocols, total_count } = data
      if (total_count > 0 && protocols.length === 0 && currentPage > 1) {
        return await wrapperRef?.value?.reload()
      }

      return {
        list: protocols,
        total: total_count,
      }
    }
  }
  catch (e) {
    // NOPE
  }

  return null
}

const { routerPushByKey } = useRouterPush()

async function handleSearch(source: "input" | "sort" | "filter" | "clear" | "folder") {
  if (source === "filter" && !searchInputVal.value) {
    return
  }
  await wrapperRef.value?.reload()
}

// const protocolInfo = ref<UnitToProtocolInfo | null>(null)
const { protocolInfo } = useProvideProtocolInfoStore(null)

function handleCancel() {
  if (!protocolInfo.value) {
    return
  }
  const { lab, project, uid } = protocolInfo.value
  routerPushByKey("protocol-info", {
    params: {
      labUid: lab.uid,
      protocolUid: uid,
      projectUid: project.uid,
    },
  })
}

async function loadFolders(projectId: string) {
  foldersLoading.value = true
  try {
    const { data } = await fetchProtocolFolders(projectId, { page: 1, pageSize: 200 })
    if (data?.folders) {
      folders.value = data.folders
    }
  }
  catch (e) {
    // NOPE
  }
  finally {
    foldersLoading.value = false
  }
}

async function handleCreateFolder() {
  const name = newFolderName.value.trim()
  if (!name || !projectInfo.value?.id) {
    return
  }
  try {
    const { error } = await postProtocolFolder(projectInfo.value.id, { name })
    if (error) {
      return
    }
    newFolderName.value = ""
    await loadFolders(projectInfo.value.id)
    message.success($t("page.project.protocolFolders.createSuccess"))
  }
  catch (e) {
    // NOPE
  }
}

function startEditFolder(folder: Api.ProtocolFolder.Folder) {
  editingFolderId.value = folder.id
  editingFolderName.value = folder.name
}

function cancelEditFolder() {
  editingFolderId.value = null
  editingFolderName.value = ""
}

function filterTransferProtocols(pattern: string, option: TransferOption) {
  return option.label?.toString().toLowerCase().includes(pattern.toLowerCase())
}

async function fetchAllProjectProtocols(projectId: string) {
  const pageSize = 200
  let page = 1
  let totalCount = 0
  const list: ProtocolModels.ProjectProtocolInfo[] = []

  do {
    const { data } = await fetchProtocols({
      projectId,
      page,
      pageSize,
      sorted_by: "updated_at",
    })

    const protocols = data?.protocols || []
    totalCount = data?.total_count || 0
    list.push(...protocols)

    if (!protocols.length) {
      break
    }

    page += 1
  } while (list.length < totalCount)

  return list
}

async function handleManageFolderProtocols(folder: Api.ProtocolFolder.Folder) {
  if (!projectInfo.value?.id) {
    return
  }

  activeFolderForProtocols.value = folder
  selectedProtocolIds.value = []
  projectProtocols.value = []
  showFolderProtocolsModal()
  folderProtocolsLoading.value = true

  try {
    const protocols = await fetchAllProjectProtocols(projectInfo.value.id)
    projectProtocols.value = protocols
    selectedProtocolIds.value = protocols
      .filter(protocol => Array.isArray(protocol.folder_ids) && protocol.folder_ids.includes(folder.id))
      .map(protocol => protocol.id)
  }
  catch (e) {
    message.error($t("page.project.protocolFolders.loadProtocolsError"))
  }
  finally {
    folderProtocolsLoading.value = false
  }
}

function closeFolderProtocolsModal() {
  folderProtocolsLoading.value = false
  hideFolderProtocolsModal()
  activeFolderForProtocols.value = null
  selectedProtocolIds.value = []
  projectProtocols.value = []
}

async function handleUpdateFolder(folder: Api.ProtocolFolder.Folder) {
  const name = editingFolderName.value.trim()
  if (!name || !projectInfo.value?.id) {
    return
  }
  try {
    const { error } = await putProtocolFolder(projectInfo.value.id, folder.id, { name })
    if (error) {
      return
    }
    editingFolderId.value = null
    editingFolderName.value = ""
    await loadFolders(projectInfo.value.id)
    message.success($t("page.project.protocolFolders.updateSuccess"))
  }
  catch (e) {
    // NOPE
  }
}

function handleDeleteFolder(folder: Api.ProtocolFolder.Folder) {
  if (!projectInfo.value?.id) {
    return
  }
  const d = dialog.error({
    title: $t("page.project.protocolFolders.deleteTitle"),
    content: $t("page.project.protocolFolders.deleteDescription", { name: folder.name }),
    positiveText: $t("common.delete"),
    negativeText: $t("common.cancel"),
    onPositiveClick: async () => {
      d.loading = true
      try {
        const { error } = await deleteProtocolFolder(projectInfo.value!.id, folder.id)
        if (error) {
          return false
        }
        await loadFolders(projectInfo.value!.id)
        message.success($t("page.project.protocolFolders.deleteSuccess"))
        return true
      }
      catch (e) {
        return false
      }
      finally {
        d.loading = false
      }
    },
  })
}

async function handleSaveFolderProtocols() {
  const projectId = projectInfo.value?.id
  const folderId = activeFolderForProtocols.value?.id
  if (!projectId || !folderId) {
    return
  }

  folderProtocolsSaving.value = true
  try {
    const { error } = await putFolderProtocols(projectId, folderId, selectedProtocolIds.value)
    if (error) {
      return
    }
    await loadFolders(projectId)
    await wrapperRef.value?.reload()
    message.success($t("page.project.protocolFolders.saveProtocolsSuccess"))
    closeFolderProtocolsModal()
  }
  catch (e) {
    message.error($t("page.project.protocolFolders.saveProtocolsError"))
  }
  finally {
    folderProtocolsSaving.value = false
  }
}

async function handleFoldersUpdated() {
  if (projectInfo.value?.id) {
    await loadFolders(projectInfo.value.id)
  }
  if (folderFilter.value !== "all") {
    await wrapperRef.value?.reload()
  }
}
</script>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *
</style>
