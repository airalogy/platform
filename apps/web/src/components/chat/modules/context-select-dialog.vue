<template>
  <n-modal
    v-model:show="modelValue" :title="modalTitle"
    preset="card" class="max-w-70vw min-w-2xl" @after-leave="handleAfterLeave"
  >
    <n-space vertical>
      <!-- Lab & Project Selection -->
      <n-form-item :label="formItemLabel" required>
        <n-cascader
          v-model:value="selectedPath" :options="options"
          :default-value="props.defaultSelectedPath"
          :placeholder="type === 'record' ? 'Choose a protocol' : 'Choose a project'" check-strategy="child"
          :on-load="handleLoad" remote :render-label="renderCascaderLabel"
          :ellipsis-tag-popover-props="{ placement: 'right' }"
          :theme-overrides="{ columnWidth: '340px', menuBorderRadius: '10px' }" @update:show="fetchLabs"
        >
          <template #empty>
            <n-empty description="No data" />
          </template>
          <template #not-found>
            <n-empty description="No matching data" />
          </template>
        </n-cascader>
      </n-form-item>

      <!-- Records Table -->
      <n-form-item :label="endFormItemLabel">
        <n-space v-if="props.type === 'record'" vertical class="w-full">
          <n-input
            v-model:value="recordSearchQuery"
            clearable
            :disabled="props.source !== 'editor' && !selectedPath"
            placeholder="Search existing Airalogy Record ID"
          >
            <template #prefix>
              <n-icon :size="14">
                <icon-ion-search />
              </n-icon>
            </template>
          </n-input>

          <n-data-table
            v-if="props.source === 'editor' || selectedPath"
            v-model:checked-row-keys="checkedRowKeys"
            remote
            :columns="columns"
            :data="contextData"
            :loading="loading"
            :pagination="pagination"
            :row-key="(row: any) => String(row?.id ?? row?.record_id ?? '')"
            min-height="20vh"
            max-height="50vh"
            @update:page="handlePageChange"
            @update:checked-row-keys="handleCheckedRowKeysUpdate"
          />
          <n-empty v-else description="Please select a protocol to view records" class="mt-6 w-full" />
        </n-space>

        <n-data-table
          v-else-if="props.source === 'editor' || selectedPath"
          v-model:checked-row-keys="checkedRowKeys"
          remote
          :columns="columns"
          :data="contextData"
          :loading="loading"
          :pagination="pagination"
          :row-key="(row: any) => String(row?.id ?? row?.record_id ?? '')"
          min-height="20vh"
          max-height="50vh"
          @update:page="handlePageChange"
          @update:checked-row-keys="handleCheckedRowKeysUpdate"
        />
        <n-empty v-else description="Please select a project to view protocols" class="mt-6 w-full" />
      </n-form-item>
      <!-- Selected Items Section -->
      <div v-if="selectedItemsMap.size > 0" class="flex flex-wrap items-center gap-2">
        <div class="w-full text-sm">
          Selected {{ selectedItemTypeLabel }}:
        </div>
        <context-tag v-for="[id, item] in selectedItemsMap" :key="id" :context="item" :closeable="item.removable && !props.readonlyList.includes(id)" @close="handleRemoveItem" />
      </div>
    </n-space>

    <template #action>
      <n-flex>
        <n-button class="ml-auto" @click="handleCancel">
          Cancel
        </n-button>
        <n-button
          type="primary" :disabled="(props.source !== 'editor' && !selectedPath) || !checkedRowKeys.length"
          @click="handleConfirm"
        >
          Confirm
        </n-button>
      </n-flex>
    </template>
  </n-modal>
</template>

<script setup lang="tsx">
import type { ContextDialogState } from "@airalogy/components/chat/providers/useChatProvider"
import type { ProtocolDocument } from "@airalogy/components/monaco-editor/types/document"
import type { ProtocolModels } from "@airalogy/shared"
import type { CascaderOption, DataTableColumns } from "naive-ui"
import { useClosableMessage, useLoading, useOpenNewTab } from "@/composables"
import { fetchProtocolRecords, fetchProtocols } from "@/service/api/project-protocols"
import { fetchProjectList } from "@/service/api/projects"
import { fetchUserLabs } from "@/service/api/users"
import { useAuthStore } from "@/store/modules/auth"
import ContextTag from "@airalogy/components/chat/modules/context-tag.vue"
import CopyToClip from "@airalogy/components/copy-to-clip.vue"
import { useProtocolDocumentsStore } from "@airalogy/components/monaco-editor/store/protocolDocumentsStore"
import { formatDate } from "@airalogy/shared/utils"
import { useDebounceFn } from "@vueuse/core"
import { NButton, NDataTable, NEllipsis, NIcon, NInput, NSpace, NTag, NText } from "naive-ui"

