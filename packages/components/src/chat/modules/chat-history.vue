<template>
  <define-action-button v-slot="{ content: tooltip, icon, size = 16, onClick, disabled, $slots, onConfirm }">
    <n-popconfirm v-if="onConfirm" @positive-click="onConfirm" @click.stop>
      <template #trigger>
        <div class="h-fit w-fit" @click.stop>
          <tooltip-button
            :button-props="{ size: 'tiny', quaternary: true, disabled }"
            :tooltip="tooltip"
            :icon="icon"
            :icon-props="{ size }"
            @click="onClick"
          />
        </div>
      </template>
      <component :is="$slots.default" />
    </n-popconfirm>
    <tooltip-button
      v-else
      :button-props="{ size: 'tiny', quaternary: true, disabled }"
      :tooltip="tooltip"
      :icon="icon"
      :icon-props="{ size }"
      @click="onClick"
    />
  </define-action-button>

  <n-popover
    trigger="click"
    placement="bottom-end"
    :show-arrow="false"
    :theme-overrides="{ padding: '8px' }"
    :show="isVisible"
    @update:show="handleUpdateShow"
  >
    <template #trigger>
      <n-button quaternary :type="isConfirmDialog ? 'primary' : 'default'">
        <template #icon>
          <n-icon size="24">
            <icon-ion-time-outline />
          </n-icon>
        </template>
      </n-button>
    </template>

    <n-tabs
      v-model:value="activeSource"
      size="small"
      type="card"
      animated
      :theme-overrides="{ tabGapSmallCard: '6px' }"
      pane-wrapper-class="!max-h-50vh !overflow-y-auto w-80"
    >
      <template #suffix>
        <n-popconfirm @positive-click="handleClearHistory">
          <template #trigger>
            <div>
              <tooltip-button
                :button-props="{ size: 'small', quaternary: true }"
                tooltip="Clear all chat history"
              >
                <template #icon>
                  <n-icon :size="16">
                    <icon-ion-trash-outline />
                  </n-icon>
                </template>
              </tooltip-button>
            </div>
          </template>
          Are you sure you want to clear all chat history?
        </n-popconfirm>
      </template>
      <n-tab-pane
        v-for="(_, sourceType) in allHistoryRecord"
        :key="sourceType"
        :name="sourceType"
        :tab="sourceType.charAt(0).toUpperCase() + sourceType.slice(1)"
      >
        <n-tree
          v-if="Array.isArray(sortedHistory) && sortedHistory.length > 0 "
          :ref="handleTreeRef"
          block-line
          expand-on-click
          :node-props="nodeProps"
          :data="treeData"
          :selected-keys="selectedKeys"
          :render-label="renderTreeLabel"
          :render-suffix="renderTreeSuffix"
          @update:selected-keys="handleSelectedKeysUpdate"
        />
        <div v-else class="p-4 text-center text-neutral-500">
          No chat history
        </div>
      </n-tab-pane>
      <n-tab-pane
        v-if="!allHistoryRecord[source]"
        :key="source"
        :name="source"
        :tab="source?.charAt(0).toUpperCase() + source?.slice(1)"
      >
        <div class="p-4 text-center text-neutral-500">
          No chat history
        </div>
      </n-tab-pane>
    </n-tabs>
  </n-popover>
</template>

<script setup lang="ts">
import type { TreeInst, TreeOption } from "naive-ui"
import type { TreeRenderProps } from "naive-ui/es/tree/src/interface"
import { TooltipButton } from "@airalogy/components"
import { useChatStore } from "@airalogy/components/chat/store"
import { useBoolean, useClosableMessage } from "@airalogy/composables"
import { createReusableTemplate } from "@vueuse/core"
// import DownloadIcon from "~icons/ion/download-outline"
import EditIcon from "~icons/ion/pencil-outline"
import DeleteIcon from "~icons/ion/trash-outline"
import { NEllipsis, NInput, NTabPane, NTabs, NTree } from "naive-ui"
import { computed, h, nextTick, onUpdated, ref, watch } from "vue"
import { useChatInfoStore } from "../composables/useChatInfoStore"

