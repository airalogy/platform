<template>
  <div class="w-full space-y-4">
    <n-cascader
      v-model:value="combinedId"
      :options="options"
      placeholder="Choose target project"
      check-strategy="child"
      :on-load="handleLoad"
      required
      remote
      :theme-overrides="{ columnWidth: '30vw', menuBorderRadius: '8px' }"
      :disabled="props.disableDefault && !!(props.defaultProject && props.defaultLab)"
      :default-value="defaultValue"
      v-bind="props.cascaderProps"
      @update-show="fetchLabs"
    >
      <template #empty>
        <n-empty description="No Project" size="small" />
      </template>
    </n-cascader>

    <n-data-table
      v-if="!!selectedProject && target === 'protocol'"
      v-model:checked-row-keys="checkedRowKeys"
      :columns="columns"
      :data="nodeListData"
      size="small"
      :pagination="{
        page: currentPage,
        pageSize: currentPageSize,
        size: 'small',
      }"
      :row-key="(row: ProtocolModels.ProjectProtocolInfo) => row.id"
      @update-expanded-row-keys="handleExpandChange"
    />

    <define-version-list v-slot="{ protocols: versions, loading, onSelect }">
      <n-spin :show="loading" size="small" class="min-h-6">
        <base-timeline-list
          v-if="versions?.length"
          :list="versions"
          :collapsed-item="{}"
          item-class="pb-2"
          label-class="-left-9 !text-4"
          class="pl-12"
          :icon-size="14"
          @show-detail="onSelect"
        >
          <template #prefix="{ item }">
            #{{ item.order }}
          </template>

          <template #content="{ item }">
            <div class="text-lg">
              v{{ item.version }}
            </div>
            <div>
              <n-text depth="3" size="tiny" class="text-gray-400">
                Updated by @{{ item.creator_name || 'Unknown' }}
              </n-text>
              <n-time :time="dayjs(item.created_at).toDate()" />
            </div>
          </template>

          <template #header="{ item }">
            <n-tag
              v-if="item.version === selectedVersion"
              type="primary"
              class="absolute-tr -top-2.5"
            >
              Selected
            </n-tag>
          </template>
        </base-timeline-list>
        <n-empty v-else-if="!loading" description="No versions available" />
      </n-spin>
    </define-version-list>
  </div>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types"
import type { CascaderOption, DataTableColumns } from "naive-ui"
import { groupProjectsByLabOptions } from "@/components/apply-steps/project-options"
import BaseTimelineList from "@/components/common/base-timeline-list.vue"
import { fetchProtocols } from "@/service/api/project-protocols"
import { fetchProjectList } from "@/service/api/projects"
import { getProtocolHistory } from "@/service/api/protocol"
import { fetchUserLabs } from "@/service/api/users"
import { useAuthStore } from "@/store/modules/auth"
import { useClosableMessage, usePagination } from "@airalogy/composables"
import { formatDate } from "@airalogy/shared/utils"
import { createReusableTemplate } from "@vueuse/core"
import dayjs from "dayjs"
import { NDataTable } from "naive-ui"

export type Option = CascaderOption & { uid: string, id: string }

export interface Lab {
  id: string
  uid: string
  name: string
  avatar?: string
}

export interface Project {
  id: string
  uid: string
  name: string
  avatar?: string
}

interface VersionInfo {
  versions: ProtocolModels.ProtocolVersion[] | null
  loading: boolean
}

interface TimelineItem {
  id: string | number
  time: string | number
  order: number
  version?: string
  creator_name?: string
  created_at?: string
}

interface VersionListProps {
  protocols: TimelineItem[] | null
  loading: boolean
  onSelect: (version: TimelineItem) => void
}

interface IProps {
  protocolInfo?: ProtocolModels.ProjectProtocolInfo | null
  excludeProjects?: string[]
  target?: "protocol" | "project"
  defaultProject?: Project | null
  defaultLab?: Lab | null
  cascaderProps?: Record<string, any>
  disableDefault?: boolean
}

const props = withDefaults(defineProps<IProps>(), {
  excludeProjects: () => [],
  target: "protocol",
  defaultProject: null,
  defaultLab: null,
  disableDefault: true,
  cascaderProps: () => ({}),
})

const emit = defineEmits<{
  "update:lab": [lab: Lab | null]
  "update:project": [project: Project | null]
  "update:node": [node: ProtocolModels.ProjectProtocolInfo | null]
}>()

const [DefineVersionList, ReuseVersionList] = createReusableTemplate<VersionListProps>()

const message = useClosableMessage()
const authStore = useAuthStore()

