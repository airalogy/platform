<template>
  <div class="size-full">
    <n-scrollbar class="relative h-full" :dir="dir">
      <n-tree
        block-line expand-on-click
        :data="sortedTreeData"
        :render-suffix="renderSuffix"
        :render-prefix="renderPrefix"
        :render-label="renderLabel"
        :selected-keys="selectedKeys"
        :expanded-keys="expandedKeys"
        :node-props="nodeProps"
        @update:selected-keys="handleSelect"
        @update:expanded-keys="handleExpand"
      />
      <n-dropdown
        trigger="manual" placement="bottom-start" :show="showDropdown" :options="(options as any)" :x="xRef"
        :y="yRef" @select="handleSelect" @clickoutside="handleClickoutside"
      />
    </n-scrollbar>
  </div>
</template>

<script setup lang="ts">
import type * as Monaco from "monaco-editor"
import type { TreeOption } from "naive-ui"
import type { TreeRenderProps } from "naive-ui/es/tree/src/interface"
import type { ShallowRef } from "vue"
import type { DirectoryInterface } from "../../types"
import type { TreeProps, TreeViewElement } from "./types"
import { isDirectory, isFile, openEditor } from "@airalogy/components/monaco-editor/utils"
import { getFileSpecificIcon, shouldPreviewFile } from "@airalogy/shared/utils"
import FolderOpenIcon from "~icons/ion/folder-open-outline"
import FolderIcon from "~icons/ion/folder-outline"
import { NIcon, NScrollbar, NTree } from "naive-ui"
import { storeToRefs } from "pinia"
import { useActiveEditorStore, useEditorStore, useModelsStore, useSplitStore } from "../../store/editorStore"
import { useFilePreviewStore } from "../../store/filePreviewStore"

import { isPending, useUploadFileDataStore } from "../../store/uploadFileDataStore"
import Actions from "./components/Actions.vue"
import FileTreeItem from "./components/FileTreeItem.vue"

const props = withDefaults(defineProps<TreeProps>(), {
  indicator: true,
  dir: "ltr",
  elements: () => [] as TreeViewElement[],
})

const monaco = injectLocal<ShallowRef<typeof Monaco | null>>("monaco", shallowRef(null))

const selectedKeys = ref<string[]>([])
const expandedKeys = ref<string[]>([])
const xRef = ref(0)
const yRef = ref(0)
const showDropdown = ref(false)
const defaultOptions = [{
  key: "copy",
  label: "Copy",
  children: [],
}, {
  key: "paste",
  label: "Paste",
  children: [],
}, {
  key: "rename",
  label: "Rename",
  children: [],
}, {
  key: "delete",
  label: "Delete",
  children: [],
}]