// Define template types
interface ActionButtonProps {
  content: string
  icon: Component
  size?: number
  disabled?: boolean
  onConfirm?: () => void
  onClick?: (e: Event) => void
}

const [DefineActionButton, ReuseActionButton] = createReusableTemplate<ActionButtonProps>()

const { loadChat, deleteHistory, editHistory, exportHistory, source, allHistoryRecord, clearHistory } = useChatInfoStore()!

const chatStore = useChatStore()

const { bool: isVisible, toggle: toggleVisible, setFalse: hideVisible } = useBoolean(false)
const { bool: isConfirmDialog, setTrue: startConfirm, setFalse: endConfirm } = useBoolean(false)
const { bool: isLoading, setTrue: startLoading, setFalse: endLoading } = useBoolean(false)

const activeSource = ref<Chat.ChatSource>(source.value || "global")
const selectedKeys = ref<[string]>([String(chatStore.state.active || "_empty_")])

const sortedHistory = computed(() => {
  const targetSource = allHistoryRecord.value[activeSource.value]

  if (!targetSource?.length)
    return []

  return [...targetSource].sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime())
})

const treeData = computed<TreeOption[]>(() => {
  if (!sortedHistory.value?.length)
    return []

  return sortedHistory.value.map(item => ({
    key: item.uuid,
    label: item.title,
    uuid: item.uuid,
    time: item.time,
    isLeaf: true,
  }))
})

const editingId = ref<string | null>(null)
const editingTitle = ref("")
const inputRef = ref<InstanceType<typeof NInput> | null>(null)
const message = useClosableMessage()

const treeRef = ref<Record<string, TreeInst>>({})

function handleTreeRef(inst: any) {
  treeRef.value[activeSource.value] = inst
}

function nodeProps() {
  return {
    class: "group/history",
  }
}

function handleLoad(item: Chat.ChatHistory) {
  loadChat(item)
  isVisible.value = false
}

async function handleDownload(uuid: string) {
  try {
    startLoading()
    await exportHistory(uuid)
  }
  finally {
    endLoading()
  }
}

async function handleDelete(uuid: string) {
  startConfirm()
  deleteHistory(uuid, "popconfirm")
  endConfirm()
}

function handleStartEdit(item: Chat.ChatHistory) {
  editingId.value = item.uuid
  editingTitle.value = item.title
  nextTick(() => {
    inputRef.value?.focus()
  })
}

async function handleSaveTitle(uuid: string) {
  const title = editingTitle.value.trim()
  if (title) {
    try {
      startLoading()
      await editHistory(uuid, title)
      message.success(`Chat title updated to ${title}`)
    }
    finally {
      endLoading()
      editingId.value = null
      editingTitle.value = ""
    }
  }
}

function handleUpdateShow(show: boolean) {
  if (isConfirmDialog.value)
    return

  if (!show) {
    editingId.value = null
    editingTitle.value = ""
  }

  if (show) {
    toggleVisible()
  }
  else {
    hideVisible()
  }
}

function handleSelectedKeysUpdate(keys: string[]) {
  // Only select keys that correspond to leaf nodes (actual chat items)
  const leafKeys = keys.filter((key) => {
    const node = findNodeByKey(treeData.value, key)
    return node?.isLeaf
  })

  if (leafKeys.length > 0) {
    const selectedNode = findNodeByKey(treeData.value, leafKeys[0])
    if (selectedNode?.uuid) {
      const item = sortedHistory.value.find(h => h.uuid === selectedNode.uuid)
      if (item) {
        selectedKeys.value = [item.uuid]
        handleLoad(item)
      }
    }
  }
  else {
    selectedKeys.value = [String(chatStore.state.active || "_empty_")]
  }
}

function findNodeByKey(nodes: TreeOption[], key: string): TreeOption | null {
  for (const node of nodes) {
    if (node.key === key)
      return node
    if (node.children) {
      const found = findNodeByKey(node.children as TreeOption[], key)
      if (found)
        return found
    }
  }
  return null
}