const props = withDefaults(defineProps<ContextDialogState & { source: Chat.ChatSource }>(), {
  defaultSelectedOptions: () => [],
  readonlyList: () => [],
  source: "protocol",
})

const emit = defineEmits<IEmits>()
interface IEmits {
  (e: "update:show", value: boolean): void
  (e: "update:selected", value: string[]): void
  (
    e: "confirm",
    value: (Chat.ChatContext & { version?: number })[],
  ): void
}

const message = useClosableMessage()
const authStore = useAuthStore()
const protocolDocumentsStore = useProtocolDocumentsStore()
const hasFetched = ref(false)

const selectedPath = ref<string | undefined>(props.defaultSelectedPath)
const options = ref<CascaderOption[]>(props.defaultSelectedOptions)
const contextData = ref<((ProtocolModels.RecordInfo & { id: string }) | ProtocolModels.ProjectProtocolInfo | ProtocolDocument)[]>([])
const checkedRowKeys = ref<string[]>([])
const selectedItemsMap = ref<Map<string, Chat.ChatContext>>(new Map())
const recordSearchQuery = ref("")

function handleCheckedRowKeysUpdate(keys: Array<string | number>) {
  checkedRowKeys.value = keys.map(key => String(key))
}

const selectedProtocolInfo = computed((): ProtocolModels.ProjectProtocolInfo | null => {
  if (selectedPath.value) {
    const [labId, projectId, protocolId] = selectedPath.value.split("_")

    // Find the lab option
    const labOption = options.value.find(opt => String(opt.value) === labId)
    if (!labOption?.children)
      return null

    // Find the project option
    const projectOption = labOption.children.find(opt => String(opt.value) === `${labId}_${projectId}`)
    if (!projectOption?.children)
      return null

    // Find the protocol option
    const protocolOption = projectOption.children.find(opt => String(opt.value) === `${labId}_${projectId}_${protocolId}`)
    if (!protocolOption) {
      return null
    }

    return {
      id: protocolId,
      uid: protocolOption.uid,
      name: protocolOption.label!,
      lab: {
        uid: labOption.uid as string,
        name: labOption.label,
        id: labOption.value,
      },
      project: {
        uid: projectOption.uid as string,
        name: projectOption.label,
        id: projectOption.value,
      },
    } as ProtocolModels.ProjectProtocolInfo
  }

  return null
})

// Initialize checked rows based on selected prop
watch(
  () => props.show,
  (show) => {
    if (show) {
      checkedRowKeys.value = props.selected.map(id => String(id))
      options.value = props.defaultSelectedOptions
      selectedPath.value = props.defaultSelectedPath
      recordSearchQuery.value = ""
    }
  },
)

function transformItem(item: ProtocolModels.RecordInfo | ProtocolModels.ProjectProtocolInfo | ProtocolDocument): Chat.ChatContext | undefined {
  console.log("transformItem called with:", {
    type: props.type,
    itemType: typeof item,
    source: props.source,
    item,
  })

  if (props.source === "editor" && props.type === "document") {
    const { id } = item as ProtocolDocument

    return {
      id,
      airalogyId: `airalogy.id.document.${id}`,
      type: "document",
      item,
    } as Chat.ChatDocumentContext
  }
  else if (props.type === "record") {
    if (!selectedProtocolInfo.value) {
      return undefined
    }

    const { airalogy_record_id } = item as ProtocolModels.RecordInfo

    const { lab, project, uid, name, id } = selectedProtocolInfo.value

    return {
      ...item,
      id: String((item as any).id ?? (item as ProtocolModels.RecordInfo).record_id ?? ""),
      type: "record",
      airalogyId: airalogy_record_id,
      item,
      removable: true,
      lab,
      project,
      protocol: { name, uid, id },
    } as Chat.ChatRecordContext
  }
  else if (props.type === "protocol") {
    const { id, lab, project, uid, airalogy_id, name } = item as ProtocolModels.ProjectProtocolInfo

    return {
      id,
      type: "protocol",
      airalogyId: airalogy_id,
      item,
      lab,
      project,
      protocol: {
        name,
        uid,
        id,
      },
      removable: !props.readonlyList.includes(id),
    } as Chat.ChatProtocolContext
  }
}