function createDefaultLabOption() {
  if (!props.defaultLab || !props.defaultProject) {
    return null
  }

  const defaultLab = props.defaultLab
  const defaultProject = props.defaultProject

  return {
    ...defaultLab,
    value: defaultLab.uid,
    label: `${defaultLab.name} (${defaultLab.uid})`,
    children: [
      {
        ...defaultProject,
        value: `${defaultLab.uid}|${defaultProject.uid}`,
        label: `${defaultProject.name} (${defaultProject.uid})`,
        isLeaf: true,
      },
    ],
  } as Option
}

function mergeWithDefaultLabOption(nextOptions: Option[]) {
  const defaultOption = createDefaultLabOption()
  if (!defaultOption) {
    return nextOptions
  }

  const mergedOptions = [...nextOptions]
  const existingIndex = mergedOptions.findIndex(option => option.id === defaultOption.id || option.uid === defaultOption.uid)

  if (existingIndex === -1) {
    return [defaultOption, ...mergedOptions]
  }

  const existingOption = mergedOptions[existingIndex]
  const existingChildren = (existingOption.children || []) as Option[]
  const defaultChild = (defaultOption.children?.[0] || null) as Option | null
  const hasDefaultChild = Boolean(
    defaultChild
    && existingChildren.some(child => child.id === defaultChild.id || child.uid === defaultChild.uid),
  )

  if (!hasDefaultChild && defaultChild) {
    existingOption.children = [defaultChild, ...existingChildren]
  }

  existingOption.label = defaultOption.label
  existingOption.id = defaultOption.id
  existingOption.uid = defaultOption.uid
  mergedOptions[existingIndex] = existingOption
  return mergedOptions
}

const options = ref<Option[]>(mergeWithDefaultLabOption([]))

const hasFetched = ref(false)
const checkedRowKeys = ref<string[]>([])
const nodeListData = ref<ProtocolModels.ProjectProtocolInfo[]>([])
const total = ref(0)
const defaultValue = computed(() => {
  if (props.defaultProject?.uid && props.defaultLab?.uid) {
    return [props.defaultLab.uid, props.defaultProject.uid].join("|")
  }
  return null
})

const combinedId = ref<string | null>(defaultValue.value)

// Keep the default project option available even when user is not a lab member.
watch(defaultValue, (newVal) => {
  options.value = mergeWithDefaultLabOption(options.value)
  if (newVal) {
    combinedId.value = newVal
  }
}, { immediate: true })

const selectedProject = ref<Project | null>(props.defaultProject || null)
const versionMap = ref<Map<string | number, VersionInfo>>(new Map())
const selectedVersion = ref<string | null>(null)

const { currentPage, currentPageSize } = usePagination({
  options: { page: 1, pageSize: 6, total },
  fetchData: async () => {
    await handleGetProtocols()
  },
})

async function handleGetProtocols() {
  const [labUid, projectUid] = combinedId.value?.split("|") || []
  if (!projectUid || !labUid) {
    nodeListData.value = []
    total.value = 0
    return
  }

  try {
    const res = await fetchProtocols({
      projectUid,
      labUid,
      page: currentPage.value,
      pageSize: currentPageSize.value,
    })
    if (res.data) {
      const { protocols, total_count } = res.data
      const currProtocolId = props.protocolInfo?.id
      const hasCurrentNode = Boolean(currProtocolId) && protocols.some(protocol => protocol.id === currProtocolId)

      nodeListData.value = hasCurrentNode ? protocols.filter(unit => unit.id !== currProtocolId) : protocols
      total.value = hasCurrentNode ? total_count - 1 : total_count
    }
  }
  catch (e) {
    message.error((e as Error).message)
    nodeListData.value = []
    total.value = 0
  }
}

async function fetchLabs(show: boolean) {
  if (!show || hasFetched.value)
    return

  try {
    if (props.target === "project") {
      const data = await fetchProjectList({
        permissionAction: "create_protocol",
        page: 1,
        pageSize: 9999,
      })

      if (data) {
        options.value = mergeWithDefaultLabOption(groupProjectsByLabOptions(data.projects, props.excludeProjects))
      }
      return
    }

    const data = await fetchUserLabs(authStore.userInfo.id, {
      page: 1,
      pageSize: 9999,
    })

    if (data) {
      const fetchedOptions = data.labs.map(({ name, id, uid }): Option => {
        const option: Option = {
          label: `${name} (${uid})`,
          value: uid,
          depth: 1,
          isLeaf: false,
          id,
          uid,
        }

        if (id === props.defaultLab?.id && props.defaultProject) {
          option.children = [{
            ...props.defaultProject,
            value: `${props.defaultLab.uid}|${props.defaultProject.uid}`,
            label: `${props.defaultProject.name} (${props.defaultProject.uid})`,
            isLeaf: true,
          },
          ]
        }

        return option
      })
      options.value = mergeWithDefaultLabOption(fetchedOptions)
    }
  }
  catch (e) {
    message.error((e as Error).message)
  }
  finally {
    hasFetched.value = true
  }
}

