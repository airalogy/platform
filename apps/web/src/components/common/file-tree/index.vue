<template>
  <n-scrollbar class="relative" :dir="dir">
    <n-tree
      block-line expand-on-click
      :data="sortedTreeData"
      :render-suffix="renderSuffix"
      :render-prefix="renderPrefix"
      :render-label="renderLabel"
      :selected-keys="selectedKeys"
      :checked-keys="checkedKeys"
      :expanded-keys="expandedKeys"
      :node-props="nodeProps"
      v-bind="treeProps"
      @update:selected-keys="handleSelect"
      @update:expanded-keys="handleExpand"
      @update:checked-keys="handleCheck"
    />
    <n-dropdown
      v-if="enableContextMenu"
      trigger="manual" placement="bottom-start" :show="showDropdown" :options="options" :x="xRef"
      :y="yRef" @select="handleDropdownSelect" @clickoutside="handleClickoutside"
    />
  </n-scrollbar>
</template>

<script setup lang="ts">
import type { TreeProps as NTreeProps, TreeOption } from "naive-ui"
import type { TreeRenderProps } from "naive-ui/es/tree/src/interface"
import type { Component } from "vue"
import { getFileSpecificIcon } from "@airalogy/shared/utils"
import FolderOpenIcon from "~icons/ion/folder-open-outline"
import FolderIcon from "~icons/ion/folder-outline"
import EditIcon from "~icons/tabler/edit"
import TrashIcon from "~icons/tabler/trash"
import { NIcon } from "naive-ui"
import TreeActions, { type Action as ActionItem } from "./Actions.vue"
import FileTreeItem from "./FileTreeItem.vue"

const props = withDefaults(defineProps<TreeProps>(), {
  indicator: true,
  dir: "ltr",
  elements: () => [] as TreeViewElement[],
  defaultExpandAll: false,
  enableContextMenu: true,
  size: "medium",
  showActions: true,
})

const emit = defineEmits<{
  (e: "select", item: TreeViewElement): void
  (e: "update:item", id: string, updatedProperties: UpdatedProperties): void
  (e: "contextMenuSelect", key: string, item: TreeViewElement): void
  (e: "update:selectedKeys", keys: string[]): void
  (e: "update:expandedKeys", keys: string[]): void
}>()

export interface TreeViewElement {
  id: string
  filename: string
  kind: "directory" | "file"
  children?: TreeViewElement[]
  status?: "init" | "modified" | "uploaded" | "error" | "pending" | "success"
  isEditable?: boolean
  isSelectable?: boolean
  path?: string
  value?: string
  icon?: Component
}

export interface TreeAction {
  icon: any
  onClick: (item: TreeViewElement, e: MouseEvent) => void
  condition?: (item: TreeViewElement) => boolean
}

export interface TreeProps {
  elements: TreeViewElement[]
  indicator?: boolean
  dir?: "ltr" | "rtl"
  defaultExpandAll?: boolean
  enableContextMenu?: boolean
  size?: "small" | "medium" | "large"
  treeProps?: NTreeProps
  showActions?: boolean
  customActions?: (item: TreeViewElement) => ActionItem[] | null
  selectedKeys?: string[]
  checkedKeys?: string[]
  expandedKeys?: string[]
}

export interface UpdatedProperties {
  filename?: string
  path?: string
  status?: string
  isEditable?: boolean
  isSelectable?: boolean
}

const selectedKeys = useVModel (props, "selectedKeys", emit)
const expandedKeys = useVModel(props, "expandedKeys", emit)
const checkedKeys = useVModel(props, "checkedKeys", emit)
const xRef = ref(0)
const yRef = ref(0)
const showDropdown = ref(false)
const defaultOptions = [{
  key: "rename",
  label: "Rename",
}, {
  key: "delete",
  label: "Delete",
}]

const options = ref<TreeOption[]>(defaultOptions)

function nodeProps(node: {
  option: TreeOption
}) {
  return {
    onContextmenu(e: MouseEvent): void {
      if (!props.enableContextMenu)
        return

      options.value = defaultOptions
      showDropdown.value = true
      xRef.value = e.clientX
      yRef.value = e.clientY
      e.preventDefault()
    },
    class: "group",
    onClick: (e: MouseEvent) => handleClickItem(e, node),
  }
}

function handleClickoutside() {
  showDropdown.value = false
}

function handleDropdownSelect(key: string) {
  const selectedItem = options.value.find(option => option.key === key)
  if (selectedItem && selectedKeys.value && selectedKeys.value.length > 0) {
    const item = findItemById(props.elements, selectedKeys.value[0])
    if (item) {
      emit("contextMenuSelect", key as string, item)
    }
  }
  showDropdown.value = false
}

function findItemById(items: TreeViewElement[], id: string): TreeViewElement | null {
  for (const item of items) {
    if (item.id === id) {
      return item
    }
    if (item.children) {
      const found = findItemById(item.children, id)
      if (found) {
        return found
      }
    }
  }
  return null
}

