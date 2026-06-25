<template>
  <div
    ref="dropZoneRef"
    class="size-full flex flex-col border border-transparent bg-light text-dark"
    :class="{
      'hidden': !isActive,
      '!border-primary': isOverDropZone,
    }"
  >
    <tab-bar
      :editor-id="props.editorId"
      class="h-8 w-full bg-[#f5f5f5]"
    />
    <breadcrumbs-below-tabs
      :editor-id="props.editorId"
      class="w-full bg-[#f0f0f0]"
      :load-options="loadItemOptions"
      @select="handleBreadcrumbSelect"
    />

    <editor-container
      :editor-id="props.editorId"
      class="flex-1"
      theme="light-plus"
      :options="editorOptions"
      :mode="isDiff ? 'diff' : 'normal'"
      @mount:editor="handleEditorDidMount"
      @selection:change="handleSelectionChange"
    />
    <protocol-bubble-menu v-if="dropZoneRef" :container-ref="dropZoneRef" />
  </div>
</template>

<script setup lang="ts">
// import type { WebContainer } from "@webcontainer/api"
import type * as Monaco from "monaco-editor"
import type { ShallowRef } from "vue"
import type { FileSystemItem } from "./types"

import { useDropZone } from "@vueuse/core"
import { type DropdownOption, NIcon } from "naive-ui"
import { storeToRefs } from "pinia"
// import parserBabel from "prettier/plugins/babel"
// import parserEstree from "prettier/plugins/estree"
import ProtocolBubbleMenu from "@airalogy/components/protocol-bubble-menu.vue"
import { getFileSpecificIcon, shouldPreviewFile } from "@airalogy/shared/utils"
import BreadcrumbsBelowTabs from "./breadcrumbs-below-tabs.vue"
import EditorContainer from "./editor-container/index.vue"
import {
  type EditorType,
  isDiffModelInfo,
  useActiveEditorStore,
  useEditorStore,
  useModelsStore,
  useSplitStore,
} from "./store/editorStore"
import { useFilePreviewStore } from "./store/filePreviewStore"
import { useProtocolDocumentsStore } from "./store/protocolDocumentsStore"
import { isPending, useUploadFileDataStore } from "./store/uploadFileDataStore"
import { useWebContainerStore } from "./store/webContainerStore"
import TabBar from "./tab-bar.vue"
import { isDiffEditor, isDirectory, isFile, openEditor } from "./utils"
import { saveProjectData } from "./utils/filesystem"

interface Props {
  editorId: number
}

const props = defineProps<Props>()

const webContainerStore = useWebContainerStore()
const uploadFileDataStore = useUploadFileDataStore()
const modelsStore = useModelsStore()
const activeEditorStore = useActiveEditorStore()
const previewStore = useFilePreviewStore()
const splitStore = useSplitStore()
const editorStore = useEditorStore()

const { getEditorInfo, setEditorInfo } = editorStore
const { setActiveModelInfo, getActiveModelInfo, saveModelInfo, getModelInfo, setModels } = modelsStore
const { setActiveEditor } = activeEditorStore
const { openFilePreview } = previewStore
const { updateFileItem, getFileById } = uploadFileDataStore
const { addSplit } = splitStore

const { webContainerInstance } = storeToRefs(webContainerStore)
const { fileData } = storeToRefs(uploadFileDataStore)
const { modelInfos } = storeToRefs(modelsStore)
const { activeEditorId, activeEditor } = storeToRefs(activeEditorStore)
const { splitState } = storeToRefs(splitStore)

const dropZoneRef = ref<HTMLDivElement>()
const currentModelInfo = computed(() => getActiveModelInfo(props.editorId, "all", false))
const isDiff = computed(() => currentModelInfo.value && isDiffModelInfo(currentModelInfo.value))

const monaco = injectLocal<ShallowRef<typeof Monaco | null>>("monaco", shallowRef(null))
// Current editing model path for syncing with webContainer filesystem
const currentPath = computed(() => (currentModelInfo.value as any)?.path)
const currentId = computed(() => (currentModelInfo.value as any)?.id)
const isActive = computed(() => getEditorInfo(props.editorId) === null || !!currentModelInfo.value)