// Update selectedItemsMap when data changes
const isSyncingSelection = ref(false)
watch([contextData, checkedRowKeys], ([newData, newKeys]) => {
  const normalizedKeys = newKeys.map(key => String(key))
  if (isSyncingSelection.value) {
    return
  }
  isSyncingSelection.value = true
  // Remove unchecked items
  selectedItemsMap.value.forEach((_, id) => {
    if (!normalizedKeys.includes(id)) {
      selectedItemsMap.value.delete(id)
    }
  })

  // Add newly checked items
  newData.forEach((item: (ProtocolModels.RecordInfo & { id: string }) | ProtocolModels.ProjectProtocolInfo | ProtocolDocument) => {
    if (normalizedKeys.includes(String(item.id))) {
      const transformedItem = transformItem(item)
      if (transformedItem) {
        selectedItemsMap.value.set(item.id, transformedItem)
      }
    }
  })
  nextTick(() => {
    isSyncingSelection.value = false
  })
}, { immediate: true })

function handleAfterLeave() {
  checkedRowKeys.value = []
  options.value = []
  selectedPath.value = undefined
  contextData.value = []
  recordSearchQuery.value = ""
  selectedItemsMap.value.clear()
  hasFetched.value = false
}

async function handleLoad(option: CascaderOption) {
  const { value, depth } = option

  try {
    if (depth === 1) {
      // Load projects for lab
      const data = await fetchProjectList({
        labId: value as string,
        page: 1,
        pageSize: 9999,
      })
      if (data) {
        const children = data.projects.map(({ id, uid, name }) => ({
          label: name,
          value: `${value}_${id}`,
          depth: 2,
          isLeaf: props.type === "protocol",
          uid,
        }))
        await nextTick(() => {
          option.children = children
        })
      }
      else {
        option.children = []
      }
    }
    else if (depth === 2 && props.type === "record") {
      const [_labId, projectId] = (value as string).split("_")
      const data = await fetchProtocols({
        projectId,
        page: 1,
        pageSize: 9999,
      })

      if (data?.data) {
        const children = data.data.protocols.map(({ id, uid, name, records_count }) => ({
          label: name,
          value: `${value}_${id}`,
          depth: 3,
          isLeaf: true,
          uid,
          count: records_count,
        }))
        await nextTick(() => {
          option.children = children
        })
      }
      else {
        option.children = []
      }
    }
  }
  catch (e) {
    message.error((e as Error).message)
  }
}

async function fetchLabs(show: boolean, reset = false) {
  if (!show || hasFetched.value)
    return

  if (reset) {
    selectedPath.value = ""
  }

  try {
    const data = await fetchUserLabs(authStore.userInfo.id, {
      page: 1,
      pageSize: 9999,
    })

    if (data) {
      const filteredOptions = data.labs.map((it) => {
        const { name, id, uid } = it
        return {
          label: name,
          value: String(id),
          depth: 1,
          isLeaf: false,
          uid,
        }
      }) as CascaderOption[]

      options.value = filteredOptions

      // If we have a selected path, find the lab and preserve its children
      if (!selectedPath.value) {
        await nextTick(() => {
          hasFetched.value = true
        })
        return
      }

      const [labId, projectId] = selectedPath.value.split("_")
      const currentLabOption = filteredOptions.find(opt => String(opt.value) === labId)

      if (currentLabOption) {
        await handleLoad(currentLabOption)
      }

      const targetProjectOptions = currentLabOption?.children?.find(opt => String(opt.value) === `${labId}_${projectId}`)

      if (targetProjectOptions) {
        await handleLoad(targetProjectOptions)
      }

      options.value = filteredOptions
    }
    await nextTick(() => {
      hasFetched.value = true
    })
  }
  catch (e) {
    message.error((e as Error).message)
  }
}

const { loading, startLoading, endLoading } = useLoading()
const pagination = reactive({
  page: 1,
  itemCount: 0,
  pageSize: 5,
})

const { openNewTab } = useOpenNewTab()

async function fetchContextData(path: string, page: number, pageSize: number) {
  if (!path)
    return null

  const [_labId, projectId, protocolId] = path.split("_")

  try {
    if (props.source === "editor" && props.type === "document") {
      // Get documents from the protocolDocumentsStore
      return {
        items: protocolDocumentsStore.documents,
        total: protocolDocumentsStore.documents.length,
      }
    }
    else if (props.type === "record") {
      const response = await fetchProtocolRecords(protocolId, {
        page,
        pageSize,
        q: recordSearchQuery.value.trim() || undefined,
      })

      if (response?.data) {
        return {
          items: response.data.records.map(it => ({
            ...it,
            id: String((it as ProtocolModels.RecordInfo).record_id ?? (it as any).id ?? ""),
            airalogyId: (it as ProtocolModels.RecordInfo).airalogy_record_id,
          })),
          total: response.data.total_count,
        }
      }
    }
    else if (props.type === "protocol") {
      const response = await fetchProtocols({
        projectId,
        page,
        pageSize,
      })

      if (response?.data) {
        return {
          items: response.data.protocols,
          total: response.data.total_count,
        }
      }
    }
  }
  catch (e) {
    message.error((e as Error).message)
  }

  return null
}

