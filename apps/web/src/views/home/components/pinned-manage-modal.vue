<template>
  <n-button size="small" quaternary class="pinned-manage-btn" @click.stop="showModal">
    <template #icon>
      <n-icon :component="PinnedIcon" :size="14" />
    </template>
    {{ $t("page.home.pinnedManage") }}
  </n-button>

  <n-modal
    :show="isShown"
    preset="card"
    :title="$t('page.home.pinnedManageTitle')"
    :bordered="false"
    size="huge"
    class="w-200"
    :mask-closable="true"
    @update:show="setModalStatus"
  >
    <n-tabs v-model:value="activeTab" type="segment">
      <n-tab-pane name="labs" :tab="$t('page.home.pinnedTabLabs')">
        <div class="mb-4 flex items-center gap-3">
          <n-input
            v-model:value="searchQuery"
            clearable
            :placeholder="$t('page.home.pinnedSearchLabsPlaceholder')"
          />
          <span class="ml-auto text-3 text-gray-500">
            {{ $t("page.home.pinnedLimitHint", { count: props.maxCount }) }}
          </span>
        </div>
        <n-spin :show="loading.labs" class="min-h-40">
          <n-list v-if="filteredLabs.length > 0" class="pinned-manage-list" hoverable>
            <n-list-item v-for="lab in filteredLabs" :key="lab.id">
              <div class="flex w-full items-center gap-3">
                <n-tooltip
                  :disabled="!isLimitDisabled(PinnedResourceType.Lab, lab.id)"
                  placement="top"
                >
                  <template #trigger>
                    <n-checkbox
                      :checked="isPinned(PinnedResourceType.Lab, lab.id)"
                      :disabled="isCheckboxDisabled(PinnedResourceType.Lab, lab.id)"
                      @update:checked="(checked: boolean) => handleToggle(PinnedResourceType.Lab, lab.id, checked)"
                    />
                  </template>
                  {{ $t("page.home.pinnedLimitReached", { count: props.maxCount }) }}
                </n-tooltip>
                <div class="min-w-0 flex-1">
                  <n-ellipsis class="font-500">
                    {{ lab.name || lab.uid }}
                  </n-ellipsis>
                  <div class="text-3 text-gray-500">
                    {{ formatNumber(lab.projects_count || 0) }} {{ $t("page.home.pinnedProjects") }}
                    ·
                    {{ formatNumber(lab.users_count || 0) }} {{ $t("page.home.pinnedMembers") }}
                  </div>
                </div>
              </div>
            </n-list-item>
          </n-list>
          <n-empty v-else :description="$t('page.home.pinnedEmptyResults')" />
        </n-spin>
      </n-tab-pane>

      <n-tab-pane name="projects" :tab="$t('page.home.pinnedTabProjects')">
        <div class="mb-4 flex items-center gap-3">
          <n-input
            v-model:value="searchQuery"
            clearable
            :placeholder="$t('page.home.pinnedSearchProjectsPlaceholder')"
          />
          <span class="ml-auto text-3 text-gray-500">
            {{ $t("page.home.pinnedLimitHint", { count: props.maxCount }) }}
          </span>
        </div>
        <n-spin :show="loading.projects" class="min-h-40">
          <n-list v-if="filteredProjects.length > 0" class="pinned-manage-list" hoverable>
            <n-list-item v-for="project in filteredProjects" :key="project.id">
              <div class="flex w-full items-center gap-3">
                <n-tooltip
                  :disabled="!isLimitDisabled(PinnedResourceType.Project, project.id)"
                  placement="top"
                >
                  <template #trigger>
                    <n-checkbox
                      :checked="isPinned(PinnedResourceType.Project, project.id)"
                      :disabled="isCheckboxDisabled(PinnedResourceType.Project, project.id)"
                      @update:checked="(checked: boolean) => handleToggle(PinnedResourceType.Project, project.id, checked)"
                    />
                  </template>
                  {{ $t("page.home.pinnedLimitReached", { count: props.maxCount }) }}
                </n-tooltip>
                <div class="min-w-0 flex-1">
                  <n-ellipsis class="font-500">
                    {{ project.name || project.uid }}
                  </n-ellipsis>
                  <div class="text-3 text-gray-500">
                    {{ project.lab_name || project.lab_uid }}
                  </div>
                </div>
              </div>
            </n-list-item>
          </n-list>
          <n-empty v-else :description="$t('page.home.pinnedEmptyResults')" />
        </n-spin>
      </n-tab-pane>

      <n-tab-pane name="protocols" :tab="$t('page.home.pinnedTabProtocols')">
        <div class="mb-4 flex items-center gap-3">
          <n-input
            v-model:value="searchQuery"
            clearable
            :placeholder="$t('page.home.pinnedSearchProtocolsPlaceholder')"
          />
          <span class="ml-auto text-3 text-gray-500">
            {{ $t("page.home.pinnedLimitHint", { count: props.maxCount }) }}
          </span>
        </div>
        <n-spin :show="loading.protocols" class="min-h-40">
          <n-list v-if="filteredProtocols.length > 0" class="pinned-manage-list" hoverable>
            <n-list-item v-for="protocol in filteredProtocols" :key="protocol.id">
              <div class="flex w-full items-center gap-3">
                <n-tooltip
                  :disabled="!isLimitDisabled(PinnedResourceType.Protocol, protocol.id)"
                  placement="top"
                >
                  <template #trigger>
                    <n-checkbox
                      :checked="isPinned(PinnedResourceType.Protocol, protocol.id)"
                      :disabled="isCheckboxDisabled(PinnedResourceType.Protocol, protocol.id)"
                      @update:checked="(checked: boolean) => handleToggle(PinnedResourceType.Protocol, protocol.id, checked)"
                    />
                  </template>
                  {{ $t("page.home.pinnedLimitReached", { count: props.maxCount }) }}
                </n-tooltip>
                <div class="min-w-0 flex-1">
                  <n-ellipsis class="font-500">
                    {{ protocol.name || protocol.uid }}
                  </n-ellipsis>
                  <div class="text-3 text-gray-500">
                    {{ protocol.lab?.name || protocol.lab?.uid }}
                    <span v-if="protocol.project" class="mx-1">/</span>
                    {{ protocol.project?.name || protocol.project?.uid }}
                  </div>
                </div>
              </div>
            </n-list-item>
          </n-list>
          <n-empty v-else :description="$t('page.home.pinnedEmptyResults')" />
        </n-spin>
      </n-tab-pane>
    </n-tabs>
  </n-modal>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types"