function sortItems(elements: TreeViewElement[]): TreeViewElement[] {
  const tempItems: TreeViewElement[] = []

  elements.forEach((item) => {
    const { children, ...rest } = item
    if (children) {
      ;(rest as any).children = sortItems(children)
    }

    tempItems.push(rest)
  })

  return tempItems.sort((a, b) => {
    if (a.kind === "directory" && b.kind === "file")
      return -1
    if (a.kind === "file" && b.kind === "directory")
      return 1
    return a.filename.localeCompare(b.filename)
  })
}

const sortedTreeData = computed(() => {
  if (!props.elements) {
    return []
  }

  return transformToTreeOptions(sortItems(props.elements))
})

function transformToTreeOptions(elements: TreeViewElement[]): TreeOption[] {
  return elements.map(item => ({
    key: item.id,
    item,
    label: item.filename,
    children: item.children ? transformToTreeOptions(item.children) : undefined,
    isLeaf: item.kind === "file",
    prefix: () => item.kind === "directory"
      ? h(expandedKeys.value && expandedKeys.value.includes(item.id) ? FolderOpenIcon : FolderIcon)
      : null,
    disabled: !item.isSelectable,
  }))
}

function renderSuffix(node: TreeRenderProps) {
  const { showActions, customActions } = props
  const { item } = (node.option || {}) as { item?: TreeViewElement }
  if (!item || !showActions) {
    return null
  }

  // Don't show actions for pending items
  if (item.status === "pending") {
    return null
  }

  // Define default actions
  const defaultActions: ActionItem[] = showActions
    ? [
        {
          id: "edit",
          icon: EditIcon,
          handler: (item) => {
            emit("update:item", item.id, { status: "pending" })
          },
        },
        {
          id: "delete",
          icon: TrashIcon,
          handler: (item) => {
            emit("contextMenuSelect", "delete", item)
          },
          confirmMessage: item => `Are you sure you want to delete "${item.filename}"?`,
        },
      ]
    : []

  // Combine with custom actions if provided
  const allActions = customActions
    ? customActions(item) || defaultActions
    : defaultActions

  return h(TreeActions, {
    item,
    actions: allActions,
    onAction: (actionId: string, actionItem: TreeViewElement) => {
      if (actionId === "delete") {
        emit("contextMenuSelect", "delete", actionItem)
      }
    },
  })
}

function renderPrefix(node: TreeRenderProps) {
  const { item } = (node.option || {}) as { item?: TreeViewElement }
  if (!item) {
    return null
  }

  const { kind, id, icon } = item
  if (icon) {
    return h(NIcon, {
      component: icon,
    })
  }

  if (kind === "file") {
    return h(NIcon, {
      component: getFileSpecificIcon(item.filename),
    })
  }

  const isExpanded = expandedKeys.value && expandedKeys.value.includes(id)
  return h(NIcon, {
    component: kind === "directory" ? (isExpanded ? FolderOpenIcon : FolderIcon) : undefined,
  })
}

function renderLabel(node: TreeRenderProps) {
  const { item } = (node.option || {}) as { item?: TreeViewElement }
  if (!item) {
    return null
  }

  const { filename, kind, status, path, id } = item

  return h(FileTreeItem, {
    filename,
    kind,
    "status": status || "success",
    path,
    "size": props.size,
    id,
    "onUpdate:properties": (updatedProperties: UpdatedProperties) => handleUpdateProperties(id, updatedProperties),
  })
}

async function handleUpdateProperties(itemId: string, updatedProperties: UpdatedProperties) {
  emit("update:item", itemId, updatedProperties)
}

async function handleClickItem(e: MouseEvent, node: { option: TreeOption }) {
  e.preventDefault()

  const { item } = node.option as { item: TreeViewElement }
  if (!item) {
    return
  }

  const { id, kind, status } = item
  if (status === "pending" || kind === "directory") {
    return
  }

  emit("select", item)
}

function handleSelect(keys: string[]) {
  selectedKeys.value = keys
  if (keys.length > 0) {
    const item = findItemById(props.elements, keys[0])
    if (item) {
      emit("select", item)
    }
  }
}

function handleExpand(keys: string[]) {
  expandedKeys.value = keys
}

function handleCheck(keys: string[]) {
  checkedKeys.value = keys
}

// Initialize expanded keys for all directories if defaultExpandAll is true
onMounted(() => {
  if (props.defaultExpandAll) {
    const allDirectoryIds = getAllDirectoryIds(props.elements)
    expandedKeys.value = allDirectoryIds
  }
})

function getAllDirectoryIds(elements: TreeViewElement[]): string[] {
  const ids: string[] = []

  for (const item of elements) {
    if (item.kind === "directory") {
      ids.push(item.id)
      if (item.children) {
        ids.push(...getAllDirectoryIds(item.children))
      }
    }
  }

  return ids
}

// Expose expanded keys and related methods
defineExpose({
  selectedKeys,
  expandedKeys,
  expandNode: (nodeId: string) => {
    if (!expandedKeys.value || !expandedKeys.value.includes(nodeId)) {
      expandedKeys.value?.push(nodeId)
    }
  },
  selectNode: (nodeId: string) => {
    selectedKeys.value = [nodeId]
    const item = findItemById(props.elements, nodeId)
    if (item) {
      emit("select", item)
    }
  },
})
</script>

<style lang="sass" scoped></style>