async function handlePageChange(page: number) {
  pagination.page = page
  await handleFetchContextList({
    currentPage: page,
    currentPageSize: pagination.pageSize,
  })
}

async function handleFetchContextList(payload: {
  currentPage: number
  currentPageSize: number
}) {
  if (!selectedPath.value)
    return

  startLoading()

  try {
    const { currentPage, currentPageSize } = payload
    const result = await fetchContextData(selectedPath.value, currentPage, currentPageSize)

    if (result) {
      contextData.value = result.items
      pagination.itemCount = result.total
    }
  }
  catch (error) {
    message.error(`Failed to fetch data: ${(error as Error).message}`)
    contextData.value = []
    pagination.itemCount = 0
  }
  finally {
    endLoading()
  }
}

const handleRecordSearch = useDebounceFn(async () => {
  if (props.type !== "record" || !selectedPath.value) {
    return
  }

  pagination.page = 1
  await handleFetchContextList({
    currentPage: 1,
    currentPageSize: pagination.pageSize,
  })
}, 300)

const selectedOptions = computed(() => {
  if (!selectedPath.value)
    return []

  const path = selectedPath.value.split("_")
  const list: CascaderOption[] = []

  // Find matching options for each level
  let currentOptions: CascaderOption[] | undefined = options.value

  path.forEach((value, idx, ary) => {
    const option = currentOptions?.find(
      opt => String(opt.value) === ary.slice(0, idx + 1).join("_"),
    )
    if (option?.uid) {
      list.push(option)
      currentOptions = option?.children
    }
  })

  return list
})

function handleRemoveItem(id: string) {
  const targetId = String(id)
  checkedRowKeys.value = checkedRowKeys.value.filter(key => String(key) !== targetId)
  selectedItemsMap.value.delete(targetId)
}

// Update the columns definition to use h() rendering
const columns = computed((): DataTableColumns<ProtocolModels.RecordInfo & { id: string } | ProtocolModels.ProjectProtocolInfo | ProtocolDocument> => {
  if (props.source === "editor" && props.type === "document") {
    return [
      { type: "selection", multiple: true, disabled: row => props.readonlyList.includes(String(row.id)) },
      { title: "Name", key: "name" },
      {
        title: "Size",
        key: "size",
        render: row => h(NText, null, { default: () => `${Math.round(("size" in row ? row.size : 0) / 1024)} KB` }),
      },
      {
        title: "Status",
        key: "status",
        render: (row) => {
          if ("status" in row) {
            return h(NTag, {
              size: "small",
              type: row.status === "uploaded" ? "success" : row.status === "error" ? "error" : "default",
            }, { default: () => row.status })
          }
          return null
        },
      },
      {
        title: "Date",
        key: "createdAt",
        render: (row) => {
          if ("createdAt" in row) {
            return h(NText, null, { default: () => formatDate(row.createdAt, "date-time") })
          }
          return h(NText, null, { default: () => "" })
        },
      },
    ]
  }
  else if (props.type === "record") {
    return [
      {
        type: "selection",
        multiple: true,
        disabled: row => props.readonlyList.includes(String(row.id)),
      },
      { title: "Number", key: "number", width: 100, render: (row) => {
        const { metadata } = row as ProtocolModels.RecordInfo
        return h("span", null, { default: () => metadata?.record_num || 0 })
      } },
      {
        title: "ID",
        key: "id",
        width: "50%",
        render: (row) => {
          const { airalogy_record_id } = row as ProtocolModels.RecordInfo & { id: string }

          // return h(NTag, { size: "small", type: "default", style: { whiteSpace: "pre-wrap", lineHeight: "1.5", height: "fit-content" } }, { default: () => `${AIRALOGY_ID_PREFIX}record.${id}.v.${version}` })
          return h(CopyToClip, { text: airalogy_record_id, showSuccess: true, contentClass: "whitespace-pre", buttonProps: { text: false, quaternary: true } })
        },
      },
      {
        title: "Time",
        key: "time",
        render: (row) => {
          const { metadata } = row as ProtocolModels.RecordInfo
          return h(NText, null, { default: () => formatDate(metadata.record_current_version_submission_time, "date-time") })
        },
      },
      {
        title: "Action",
        key: "actions",
        render: row =>
          h(
            NButton,
            {
              type: "primary",
              size: "small",
              onClick: () => {
                const [labUid, projectUid, protocolUid] = selectedOptions.value.map(
                  it => it.uid as string,
                )

                openNewTab({
                  name: "protocol-record-report",
                  params: {
                    labUid,
                    projectUid,
                    protocolUid,
                    protocolVersion: (row as ProtocolModels.RecordInfo).metadata?.protocol_version,
                    recordId: String(row.id),
                    recordVersion: String((row as ProtocolModels.RecordInfo).record_version),
                  },
                })
              },
            },
            { default: () => "View Report" },
          ),
      },
    ]
  }
  else if (props.type === "protocol") {
    return [
      { type: "selection", multiple: true, disabled: row => props.readonlyList.includes(String(row.id)) },
      { title: "Name", key: "name" },
      {
        title: "Action",
        key: "actions",
        render: row =>
          h(
            NButton,
            {
              type: "primary",
              size: "small",
              onClick: () => {
                const [labUid, projectUid, protocolUid] = selectedOptions.value.map(
                  it => it.uid as string,
                )

                openNewTab({
                  name: "protocol-detail",
                  params: { labUid, projectUid, protocolUid },
                })
              },
            },
            { default: () => "View Protocol" },
          ),
      },
    ]
  }

  return []
})