import { useClosableMessage, useShowModal } from "@/composables"
import { type PinnedItem, PinnedResourceType } from "@/service/api/pinned-items"
import { fetchUserLabs, fetchUserProjects, fetchUserProtocols } from "@/service/api/users"
import { useAuthStore } from "@/store/modules/auth"
import { formatNumber } from "@airalogy/shared"
import { $t } from "@airalogy/shared/locales"
import PinnedIcon from "~icons/tabler/pinned"

interface Props {
  pinnedMap?: Map<string, PinnedItem>
  pinningKeys?: Set<string>
  maxCount?: number
}

const props = withDefaults(defineProps<Props>(), {
  pinnedMap: () => new Map<string, PinnedItem>(),
  pinningKeys: () => new Set<string>(),
  maxCount: 10,
})

const emits = defineEmits<{
  (ev: "togglePin", payload: { resourceType: PinnedResourceType, resourceId: string }): void
}>()

const { userInfo } = useAuthStore()
const message = useClosableMessage()
const { isShown, showModal, setModalStatus } = useShowModal()

const activeTab = ref<"labs" | "projects" | "protocols">("labs")
const searchQuery = ref("")
const labs = ref<Api.Lab.LabInfo[]>([])
const projects = ref<Api.Project.MyProjectInfo[]>([])
const protocols = ref<ProtocolModels.ProjectProtocolInfo[]>([])
const loaded = reactive({
  labs: false,
  projects: false,
  protocols: false,
})
const loading = reactive({
  labs: false,
  projects: false,
  protocols: false,
})

const selectedCount = computed(() => props.pinnedMap?.size || 0)

function getKey(type: PinnedResourceType, id?: string) {
  if (!id) {
    return null
  }
  return `${type}:${id}`
}

function isPinned(type: PinnedResourceType, id?: string) {
  const key = getKey(type, id)
  if (!key || !props.pinnedMap) {
    return false
  }
  return props.pinnedMap.has(key)
}

function isPinning(type: PinnedResourceType, id?: string) {
  const key = getKey(type, id)
  if (!key || !props.pinningKeys) {
    return false
  }
  return props.pinningKeys.has(key)
}

