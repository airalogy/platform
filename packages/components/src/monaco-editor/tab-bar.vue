<template>
  <div class="editor__tab-bar">
    <n-scrollbar
      x-scrollable
      class="h-full max-w-[calc(100%-96px)] !overflow-visible"
      :theme-overrides="{
        color: '#00000022',
        colorHover: '#00000066',
      }"
      content-class="h-full overflow-hidden"
    >
      <div ref="tabBarRef" class="h-full w-fit flex items-center">
        <div
          v-for="modelInfo in mockModelInfosForSort"
          :key="modelInfo.id"
          :ref="el => setTabRef(modelInfo.id, el)"
          class="group editor__tab-bar-item"
          :class="[
            activeModel?.id === modelInfo.id
              ? 'bg-[#e5e7eb] !b-[#00000066]'
              : 'bg-transparent',
          ]"
          @click="handleTabClick(modelInfo)"
          @click.middle="handleCloseEditor(modelInfo)"
          @contextmenu="e => handleContextMenu(modelInfo.id, e)"
        >
          <n-icon
            :component="getFileSpecificIcon(modelInfo.name)"
            class="text-black"
          />
          <n-ellipsis
            :class="[
              activeModel?.id === modelInfo.id
                ? 'text-black'
                : 'text-[#4b5563] group-hover:text-black',
            ]"
          >
            {{ modelInfo.name }}
          </n-ellipsis>
          <n-button
            quaternary
            :theme-overrides="{
              textColor: '#00000099',
              colorQuaternaryHover: '#00000022',
              paddingMedium: '10px',
            }"
            class="h-4 w-4 transition-opacity duration-300"
            :class="[activeModel?.id === modelInfo.id || modelInfo.isDirty ? 'opacity-100' : 'opacity-0 group-hover:opacity-100']"
            @click.stop="handleCloseEditor(modelInfo)"
          >
            <template #icon>
              <n-icon size="14">
                <icon-octicon-dot-fill-16 v-if="modelInfo.isDirty" class="group-hover:hidden" />
                <icon-ion-close :class="modelInfo.isDirty ? 'group-hover:block hidden' : ''" />
              </n-icon>
            </template>
          </n-button>
        </div>
      </div>
    </n-scrollbar>

    <div class="mx-2 flex flex-grow items-center justify-end gap-x-4 bg-transparent">
      <tooltip-button
        v-if="showSplitButton"
        tooltip="Split Editor"
        :button-props="{
          size: 'tiny',
          quaternary: true,
          themeOverrides: {
            textColor: '#333333',
          },
        }"
        class="opacity-30 hover:opacity-100"
        :icon="SplitHorizontal"
        :icon-props="{ size: 16 }"
        @click="addSplit()"
      />
      <n-dropdown
        trigger="click"
        :options="dropdownOptions"
        :show-arrow="false"
        @select="handleDropdownSelect"
      >
        <div>
          <tooltip-button
            class="opacity-30 hover:opacity-100"
            tooltip="Handle Tab Actions"
            :button-props="{
              size: 'tiny',
              quaternary: true,
              themeOverrides: {
                textColor: '#333333',
              },
            }"
            :icon="EllipsisHorizontal"
            :icon-props="{ size: 16 }"
          />
        </div>
      </n-dropdown>
    </div>
    <n-dropdown
      placement="bottom-start"
      trigger="manual"
      :x="xRef"
      :y="yRef"
      :options="dropdownOptions"
      :show="showDropdownRef"
      :on-clickoutside="() => showDropdownRef = false"
      @select="handleDropdownSelect"
    />
  </div>
</template>

<script setup lang="ts">
import type { DropdownOption } from "naive-ui"
import type { Raw } from "vue"
import type { DiffModelInfo, EditorType, ModelInfo } from "./store/editorStore"