const { isOverDropZone } = useDropZone(dropZoneRef, {
  onDrop: (files) => {
    // Handle dropped files here if needed
    console.log("Files dropped:", files)
  },
})

const defaultOptions = computed((): Monaco.editor.IStandaloneEditorConstructionOptions => ({
  minimap: { enabled: false }, // 暂时禁用 Minimap，避免主题服务错误
  fontSize: 16,
  wordWrap: "on",
  automaticLayout: true,
  theme: "light-plus",
}))

const editorOptions = computed(() => {
  const { options } = currentModelInfo.value || {}
  if (!options) {
    return defaultOptions.value
  }

  return {
    ...defaultOptions.value,
    ...options,
  }
})

const protocolDocumentsStore = useProtocolDocumentsStore()
const { updateDocumentContentById: updateDocumentContent } = protocolDocumentsStore
// Format code with Prettier
// async function formatWithPrettier(
//   item: Monaco.editor.IStandaloneCodeEditor,
//   prettierConfig: Record<string, any> = {},
// ) {
//   if (!item)
//     return

//   try {
//     const model = item.getModel()
//     if (!model)
//       return

//     const unformattedCode = model.getValue()
//     // const prettier = await import("prettier/standalone")

//     // const formattedCode = await prettier.format(unformattedCode, {
//     //   parser: "babel",
//     //   // plugins: [parserBabel, parserEstree],
//     //   ...prettierConfig,
//     // })

//     model.pushEditOperations(
//       [],
//       [
//         {
//           range: model.getFullModelRange(),
//           text: unformattedCode,
//         },
//       ],
//       () => null,
//     )
//   }
//   catch (error) {
//     console.error("Error formatting code:", error)
//   }
// }

async function handleEditorDidMount(editor: EditorType) {
  const monacoInstance = monaco.value

  if (!monacoInstance) {
    return
  }

  setEditorInfo(props.editorId, editor)
  if (isDiffEditor(editor)) {
    handleDiffEditor(editor, monacoInstance)
  }
  else {
    handleNormalEditor(editor, monacoInstance)
  }

  editor.updateOptions({ theme: "light-plus" })
}