function isLimitDisabled(type: PinnedResourceType, id?: string) {
  if (isPinned(type, id)) {
    return false
  }
  return selectedCount.value >= props.maxCount
}

function isCheckboxDisabled(type: PinnedResourceType, id?: string) {
  if (isPinning(type, id)) {
    return true
  }
  return isLimitDisabled(type, id)
}

function handleToggle(type: PinnedResourceType, id: string, checked: boolean) {
  if (!id) {
    return
  }
  if (checked && selectedCount.value >= props.maxCount) {
    message.warning($t("page.home.pinnedLimitReached", { count: props.maxCount }))
    return
  }
  if (checked !== isPinned(type, id)) {
    emits("togglePin", { resourceType: type, resourceId: id })
  }
}

function matchesSearch(values: Array<string | undefined>) {
  const query = searchQuery.value.trim().toLowerCase()
  if (!query) {
    return true
  }
  return values.some(value => value?.toLowerCase().includes(query))
}

const filteredLabs = computed(() => {
  return labs.value
    .filter(lab => matchesSearch([lab.name, lab.uid]))
    .sort((a, b) => Number(isPinned(PinnedResourceType.Lab, b.id)) - Number(isPinned(PinnedResourceType.Lab, a.id)))
})

const filteredProjects = computed(() => {
  return projects.value
    .filter(project => matchesSearch([project.name, project.uid, project.lab_name, project.lab_uid]))
    .sort((a, b) => Number(isPinned(PinnedResourceType.Project, b.id)) - Number(isPinned(PinnedResourceType.Project, a.id)))
})

const filteredProtocols = computed(() => {
  return protocols.value
    .filter(protocol =>
      matchesSearch([
        protocol.name,
        protocol.uid,
        protocol.lab?.name,
        protocol.lab?.uid,
        protocol.project?.name,
        protocol.project?.uid,
      ]),
    )
    .sort((a, b) => Number(isPinned(PinnedResourceType.Protocol, b.id)) - Number(isPinned(PinnedResourceType.Protocol, a.id)))
})

async function loadLabs() {
  if (loaded.labs || !userInfo?.id) {
    return
  }
  loading.labs = true
  try {
    const items: Api.Lab.LabInfo[] = []
    let page = 1
    const pageSize = 100
    while (true) {
      const data = await fetchUserLabs(userInfo.id, { page, pageSize, sortedBy: "updated_at" })
      if (!data) {
        break
      }
      items.push(...data.labs)
      if (items.length >= data.total_count || data.labs.length < pageSize) {
        break
      }
      page += 1
    }
    labs.value = items
  }
  finally {
    loading.labs = false
    loaded.labs = true
  }
}

async function loadProjects() {
  if (loaded.projects || !userInfo?.id) {
    return
  }
  loading.projects = true
  try {
    const items: Api.Project.MyProjectInfo[] = []
    let page = 1
    const pageSize = 100
    while (true) {
      const data = await fetchUserProjects(userInfo.id, { page, pageSize, sortedBy: "updated_at" })
      if (!data) {
        break
      }
      items.push(...data.projects)
      if (items.length >= data.total_count || data.projects.length < pageSize) {
        break
      }
      page += 1
    }
    projects.value = items
  }
  finally {
    loading.projects = false
    loaded.projects = true
  }
}

async function loadProtocols() {
  if (loaded.protocols || !userInfo?.id) {
    return
  }
  loading.protocols = true
  try {
    const items: ProtocolModels.ProjectProtocolInfo[] = []
    let page = 1
    const pageSize = 100
    while (true) {
      const data = await fetchUserProtocols(userInfo.id, { page, pageSize, sortedBy: "updated_at" })
      if (!data) {
        break
      }
      items.push(...data.protocols)
      if (items.length >= data.total_count || data.protocols.length < pageSize) {
        break
      }
      page += 1
    }
    protocols.value = items
  }
  finally {
    loading.protocols = false
    loaded.protocols = true
  }
}

watch([isShown, activeTab], ([show, tab]) => {
  if (!show) {
    return
  }
  if (tab === "labs") {
    loadLabs()
  }
  else if (tab === "projects") {
    loadProjects()
  }
  else {
    loadProtocols()
  }
}, { immediate: false })
</script>

<style scoped lang="sass">
.pinned-manage-btn
  padding: 0 8px

.pinned-manage-list
  max-height: 480px
  overflow: auto
</style>