import { isDiffEditor } from "@airalogy/components/monaco-editor/utils"
import { useSortable, useThemeStore } from "@airalogy/composables"
import { getFileSpecificIcon } from "@airalogy/shared/utils"
import EllipsisHorizontal from "~icons/ion/ellipsis-horizontal"
import SplitHorizontal from "~icons/lucide/square-split-horizontal"

import { NIcon, useDialog } from "naive-ui"
import { storeToRefs } from "pinia"
import { isDiffModelInfo, isNormalModelInfo, useActiveEditorStore, useEditorStore, useModelsStore, useSplitStore } from "./store/editorStore"
import { useUploadFileDataStore } from "./store/uploadFileDataStore"
import { useWebContainerStore } from "./store/webContainerStore"

interface Props {
  editorId: number
}

const props = defineProps<Props>()

// Stores
const modelsStore = useModelsStore()
const editorStore = useEditorStore()
const splitStore = useSplitStore()
const activeEditorStore = useActiveEditorStore()
const webContainerStore = useWebContainerStore()
const uploadFileDataStore = useUploadFileDataStore()

const { webContainerInstance } = storeToRefs(webContainerStore)
const { removeModelById, removeModel, removeAllEditorModels, saveModelInfo, getActiveModelInfo, setActiveModelInfo, clearActiveModelInfo } = modelsStore
const { getEditorInfo } = editorStore
const { addSplit, removeSplit } = splitStore
const { updateFileItem } = uploadFileDataStore

const { currentSplitSize } = storeToRefs(splitStore)
const { modelInfos } = storeToRefs(modelsStore)

const tabRefs = ref<Map<string, HTMLDivElement>>(new Map())

function setTabRef(id: string, el: any) {
  tabRefs.value.set(id, el)
}
// Get theme store
const themeStore = useThemeStore()
// Dark mode has been removed from the project

const dialog = useDialog()

// Refs
const mockModelInfosForSort = ref<ModelInfo[]>([])
const tabBarRef = ref<HTMLDivElement>()

// Computed
const currentEditor = shallowRef<Raw<EditorType> | null>(null)
const activeModel = computed(() => getActiveModelInfo(props.editorId))

const showSplitButton = computed(() => activeEditorStore.activeEditorId === props.editorId || (activeEditorStore.activeEditorId === -1 && props.editorId === 0))

// Watch for models changes
watch(modelInfos, async (newModels) => {
  await nextTick()
  // mockModelsForSort.value = newModels.map((item: ModelInfo) => ({ ...item }))
  mockModelInfosForSort.value = newModels.filter((item, _, ary): item is ModelInfo => {
    if (isDiffModelInfo(item)) {
      const { source } = item

      return ary.findIndex(m => m.id === source.id) === -1
    }

    const { usedBy, name: filename } = item

    return Boolean(filename && usedBy?.includes(props.editorId))
  })

  // remove all tab refs not in newModels
  Object.keys(tabRefs.value).forEach((id) => {
    if (!newModels.some(model => model.id === id)) {
      tabRefs.value.delete(id)
    }
  })
}, { deep: true, immediate: true, flush: "post" })

watch(activeModel, (newActiveModel) => {
  if (!newActiveModel) {
    return
  }

  const targetTab = unrefElement(tabRefs.value.get(newActiveModel.id))
  if (targetTab) {
    targetTab.scrollIntoView({ behavior: "smooth", block: "center" })
  }
})

const isDragging = ref(false)
// Sortable setup
const { start, stop, option } = useSortable(tabBarRef, mockModelInfosForSort, {
  onEnd: (e) => {
    isDragging.value = false
  },
  onStart: () => {
    isDragging.value = true
  },
})
option("animation", 300)