async function handleNormalEditor(editor: Monaco.editor.IStandaloneCodeEditor, monacoInstance: typeof Monaco) {
  setEditorInfo(props.editorId, editor)

  // Register content change listener to track dirty state
  const disposable = editor.onDidChangeModelContent((event) => {
    if (currentModelInfo.value && !isDiffModelInfo(currentModelInfo.value)) {
      currentModelInfo.value.isDirty = computeIsDirty(editor, currentModelInfo.value.lastSavedVersionId || 1)
    }
  })

  // Add keyboard shortcut for saving (Ctrl+S or Cmd+S)
  editor.addCommand(monacoInstance.KeyMod.CtrlCmd | monacoInstance.KeyCode.KeyS, async () => {
    const activeModelInfo = getActiveModelInfo(props.editorId, "normal", false)
    if (!activeModelInfo) {
      return null
    }

    // Get upload store first
    const uploadFileDataStore = useUploadFileDataStore()
    const { fileData, packageId, updateFileItem: updateFileItemFn, getFileByFilename } = uploadFileDataStore

    // Save the model info (updates memory, WebContainer, clears dirty flag)
    // Don't pass updateFileItem here - we'll call it manually with await
    const savedContent = saveModelInfo(
      activeModelInfo,
      webContainerInstance.value,
      undefined, // Don't pass updateFileItem callback
    )

    if (activeModelInfo.id.startsWith("doc-preview-")) {
      updateDocumentContent(activeModelInfo.id, savedContent || "")
    }

    // Now update fileData and save to OPFS
    if (fileData && packageId && savedContent !== undefined) {
      try {
        // Find the file in fileData by filename (not by model ID!)
        const fileInData = getFileByFilename(activeModelInfo.name)

        if (fileInData) {
          console.log("[Editor] Found file in fileData:", fileInData.name, "id:", fileInData.id)

          // Update fileData with the new content using the CORRECT file ID and field name
          await updateFileItemFn(fileInData.id, {
            content: savedContent,
          })

          // Save the updated fileData to OPFS
          await saveProjectData(packageId, fileData, () => Promise.resolve())
          console.log("[Editor] Saved to OPFS after Cmd+S")
        }
        else {
          console.warn("[Editor] File not found in fileData:", activeModelInfo.name)
        }
      }
      catch (error) {
        console.error("[Editor] Failed to save to OPFS:", error)
      }
    }

    // Prevent default browser save dialog from opening
    return null
  })

  // Remember to dispose event listeners when editor is disposed
  editor.onDidDispose(() => {
    disposable.dispose()

    // // Handle cleanup for shared models
    // const activeModel = getActiveModelInfo(props.editorId, "normal")
    // if (activeModel?.usedBy) {
    //   // Remove this editor from the usedBy array
    //   const usedByIndex = activeModel.usedBy.indexOf(props.editorId)
    //   if (usedByIndex !== -1) {
    //     activeModel.usedBy.splice(usedByIndex, 1)
    //     console.log(`Editor ${props.editorId} removed from model ${activeModel.id} usedBy list. Remaining users: ${activeModel.usedBy.join(", ") || "none"}`)
    //   }
    // }
  })

  // Try to find an active editor to duplicate its content
  const activeEditorId = activeEditorStore.activeEditorId

  // Check if we have a valid active editor with a valid model
  const activeNormalModelInfo = getActiveModelInfo(activeEditorId, "normal")

  try {
    // Get the current active model
    if (activeNormalModelInfo) {
      const modelInstance = toRaw(activeNormalModelInfo.model) as Monaco.editor.ITextModel

      // Only proceed if the model is valid and not disposed
      if (!modelInstance.isDisposed()) {
        console.log(`Sharing model from editor ${activeEditorId} to new split ${props.editorId}`)

        // Instead of duplicating, directly use the same model instance
        editor.setModel(modelInstance)

        // Update the tracking to include this editor in usedBy array
        if (!activeNormalModelInfo.usedBy) {
          activeNormalModelInfo.usedBy = [props.editorId]
        }
        else if (!activeNormalModelInfo.usedBy.includes(props.editorId)) {
          activeNormalModelInfo.usedBy.push(props.editorId)
        }

        // Register the shared model in our store for this editor
        setActiveModelInfo(activeNormalModelInfo, props.editorId)

        // Don't need to continue further since we've set up the model
        setActiveEditor(editor, props.editorId)
        return
      }
    }
  }
  catch (error) {
    console.error("Error sharing active editor model:", error)
    // Continue with fallback options below if sharing fails
  }

  // If we couldn't duplicate from the active editor or there isn't one,
  // try to get the model from other valid editors
  const newModel = activeEditorId < 1 ? getActiveModelInfo(0, "normal") : getActiveModelInfo(1, "normal")

  if (newModel) {
    try {
      // Check if the model is valid and not disposed
      const modelInstance = toRaw(newModel.model) as Monaco.editor.ITextModel

      // Skip if the model is disposed
      if (!modelInstance || modelInstance.isDisposed()) {
        console.warn("Attempted to use a disposed model. Creating a new model instead.")
        // Create a new model with the same content if possible
        let content = ""
        let language = "plaintext"

        try {
          // Try to get content from the original model info
          content = newModel.content || ""
          language = newModel.language || "plaintext"
        }
        catch (e) {
          console.warn("Could not recover content from disposed model", e)
        }

        const defaultModel = toRaw(monacoInstance.editor.createModel(content, language))
        await nextTick()
        editor.setModel(defaultModel)

        // Update the model registry with the new model
        setActiveModelInfo({
          ...newModel,
          model: defaultModel,
          usedBy: [props.editorId],
        }, props.editorId)
        return
      }

      // Use nextTick to prevent UI freeze
      await nextTick()

      // Update the usedBy array to include this editor
      if (!newModel.usedBy) {
        newModel.usedBy = [props.editorId]
      }
      else if (!newModel.usedBy.includes(props.editorId)) {
        newModel.usedBy.push(props.editorId)
        console.log(`Fallback: Model ${newModel.id} now used by editors: ${newModel.usedBy.join(", ")}`)
      }

      setActiveModelInfo(newModel, props.editorId)
      editor.setModel(modelInstance)
    }
    catch (error) {
      console.error("Error setting editor model:", error)
      // Fallback to creating a new model
      const defaultModel = toRaw(monacoInstance.editor.createModel("", "plaintext"))
      await nextTick()
      editor.setModel(defaultModel)
    }
  }

  await nextTick()
  // Fallback for when no existing model is available
  if (modelInfos.value.length === 0) {
    const defaultModel = toRaw(monacoInstance.editor.createModel("", "plaintext"))
    editor.setModel(defaultModel)
  }

  editor.onDidFocusEditorText(() => {
    setActiveEditor(editor, props.editorId)
  })

  // Add save command with debounce
  // editor.addCommand(KeyMod.CtrlCmd | KeyCode.KeyS, () => {
  //   const prettierValue = getPrettierConfig(fileData.value)
  //   formatWithPrettier(editor, prettierValue)
  // })
}

