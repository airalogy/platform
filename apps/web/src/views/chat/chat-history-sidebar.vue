<template>
  <div class="chat-history-sidebar h-full flex flex-col">
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

    <!-- Title Area -->
    <div class="flex items-center justify-between border-b border-gray-100 p-4">
      <h3 class="whitespace-nowrap text-gray-700 font-medium">
        {{ $t("chat.history") }}
      </h3>
    </div>

    <!-- Source Type Tabs -->
    <div v-if="Object.keys(allHistoryRecord).length > 1" class="px-2 py-2">
      <n-tabs
        v-model:value="activeSource"
        size="small"
        type="line"
        :theme-overrides="{ tabGapSmallLine: '8px' }"
      >
        <n-tab-pane
          v-for="(_, sourceType) in allHistoryRecord"
          :key="sourceType"
          :name="sourceType"
          :tab="sourceType.charAt(0).toUpperCase() + sourceType.slice(1)"
        />
      </n-tabs>
    </div>

    <!-- Chat History Tree -->
    <div class="flex-1 overflow-hidden">
      <n-scrollbar class="h-full">
        <div class="px-2">
          <n-tree
            v-if="Array.isArray(sortedHistory) && sortedHistory.length > 0"
            :ref="handleTreeRef"
            v-model:expanded-keys="expandedKeys"
            block-line
            expand-on-click
            :node-props="nodeProps"
            :data="treeData"
            :selected-keys="selectedKeys"
            :render-switcher-icon="renderSwitcherIcon"
            :render-label="renderTreeLabel"
            :render-prefix="undefined"
            :render-suffix="renderTreeSuffix"
            @update:selected-keys="handleSelectedKeysUpdate"
          />
          <div v-else class="whitespace-nowrap p-4 text-center text-neutral-500">
            No chat history
          </div>
        </div>
      </n-scrollbar>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { TreeInst, TreeOption } from "naive-ui"
import type { TreeRenderProps } from "naive-ui/es/tree/src/interface"
import { TooltipButton } from "@airalogy/components"
import { useOrProvideChatInfoStore } from "@airalogy/components/chat/composables/useChatInfoStore"
import { useChatStore } from "@airalogy/components/chat/store"
import { useBoolean, useClosableMessage } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import { createReusableTemplate } from "@vueuse/core"
import ChevronRightIcon from "~icons/ion/chevron-forward-outline"
import EditIcon from "~icons/ion/pencil-outline"
import DeleteIcon from "~icons/ion/trash-outline"
import { NEllipsis, NIcon, NInput, NScrollbar, NTabPane, NTabs, NTree } from "naive-ui"
import { computed, h, nextTick, onUpdated, ref, watch } from "vue"

defineOptions({ name: "ChatHistorySidebar" })

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
const { loadChat, deleteHistory, editHistory, exportHistory, source, allHistoryRecord } = useOrProvideChatInfoStore({}, () => ({}))

const chatStore = useChatStore()
const { bool: isLoading, setTrue: startLoading, setFalse: endLoading } = useBoolean(false)

const activeSource = ref<Chat.ChatSource>(source.value || "global")
const expandedKeys = ref<string[]>([])
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
  deleteHistory(uuid, "popconfirm")
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
      message.success(`Chat title updated to: ${title}`)
    }
    finally {
      endLoading()
      editingId.value = null
      editingTitle.value = ""
    }
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
        // Find and expand parent node
        const parentNode = findParentNode(treeData.value, selectedNode.key as string)
        if (parentNode) {
          expandedKeys.value = Array.from(new Set([...expandedKeys.value, parentNode.key as string]))
        }
        // Load chat
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

function findParentNode(nodes: TreeOption[], key: string, parent: TreeOption | null = null): TreeOption | null {
  for (const node of nodes) {
    if (node.key === key)
      return parent
    if (node.children) {
      const found = findParentNode(node.children as TreeOption[], key, node)
      if (found)
        return found
    }
  }
  return null
}

// Add watcher to keep selectedKeys in sync with active chat
watch(
  () => chatStore.state.active,
  (newActive) => {
    selectedKeys.value = [String(newActive || "_empty_")]
  },
)

function renderSwitcherIcon() {
  return h(NIcon, {
    size: 16,
    component: ChevronRightIcon,
  })
}

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

onUpdated(async () => {
  const { active } = chatStore.state
  const targetTree = treeRef.value[activeSource.value]
  if (active && targetTree) {
    const parentNode = findParentNode(treeData.value, active)
    if (parentNode) {
      expandedKeys.value = Array.from(new Set([...expandedKeys.value, parentNode.key as string]))
      targetTree.scrollTo({ key: parentNode.key })
    }
    else {
      targetTree.scrollTo({ key: active })
    }
  }
})
</script>

<style lang="sass" scoped>
.chat-history-sidebar
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

.n-input
  min-width: 100px
</style>