// Add a watcher to keep selectedKeys in sync with active chat
watch(
  () => chatStore.state.active,
  (newActive) => {
    selectedKeys.value = [String(newActive || "_empty_")]
  },
)

function renderTreeLabel(node: TreeRenderProps) {
  const { label, isLeaf, uuid } = node.option
  if (!isLeaf) {
    return label
  }

  const item = sortedHistory.value.find(h => h.uuid === uuid)
  if (!item)
    return label

  if (editingId.value === item.uuid) {
    return h(NInput, {
      ref: inputRef,
      value: editingTitle.value,
      size: "tiny",
      autofocus: true,
      themeOverrides: { borderRadius: "4px", paddingTiny: "0 4px" },
      onUpdateValue: (v: string) => editingTitle.value = v,
      onKeydown: (e: KeyboardEvent) => {
        if (e.key === "Enter")
          handleSaveTitle(item.uuid)
      },
      onBlur: () => handleSaveTitle(item.uuid),
      onClick: (e: Event) => e.stopPropagation(),
    })
  }

  // return h("div", {
  //   class: "flex items-center w-full py-1 group",
  //   style: {
  //     minHeight: "32px",
  //   },
  // }, [
  //   h("span", {
  //     class: [
  //       "flex-1 truncate text-sm",
  //       item.uuid === chatStore.state.active
  //         ? "text-primary-500 font-medium"
  //         : "text-neutral-700 dark:text-neutral-300",
  //     ],
  //   }, item.title),
  // ])
  return h(NEllipsis, {
    class: "w-full",
  }, {
    default: () => item.title,
  })
}

function renderTreeSuffix(node: TreeRenderProps) {
  const { isLeaf, uuid } = node.option
  if (!isLeaf)
    return null

  const item = sortedHistory.value.find(h => h.uuid === uuid)
  if (!item || editingId.value === item.uuid)
    return null

  return h("div", {
    class: [
      "items-center gap-1 transition-opacity duration-200",
      "hidden opacity-0 group-hover/history:opacity-100 group-hover/history:flex",
    ],
  }, [
    h(ReuseActionButton, {
      content: "Edit Title",
      icon: EditIcon,
      disabled: isLoading.value,
      onClick: (e: Event) => {
        e.stopPropagation()
        e.preventDefault()
        handleStartEdit(item)
      },
    }),
    // h(ReuseActionButton, {
    //   content: "Download",
    //   icon: DownloadIcon,
    //   disabled: isLoading.value,
    //   onClick: (e: Event) => {
    //     e.stopPropagation()
    //     e.preventDefault()
    //     handleDownload(item.uuid)
    //   },
    // }),
    h(ReuseActionButton, {
      content: "Delete",
      icon: DeleteIcon,
      disabled: isLoading.value,
      onConfirm: () => {
        handleDelete(item.uuid)
      },
    }, {
      default: () => "Delete this chat?",
    }),
  ])
}

watch(
  () => allHistoryRecord.value,
  (val) => {
    if (!val[activeSource.value]?.length) {
      const firstSourceWithHistory = Object.entries(val).find(
        ([_, histories]) => histories.length > 0,
      )?.[0] as Chat.ChatSource | undefined

      if (firstSourceWithHistory)
        activeSource.value = firstSourceWithHistory
    }
  },
  { deep: true },
)

function handleClearHistory() {
  clearHistory()
}

onUpdated(async () => {
  const { active } = chatStore.state
  const targetTree = treeRef.value[activeSource.value]
  if (active && targetTree) {
    targetTree.scrollTo({ key: active })
  }
})
</script>

<style lang="sass" scoped>
.n-input
  min-width: 100px

:deep(.n-tree-node-switcher--hide)
  display: none

:deep(.n-tree-node-content__prefix)
  width: fit-content

:deep(.n-tree-node-indent)
  display: none!important

:deep(.n-tree-node-content__text)
  overflow: hidden

:deep(:not(.n-tree-node-switcher--hide ~ .n-tree-node-content) > .n-tree-node-content__prefix)
  display: none
</style>