// Methods
function handleTabClick(modelInfo: ModelInfo | DiffModelInfo) {
  const editorInfo = getEditorInfo(props.editorId)
  if (!editorInfo) {
    return
  }
  if (isDiffEditor(editorInfo.editor)) {
    if (isDiffModelInfo(modelInfo)) {
      const { source, target } = modelInfo
      editorInfo.editor.setModel(toRaw({ original: source, modified: target }))
    }
  }
  else if (isNormalModelInfo(modelInfo) && modelInfo.model) {
    editorInfo.editor.setModel(toRaw(modelInfo.model))
  }

  // Get the current editor
  setActiveModelInfo(modelInfo, props.editorId)
}

async function handleCloseEditor(modelInfo: ModelInfo | DiffModelInfo | null) {
  if (!modelInfo) {
    return
  }

  try {
    if (isNormalModelInfo(modelInfo) && modelInfo.isDirty) {
      const d = dialog.warning({
        title: `Save changes to ${modelInfo.name}?`,
        content: "Your changes will be lost if you don't save them.",
        positiveText: "Save",
        negativeText: "Don't Save",
        onPositiveClick: async () => {
          await saveModelInfo(modelInfo, webContainerInstance.value, updateFileItem)
          closeEditorTab(modelInfo)
        },
        onNegativeClick: () => {
          closeEditorTab(modelInfo)
        },
      })
    }
    else {
      closeEditorTab(modelInfo)
    }
  }
  catch (error) {
    console.error("Error closing editor:", error)
  }
}

// function closeEditorTabById(modelId: string) {
//   const { editorId } = props

//   const newModel = removeModelById(modelId, editorId)

//   if (newModel && newModel.id) {
//     setActiveModelInfo(newModel.id, newModel, editorId)
//     if (currentEditor.value) {
//       currentEditor.value.setModel(toRaw(newModel.model))
//     }
//   }
//   else {
//     handleCloseAll()
//   }
// }

function closeEditorTab(modelInfo: ModelInfo | DiffModelInfo) {
  const editor = currentEditor.value

  const newModel = removeModel(modelInfo, props.editorId)

  if (newModel) {
    setActiveModelInfo(newModel, props.editorId)
    if (!editor) {
      return
    }
    if (isDiffEditor(editor)) {
      if (isDiffModelInfo(newModel)) {
        const { source, target } = newModel
        if (isDiffEditor(editor)) {
          editor.setModel(toRaw({ original: source, modified: target }))
        }
      }
    }
    else if (isNormalModelInfo(newModel) && newModel.model) {
      editor.setModel(toRaw(newModel.model))
    }
  }
  else {
    removeSplit(props.editorId)
  }
}

async function handleCloseAll() {
  try {
    const dirtyModels = modelInfos.value.filter(m => isNormalModelInfo(m) && m.isDirty && m.usedBy.includes(props.editorId))

    if (dirtyModels.length > 0) {
      const fileList = dirtyModels.map(m => `• ${m.name}`).join("\n")
      const d = dialog.warning({
        title: "Save changes?",
        content: `The following files have unsaved changes:\n\n${fileList}`,
        positiveText: "Save All",
        negativeText: "Don't Save",
        onPositiveClick: async () => {
          for (const model of dirtyModels) {
            if (isNormalModelInfo(model)) {
              await saveModelInfo(model, webContainerInstance.value, updateFileItem)
            }
          }
          closeAllTabs()
        },
        onNegativeClick: () => {
          closeAllTabs()
        },
      })
      return
    }

    closeAllTabs()
  }
  catch (error) {
    console.error("Error closing all tabs:", error)
  }
}

function closeAllTabs() {
  const editor = currentEditor.value
  if (!editor) {
    return
  }

  // Clear the editor model first
  editor.setModel(null)

  // Remove all models and cleanup state
  removeAllEditorModels(props.editorId)
  clearActiveModelInfo(props.editorId)

  // Handle split editor cleanup
  if (currentSplitSize.value > 1) {
    // Save reference to the first editor before removing this one
    const firstEditor = editorStore.getEditorInfo(0)

    // Remove the current editor and its split
    editorStore.removeEditor(props.editorId)
    splitStore.removeSplit(props.editorId)

    // Only set active editor if it exists
    if (firstEditor) {
      activeEditorStore.setActiveEditor(firstEditor.editor, 0)
    }
  }
}

