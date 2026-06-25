<template>
  <n-popconfirm
    v-for="action in actions"
    :key="action.id"
    :trigger="action.confirmMessage ? 'click' : 'manual'"
    @positive-click="action.handler"
    @update:show="(val: boolean) => setActiveAction(val)"
  >
    <template #trigger>
      <n-button
        quaternary
        class="action-button"
        :class="{ 'action-button--active': isActive }"
        color="black"
        :disabled="isEditorReadOnly"
        @click.stop="handleClick($event, action)"
      >
        <template #icon>
          <n-icon size="12">
            <component :is="action.icon" />
          </n-icon>
        </template>
      </n-button>
    </template>
    <template v-if="action.confirmMessage" #default>
      {{ action.confirmMessage(props.item) }}
    </template>
  </n-popconfirm>
</template>

<script setup lang="ts">
import type { WebContainer } from "../../../types/fileSystem"
import type { TreeViewElement } from "../types"
import { isDiffEditor, rm } from "@airalogy/components/monaco-editor/utils"
import { useBoolean, useThemeStore } from "@airalogy/composables"
import EditIcon from "~icons/tabler/edit"
import DeleteIcon from "~icons/tabler/trash"
import { useDialog } from "naive-ui"
import { storeToRefs } from "pinia"
import { isNormalModelInfo, useEditorStore, useModelsStore, useSplitStore } from "../../../store/editorStore"
import { useUploadFileDataStore } from "../../../store/uploadFileDataStore"
import { useWebContainerStore } from "../../../store/webContainerStore"

interface Props {
  item: TreeViewElement
  isDirty: boolean
}

const props = defineProps<Props>()

const modelsStore = useModelsStore()
const editorStore = useEditorStore()
const splitStore = useSplitStore()
const fileDataStore = useUploadFileDataStore()
const webContainerStore = useWebContainerStore()

const { removeFileById, updateFileItem } = fileDataStore
const { removeModelById: removeModel, removeAllEditorModels: removeAllModel } = modelsStore
const { removeEditor } = editorStore
const { removeSplit } = splitStore

const { webContainerInstance } = storeToRefs(webContainerStore)
const { currentSplitSize } = storeToRefs(splitStore)
const isEditorReadOnly = injectLocal<Ref<boolean>>("isEditorReadOnly")
const themeStore = useThemeStore()

const { bool: isActive, setBool: setActiveAction } = useBoolean()
const dialog = useDialog()
async function handleDelete(e: Event) {
  let isConfirmed
  if (props.isDirty) {
    isConfirmed = new Promise((resolve) => {
      dialog.warning({
        title: "Warning",
        content: "This file is not saved. Are you sure you want to delete it?",
        positiveText: "Yes",
        negativeText: "No",
        onPositiveClick: () => resolve(true),
        onNegativeClick: () => resolve(false),
      })
    })
  }
  if (isConfirmed) {
    const result = await isConfirmed
    if (!result) {
      return
    }
  }

  const { id, path, kind } = props.item

  if (webContainerInstance.value) {
    await rm(path, webContainerInstance.value as WebContainer)
  }

  removeFileById(id)

  const { editorMap } = editorStore
  if (kind === "file") {
    editorMap.forEach((editor, editorId) => {
      removeModel(id, editorId)
    })
    return
  }

  editorMap.forEach(({ editor }, editorId) => {
    const newModels = removeModel(id, editorId)

    if (newModels && "filename" in newModels) {
      modelsStore.setActiveModelInfo(newModels, editorId)

      if (editor && !isDiffEditor(editor) && isNormalModelInfo(newModels)) {
        editor.setModel(toRaw(newModels.model))
      }
    }
    else {
      removeAllModel(editorId)
      if (editor) {
        editor.setModel(null)
      }

      if (currentSplitSize.value > 1) {
        removeEditor(editorId)
        removeSplit(editorId)
      }
    }
  })
}

function handleEdit(e: Event) {
  const { id } = props.item
  updateFileItem(id, { status: "pending" })
}

interface Action {
  id: string
  icon: Component
  handler: (e: Event) => void
  confirmMessage?: (item: TreeViewElement) => string
}

// Define actions array for v-for iteration
const actions: Action[] = [
  {
    id: "delete",
    icon: DeleteIcon,
    handler: handleDelete,
    confirmMessage: (item: TreeViewElement) => `Are you sure you want to delete "${item.name}"?`,
  },
  {
    id: "edit",
    icon: EditIcon,
    handler: handleEdit,
  },
]

function handleClick(e: PointerEvent | MouseEvent, action: Action) {
  if (action.confirmMessage) {
    return
  }

  action.handler(e)
}
</script>

<style scoped lang="sass">
.action-button
  @apply mx-0.5 hidden h-5 w-5 opacity-0 group-hover:flex !p-0 group-hover:opacity-70 !hover:opacity-100
  &--active
    @apply flex opacity-100!
</style>