const options = ref<TreeOption[]>([])
function nodeProps(node: {
  option: TreeOption
}) {
  return {
    onContextmenu(e: MouseEvent): void {
      options.value = [node.option]
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

// const context = useProvideTreeContext({
//   ...props,
//   openIcon: FolderOpenIcon,
//   closeIcon: FolderIcon,
// })

function sortItems(elements: TreeViewElement[]): TreeViewElement[] {
  const tempItems: TreeViewElement[] = []

  elements.forEach((item) => {
    if (isDirectory(item)) {
      tempItems.push({ ...item, children: item.children ? sortItems(item.children) : [] })
      return
    }

    tempItems.push(item)
  })

  return tempItems.sort((a, b) => {
    if (a.kind === "directory" && b.kind === "file")
      return -1
    if (a.kind === "file" && b.kind === "directory")
      return 1
    return a.name.localeCompare(b.name)
  })
}

const uploadFileStore = useUploadFileDataStore()
const { setSelected, getFileById } = uploadFileStore

const activeEditorStore = useActiveEditorStore()
const modelsStore = useModelsStore()
const splitStore = useSplitStore()
const editorStore = useEditorStore()
const filePreviewStore = useFilePreviewStore()

const { setModels, getModelInfo, setActiveModelInfo } = modelsStore
const { getEditorInfo } = editorStore
const { addSplit } = splitStore
const { setActiveEditor } = activeEditorStore
const { openFilePreview } = filePreviewStore

const { activeEditor, activeEditorId } = storeToRefs(activeEditorStore)
const { splitState } = storeToRefs(splitStore)
const { modelInfos } = storeToRefs(modelsStore)

const sortedTreeData = ref<TreeViewElement[]>([])

function getTreeData(elements: TreeViewElement[]) {
  if (!elements || !elements.length) {
    return []
  }

  return transformToTreeOptions(sortItems(elements))
}

function transformToTreeOptions(elements: TreeViewElement[]): TreeOption[] {
  return elements.map(item => ({
    key: item.id,
    item,
    label: item.name,
    children: isDirectory(item) && item.children ? getTreeData(item.children) : undefined,
    isLeaf: item.kind === "file",
    prefix: () => item.kind === "directory"
      ? h(expandedKeys.value.includes(item.id) ? FolderOpenIcon : FolderIcon)
      : null,
    // disabled: !item.isSelectable,
    disabled: false,
  }))
}

function renderSuffix(node: TreeRenderProps) {
  const { item } = (node.option || {}) as { item?: TreeViewElement }
  if (!item) {
    return null
  }
  const { status, isEditable } = item

  if (status === "pending" || status === "error" || !isEditable) {
    return null
  }

  const modelInfo = getModelInfo(item.id, "normal")
  if (modelInfo?.isDirty) {
    return [
      h("span", {
        class: "bg-[#666] block rounded-full w-1.5 h-1.5 mr-2 opacity-50 self-center",
      }, ""),
      h(Actions, { item, isDirty: true }),
    ]
  }
  else {
    return h(Actions, { item, isDirty: false })
  }
}

function renderPrefix(node: TreeRenderProps) {
  const { item } = (node.option || {}) as { item?: TreeViewElement }
  if (!item) {
    return null
  }

  const { name, id } = item
  if (isFile(item)) {
    return h(NIcon, {
      size: 14,
      component: getFileSpecificIcon(name),
    })
  }

  const isExpanded = expandedKeys.value.includes(id)
  return h(NIcon, {
    size: 14,
    component: isExpanded ? FolderOpenIcon : FolderIcon,
  })
}

function renderLabel(node: TreeRenderProps) {
  const { item } = (node.option || {}) as { item?: TreeViewElement }
  if (!item) {
    return null
  }

  const { name, kind, status, path, id } = item

  return h(FileTreeItem, {
    name,
    kind,
    "status": status || "init",
    path,
    id,
    "options": defaultOptions,
    "onUpdate:properties": (updatedProperties: Partial<DirectoryInterface>) => handleUpdateProperties(id, updatedProperties),
  })
}

async function handleUpdateProperties(modelId: string, updatedProperties: Partial<DirectoryInterface>) {
  if (!updatedProperties.name) {
    return
  }

  const model = getModelInfo(modelId)
  if (model) {
    model.name = updatedProperties.name
  }
}

async function handleClickItem(e: MouseEvent, node: { option: TreeOption }) {
  if (!monaco.value) {
    return
  }

  e.preventDefault()

  const { item } = node.option as { item: TreeViewElement }
  if (!item) {
    return
  }

  const { id, name, status } = item
  if (status === "pending" || !isFile(item)) {
    return
  }

  if (isPending(name)) {
    return
  }

  // Check if this file should be previewed instead of edited
  if (shouldPreviewFile(name)) {
    openFilePreview(item)
    return
  }

  await openEditor({
    activeEditor,
    activeEditorId,
    splitState,
    getEditorInfo,
    getModelInfo,
    setActiveModelInfo,
    setModels,
    setActiveEditor,
    addSplit,
    monaco: monaco.value,
    id,
    item,
  })
  // const willChangeEditorId = activeEditor.value ? activeEditorId.value : splitState.value.findIndex(Boolean)
  // const willChangeEditor = getEditor(willChangeEditorId)

  // const matchModel = getModelInfo(id)

  // if (matchModel && matchModel.model) {
  //   setActiveModelInfo(matchModel.id, matchModel, willChangeEditorId)
  //   setModels(
  //     {
  //       filename: matchModel.filename,
  //       value: "",
  //       language: getFileLanguage(matchModel.filename),
  //       id,
  //     },
  //     matchModel.model,
  //     willChangeEditorId,
  //   )
  //   if (willChangeEditor && !Array.isArray(willChangeEditor)) {
  //     willChangeEditor.setModel(matchModel.model)
  //   }
  // }
  // else if (willChangeEditor) {
  //   const monaco = getMonaco(willChangeEditorId)
  //   if (monaco) {
  //     addNewModel(
  //       { ...item, language: getFileLanguage(item.filename), value: item.value || "" },
  //       monaco,
  //       willChangeEditor as editor.IStandaloneCodeEditor,
  //       setModels,
  //       setActiveModelInfo,
  //       willChangeEditorId,
  //     )
  //   }
  //   else {
  //     console.log("no monaco")
  //   }
  // }
  // else {
  //   addSplit()

  //   const unwatch = watch(() => editors.value[0], (newEditor) => {
  //     if (newEditor) {
  //       const editor = toRaw(newEditor) as editor.IStandaloneCodeEditor
  //       unwatch() // Stop watching once we get the editor
  //       setActiveEditor(editor, 0)
  //       const monaco = getMonaco(0)
  //       if (monaco) {
  //         addNewModel(
  //           { ...item, language: getFileLanguage(item.filename), value: item.value || "" },
  //           monaco,
  //           editor,
  //           setModels,
  //           setActiveModelInfo,
  //           0,
  //         )
  //       }
  //       else {
  //         console.log("no monaco")
  //       }
  //     }
  //   }, { immediate: true })
  // }
}

function handleSelect(keys: string[]) {
  selectedKeys.value = keys
  if (keys.length > 0) {
    setSelected(keys[0])
  }
}

function handleExpand(keys: string[]) {
  expandedKeys.value = keys
}

// Make setSelected available to child components
// context.selectItem = (id: string) => {
//   context.selectedId.value = id
//   uploadFileStore.setSelected(id)
// }
watch(modelInfos, (newModels) => {
  if (!newModels || newModels.length === 0) {
    selectedKeys.value = []
  }
})

watch(() => props.elements, (val) => {
  if (!val || val.length === 0) {
    expandedKeys.value = []
    return
  }

  // expandedKeys.value = expandedKeys.value.filter(id => val.some(it => it.id === id))
  sortedTreeData.value = getTreeData(val)
}, { immediate: true, deep: true })

// Expose expanded keys and related methods
defineExpose({
  expandedKeys,
  expandNode: (nodeId: string) => {
    if (!expandedKeys.value.includes(nodeId)) {
      expandedKeys.value.push(nodeId)
    }
  },
})
</script>

<style lang="sass" scoped>
:deep(.n-tree-node-wrapper)
  @apply px-px text-[12px] font-[300]

:deep(.n-tree-node-switcher)
  width: 12px!important
</style>