async function handleCloseOthers() {
  try {
    const activeModel = getActiveModelInfo(props.editorId)
    if (!activeModel?.id)
      return

    const dirtyModels = modelInfos.value.filter(model =>
      model.id !== activeModel.id
      && (isNormalModelInfo(model)
        ? model.usedBy.includes(props.editorId)
        && model.isDirty
        : true),
    )

    if (dirtyModels.length > 0) {
      const fileList = dirtyModels.map(m => `• ${m.name}`).join("\n")
      const d = dialog.warning({
        title: "Save changes to other files?",
        content: `The following files have unsaved changes:\n\n${fileList}`,
        positiveText: "Save All",
        negativeText: "Don't Save",
        onPositiveClick: async () => {
          for (const model of dirtyModels) {
            if (isNormalModelInfo(model)) {
              await saveModelInfo(model, webContainerInstance.value, updateFileItem)
            }
          }
          closeOtherTabs(activeModel.id)
        },
        onNegativeClick: () => {
          closeOtherTabs(activeModel.id)
        },
      })
      return
    }

    closeOtherTabs(activeModel.id)
  }
  catch (error) {
    console.error("Error closing other tabs:", error)
  }
}

function closeOtherTabs(activeModelId: string) {
  const modelsToRemove = modelInfos.value.filter(model =>
    model.id !== activeModelId
    && (isNormalModelInfo(model)
      ? model.usedBy.includes(props.editorId)
      : true),
  )

  for (const model of modelsToRemove) {
    removeModelById(model.id, props.editorId)
  }
}

const dropdownOptions = computed(() => {
  const activeModel = getActiveModelInfo(props.editorId, "all", false)
  const canSave = Boolean(activeModel && isNormalModelInfo(activeModel) && activeModel.isDirty)

  return [
    {
      label: "Save",
      key: "save",
      disabled: !canSave,
    },
    {
      label: "Close",
      key: "close",
    },
    {
      label: "Close All",
      key: "close-all",
    },
    {
      label: "Close Others",
      key: "close-others",
    },
  ] as DropdownOption[]
})

function handleDropdownSelect(key: string) {
  switch (key) {
    case "save":
      handleSave()
      break
    case "close":
      handleCloseEditor(activeModel.value)
      break
    case "close-all":
      handleCloseAll()
      break
    case "close-others":
      handleCloseOthers()
      break
  }
}

const showDropdownRef = ref(false)
const xRef = ref(0)
const yRef = ref(0)

async function handleContextMenu(modelId: string, e: MouseEvent) {
  e.preventDefault()
  showDropdownRef.value = false
  await nextTick()
  showDropdownRef.value = true
  xRef.value = e.clientX
  yRef.value = e.clientY
}

// Save the current file
function handleSave() {
  const activeModel = getActiveModelInfo(props.editorId)
  if (activeModel && isNormalModelInfo(activeModel)) {
    saveModelInfo(
      activeModel,
      webContainerInstance.value,
      updateFileItem,
    )
  }
}

watchEffect(() => {
  currentEditor.value = getEditorInfo(props.editorId)?.editor || null
})
</script>

<style lang="sass" scoped>
.editor__tab-bar
  @apply flex items-center justify-start bg-transparent text-xs font-light

  :deep(.n-scrollbar-rail--horizontal)
    bottom: -4px!important
  &-item
    @apply h-full flex cursor-pointer items-center gap-1 b-b-1 b-transparent px-2 py-1 text-xs font-light transition-colors duration-300
    max-width: 360px
  &-item:hover
    @apply bg-transparent
  &-item:hover:not(:active)
    @apply bg-transparent
  &-item:active
    @apply bg-transparent
</style>