function handleCancel() {
  emit("update:show", false)
}

async function handleConfirm() {
  await nextTick()
  if (props.source === "editor" && props.type === "document") {
    // For documents from editor, we don't need path parts
    const contextItems = contextData.value
      .filter(item => checkedRowKeys.value.find(id => String(item.id) === String(id)))

    const target = contextItems.map(item => ({
      ...transformItem(item),
    }))

    emit("confirm", target as any)
  }
  else {
    const target: Chat.ChatContext[] = checkedRowKeys.value.map(id => selectedItemsMap.value.get(id)).filter((it): it is Chat.ChatContext => Boolean(it))

    emit("confirm", target)
  }

  emit("update:selected", checkedRowKeys.value)
  emit("update:show", false)
}

const modelValue = computed({
  get: () => props.show,
  set: value => emit("update:show", value),
})

function renderCascaderLabel(option: CascaderOption) {
  const { label, uid, count } = option
  const countText = count ? `${count} ${props.type === "record" ? "record" : "protocol"}` : ""
  return (
    <div class="flex items-center gap-2">
      <NEllipsis class="whitespace-normal break-all">
        {label}
      </NEllipsis>
      {uid && (
        <NTag size="small" type="info" class="whitespace-nowrap">
          {uid}
        </NTag>
      )}
      {countText && (
        <span class="text-sm color-text-secondary">
          {`(${countText}${Number(count) > 1 ? "s" : ""})`}
        </span>
      )}
    </div>
  )
}

// Helper functions for UI text
const modalTitle = computed(() => {
  if (props.source === "editor" && props.type === "document") {
    return "Select Documents"
  }
  return props.type === "record" ? "Select Protocol Records" : "Select Protocol"
})

const formItemLabel = computed(() => {
  return props.type === "record" ? "Target Protocol" : "Target Project"
})

const endFormItemLabel = computed(() => {
  return props.type === "record" ? "Target Records" : "Target Protocols"
})

const selectedItemTypeLabel = computed(() => {
  if (props.source === "editor" && props.type === "document") {
    return "Documents"
  }
  return props.type === "record" ? "Records" : "Protocols"
})

watch(selectedPath, async (path, prev) => {
  // For editor documents, we don't need a path
  if (props.source === "editor" && props.type === "document") {
    // For editor documents, directly use the store data
    contextData.value = protocolDocumentsStore.documents
    pagination.itemCount = protocolDocumentsStore.documents.length
    return
  }

  // For protocol sources, we need a path
  if (!path) {
    return
  }

  if (path !== prev) {
    pagination.page = 1
  }

  const targetPage = path === prev ? pagination.page : 1
  const result = await fetchContextData(path, targetPage, pagination.pageSize)
  if (result) {
    contextData.value = result.items
    pagination.itemCount = result.total
  }
}, { immediate: true })

watch(recordSearchQuery, () => {
  if (props.type !== "record") {
    return
  }

  void handleRecordSearch()
})
</script>

<style scoped lang="sass">
.n-space
  width: 100%

:deep(.n-form-item-feedback-wrapper)
  position: absolute
</style>