async function handleDiffEditor(editor: Monaco.editor.IStandaloneDiffEditor, monacoInstance: typeof Monaco) {
  // Try to find an active editor to duplicate its content
  // Check if we have a valid active editor with a valid model
  const activeDiffModelInfo = getActiveModelInfo(0, "diff")

  if (activeDiffModelInfo) {
    const { source, target } = toRaw(activeDiffModelInfo)

    editor.setModel({
      original: source,
      modified: target,
    })
  }
}

function handleSelectionChange(event: Monaco.editor.ICursorSelectionChangedEvent) {
  const { selection } = event
}

// function handleEditorChange(value: string = "") {
//   console.log("handleEditorChange", value)
//   if (currentId.value) {
//     updateItem(currentId.value, { value })
//   }

//   if (webContainerInstance.value && currentPath.value) {
//     writeFile(currentPath.value, value, webContainerInstance.value as WebContainer)
//   }
// }

// Theme is fixed to light-plus, no need to watch for changes

// Helper function to find items at the same directory level as the given path
function getSiblingOptions(items: FileSystemItem[], targetPath: string): DropdownOption[] {
  const options: DropdownOption[] = []

  // Find the parent directory path
  const parentPath = targetPath.split("/").slice(0, -1).join("/")

  // Find all items that share the same parent path
  for (const item of items) {
    const itemParentPath = item.path.split("/").slice(0, -1).join("/")
    if (itemParentPath === parentPath) {
      options.push({
        label: item.name,
        key: item.id,
        disabled: !item.isSelectable,
        props: {
          class: item.path === targetPath ? "n-dropdown-option-body--active" : "",
        },
        icon: () => h(NIcon, { component: getFileSpecificIcon(item.name) }),
      })
    }

    // Recursively search in children
    if (isDirectory(item) && item.children && item.children.length > 0) {
      options.push(...getSiblingOptions(item.children, targetPath))
    }
  }

  return options
}

function loadItemOptions(path: string): DropdownOption[] {
  if (!fileData.value)
    return []

  // Get all sibling options for the current path
  const options = getSiblingOptions(fileData.value, path)

  return options.sort((a, b) => (a.label as string).localeCompare(b.label as string))
}

function computeIsDirty(editor: Monaco.editor.IStandaloneCodeEditor, initialVersionId?: number): boolean {
  if (!editor) {
    return true
  }

  const model = editor.getModel()
  if (!model) {
    return false
  }

  // Get current version ID
  const currentVersionId = model.getAlternativeVersionId()

  // If versions differ, changes exist
  return initialVersionId !== currentVersionId
}

async function handleBreadcrumbSelect(key: string | number) {
  if (!key || !monaco.value) {
    return
  }

  const file = getFileById(String(key))
  if (!file || !isFile(file)) {
    return
  }

  const { status, name, id } = file
  if (status === "pending" || isPending(name)) {
    return
  }

  // Check if this file should be previewed instead of edited
  if (shouldPreviewFile(name)) {
    openFilePreview(file)
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
    item: file,
  })
}
</script>