async function handleLoad(option: CascaderOption) {
  if (props.target === "project") {
    return
  }

  const { value, id: labId } = option

  try {
    const data = await fetchProjectList({
      labId: labId as string,
      page: 1,
      pageSize: 9999,
    })
    if (data) {
      const children = data.projects.filter(project => !props.excludeProjects.includes(project.uid)).map(({ uid, name, id }) => ({
        label: `${name} (${uid})`,
        value: `${value}|${uid}`,
        depth: 2,
        isLeaf: true,
        uid,
        id,
      }))
      await nextTick(() => {
        option.children = children
      })
    }
  }
  catch (e) {
    message.error((e as Error).message)
  }
}

const columns: DataTableColumns<ProtocolModels.ProjectProtocolInfo> = [
  {
    type: "selection",
    multiple: false,
  },
  {
    type: "expand",
    renderExpand: (rowData: ProtocolModels.ProjectProtocolInfo) => {
      const versionInfo = versionMap.value.get(rowData.id)

      if (!versionInfo) {
        return ""
      }

      if (!versionInfo.loading && !versionInfo.versions?.length) {
        return "No version history"
      }

      const formattedVersions = versionInfo.versions ? formatVersions(versionInfo.versions) : null

      return h(ReuseVersionList, {
        protocols: formattedVersions,
        loading: versionInfo.loading,
        onSelect: version => handleVersionSelect(rowData, version),
      })
    },
    expandable: (rowData: ProtocolModels.ProjectProtocolInfo) => {
      return !!rowData.latest_version
    },
  },
  {
    title: "Name",
    key: "name",
  },
  {
    title: "ID",
    key: "uid",
  },
  {
    title: "Version",
    key: "current_node_version",
  },
  {
    title: "Created At",
    key: "created_at",
    render: row => formatDate(row.created_at, "date-short"),
  },
]

async function handleExpandChange(keys: Array<string | number>) {
  if (!keys.length) {
    return
  }

  const promises = keys.map(async (key) => {
    const existing = versionMap.value.get(key)
    if (existing?.versions) {
      return
    }

    versionMap.value.set(key, { versions: null, loading: true })

    try {
      const res = await getProtocolHistory({ id: key as string, page: 1, pageSize: 9999 })
      if (res && res.versions) {
        versionMap.value.set(key, { versions: res.versions, loading: false })
      }
    }
    catch (e) {
      message.error((e as Error).message)
      versionMap.value.set(key, { versions: null, loading: false })
    }
  })

  await Promise.all(promises)
}

function handleVersionSelect(research: ProtocolModels.ProjectProtocolInfo, version: TimelineItem) {
  selectedVersion.value = version.version || null
  if (version.version) {
    emit("update:node", {
      ...research,
      latest_version: version.version,
    })
  }
}

watch(
  combinedId,
  async (newVal) => {
    checkedRowKeys.value = []
    selectedVersion.value = null

    if (newVal) {
      const selectedOption = options.value
        .flatMap(opt => opt.children || [])
        .find((opt): opt is Option => opt.value === newVal)

      if (selectedOption) {
        const lab = options.value.find(opt => opt.children?.some(child => child.value === newVal))
        if (lab) {
          const labData: Lab = {
            id: lab.id || "",
            uid: lab.uid || "",
            name: (lab.label as string).split(" (")[0],
          }
          const projectData: Project = {
            id: selectedOption.id || "",
            uid: selectedOption.uid || "",
            name: (selectedOption.label as string).split(" (")[0],
          }
          selectedProject.value = projectData
          emit("update:lab", labData)
          emit("update:project", projectData)

          if (props.target === "protocol") {
            await handleGetProtocols()
          }
          return
        }
      }
    }

    selectedProject.value = null
    nodeListData.value = []
    emit("update:lab", null)
    emit("update:project", null)
  },
  { immediate: true },
)

watch(
  [currentPage, currentPageSize],
  async () => {
    await handleGetProtocols()
  },
)

watch(checkedRowKeys, (newKeys) => {
  if (newKeys.length === 0) {
    emit("update:node", null)
    return
  }
  const selectedNode = nodeListData.value.find(node => String(node.id) === String(newKeys[0]))
  emit("update:node", selectedNode || null)
})

function formatVersions(versions: ProtocolModels.ProtocolVersion[]): TimelineItem[] {
  return versions.map((version, index): TimelineItem => {
    const createdAt = version.created_at || new Date().toISOString()
    return {
      id: version.id || `version-${index}`,
      time: new Date(createdAt).getTime(),
      order: versions.length - index,
      version: version.version,
      creator_name: version.meta_data?.authors?.[0]?.name || "Unknown",
      created_at: createdAt,
    }
  })
}
</script>
