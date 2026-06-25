<template>
  <n-layout class="size-screen" content-class="flex flex-col">
    <n-layout-header :theme-overrides="{ headerColor: '#f7fafc' }">
      <tab-header :protocol-info="null" @new-file="emit('newFile', $event)" @save="handleSave">
        <template v-if="$slots.title" #title>
          <slot name="title" />
        </template>
      </tab-header>
    </n-layout-header>

    <!-- Read-only mode banner -->
    <n-alert
      v-if="isReadOnly"
      type="info"
      :bordered="false"
      class="rounded-none"
      :theme-overrides="{
        color: '#e6f4ff',
        contentTextColor: '#0958d9',
        border: '1px solid #91caff',
        iconColor: '#0958d9',
      }"
    >
      <template #icon>
        <n-icon :component="IconLock" />
      </template>
      <div class="flex items-center justify-between">
        <span class="font-medium">
          You are viewing a read-only version. Click the "Edit" button in the top bar to create an editable copy.
        </span>
      </div>
    </n-alert>

    <n-layout-content class="flex-1">
      <n-split
        v-if="!reloadFlag"
        :size="menuSplitSize" :min="DEFAULT_MENU_COLLAPSED_SIZE"
        class="relative size-full flex flex-1 overflow-hidden"
        :style="{ backgroundColor: '#f7fafc' }" :resize-trigger-size="2"
        :theme-overrides="{ resizableTriggerColor: '#cccccc0f' }" @update:size="handleUpdateSize"
      >
        <!-- Sidebar -->
        <template #1>
          <slot name="aside">
            <n-tabs
              ref="menusRef" v-model:value="activeMenu" :default-value="undefined" class="h-full !max-w-full"
              placement="left" tab-class="!p-1" pane-class="!p-0 flex-1 overflow-auto"
            >
              <n-tab-pane v-for="menu in sideMenus" :key="menu.key" :name="menu.key" display-directive="show">
                <template #tab>
                  <n-button
                    quaternary :type="menu.key === activeMenu ? 'primary' : 'default'"
                    :class="{ 'opacity-60 hover:opacity-100': menu.key !== activeMenu }"
                    @click="handleSideMenuClick(menu)"
                  >
                    <template #icon>
                      <n-icon :component="menu.icon" size="24" />
                    </template>
                  </n-button>
                </template>
                <component
                  :is="menu.component" v-if="!isMenuCollapsed && menu.component" class="size-full"
                  v-bind="menu.componentProps || {}" v-on="menu.componentEvents || {}"
                />
              </n-tab-pane>
            </n-tabs>
          </slot>
          <!-- File explorer panel -->
          <slot />
        </template>

        <!-- Main content area -->
        <template #2>
          <n-spin :show="loading" class="size-full" content-class="size-full">
            <!-- Editor and terminal panel -->
            <n-split
              v-if="splitState.some(Boolean)" v-model:size="contentSplitSize" class="size-full overflow-y-hidden"
              :theme-overrides="{ resizableTriggerColor: '#cccccc0f' }"
              :resize-trigger-size="2"
            >
              <template #1>
                <slot name="editor">
                  <split-editor :editor-id="0" :split-state="splitState" />
                </slot>
              </template>
              <!-- <preview /> -->
              <template #2>
                <file-preview-pane
                  v-model:is-full-screen="isFullScreen"
                  v-model:is-preview-mode="isPreviewMode"
                  :disabled="props.disabled"
                >
                  <template #prefix>
                    <slot name="prefix" v-bind="{ protocolContent }" />
                  </template>
                  <template #suffix>
                    <slot name="suffix" v-bind="{ protocolContent }" />
                  </template>
                  <template #preview>
                    <slot v-bind="{ protocolContent }" name="preview" />
                  </template>
                  <template #raw>
                    <slot name="raw" v-bind="{ protocolContent }" />
                  </template>
                </file-preview-pane>
              </template>
            </n-split>
            <slot v-else name="landing" />
          </n-spin>
        </template>
      </n-split>
    </n-layout-content>
  </n-layout>
</template>

<script setup lang="ts">
import type { useLoading } from "@airalogy/composables"
import type { ZipItem } from "@airalogy/shared"
import type { ProtocolModels } from "@airalogy/shared/types/models"

import type * as Monaco from "monaco-editor"
import type { NButton, NIcon, NLayout, NTab } from "naive-ui"
import type { ShallowRef } from "vue"

import type { FileInterface, FileSystemItem } from "./types"
import { useThemeStore } from "@airalogy/composables"

import IconLock from "~icons/tabler/lock"
import { NAlert } from "naive-ui"
import { storeToRefs } from "pinia"
import { onBeforeUnmount, ref, watch } from "vue"
import { useEditorBeforeUnload } from "./composables/useEditorBeforeUnload"
import { useFileUpload } from "./composables/useFileUpload"
import FilePreviewPane from "./FilePreviewPane.vue"
import SplitEditor from "./split-editor.vue"
import TabHeader from "./tab-header.vue"
import { defaultSideMenus, type ISideMenuItem } from "./utils/sideMenus"
// import Preview from "./preview/index.vue"
import { useDragIconStore } from "@airalogy/components/monaco-editor/store/dragIconStore"
import { arrayBufferToString, DEFAULT_FILE_ID_MAP } from "@airalogy/shared"
import { assert } from "@airalogy/shared/utils"
import { useLanguageClient } from "./composables/useLanguageClient"
import {
  DEFAULT_MENU_COLLAPSED_SIZE,
  type EditorInfo,
  type ModelInfo,
  useEditorStore,
  useModelsStore,
  useSplitStore,
} from "./store/editorStore"
import { useFilePreviewStore } from "./store/filePreviewStore"
import { useUploadFileDataStore } from "./store/uploadFileDataStore"
import { useWebContainerStore } from "./store/webContainerStore"
import { addNewModel, isDiffEditor, isFile, saveProjectData } from "./utils"
import { findByFilename } from "./utils/file-tree"

const props = withDefaults(defineProps<IProps>(), {
  isReadOnly: false,
  loading: false,
  sideMenus: () => [...defaultSideMenus],
  isFullScreen: false,
  isPreviewMode: false,
  uploadPackage: () => Promise.resolve(),
  packageId: null,
  emitZip: false,
  reloadFlag: false,
  disabled: false,
})

const emit = defineEmits<{
  (e: "showTemplateDialog", show: boolean): void
  (e: "redirect", id: string): void
  (e: "update:isFullScreen", val: boolean): void
  (e: "update:isPreviewMode", val: boolean): void
  (e: "update:isReadOnly", val: boolean): void
  (e: "update:packageId", val: string | null): void
  (e: "save", data: { items: ZipItem[], file: Uint8Array<ArrayBufferLike> }, toml: string): void
  (e: "save:dry"): void
  (e: "newFile", mode: "copy" | "empty"): void
}>()

interface IProps {
  loading?: boolean
  isReadOnly?: boolean
  isFullScreen?: boolean
  isPreviewMode?: boolean
  protocolInfo?: ProtocolModels.ProjectProtocolInfo | null
  sideMenus?: ISideMenuItem[]
  uploadPackage?: (id: string, data: FileSystemItem[]) => Promise<void>
  packageId?: string | null
  emitZip?: boolean
  reloadFlag?: boolean
  disabled?: boolean
}

// Refs and state
// const terminalRef = ref<InstanceType<typeof TerminalPanel> | null>(null)

const { isFullScreen, isPreviewMode, isReadOnly, packageId } = useVModels(props, emit)
provideLocal("isEditorReadOnly", isReadOnly)

const contentSplitSize = ref(0.5)
const { undo: undoContentSplitSize } = useRefHistory(contentSplitSize)
watch(isFullScreen, (val) => {
  if (val) {
    contentSplitSize.value = 0
  }
  else {
    undoContentSplitSize()
  }
})

const { monaco, init, loadingState } = useLanguageClient()

provideLocal("monaco", monaco)
// Store initialization
const splitStore = useSplitStore()
const editorStore = useEditorStore()
const modelsStore = useModelsStore()
const uploadFileDataStore = useUploadFileDataStore()
const webContainerStore = useWebContainerStore()
const themeStore = useThemeStore()
const filePreviewStore = useFilePreviewStore()

const { addSplit, clearSplit, handleUpdateSize } = splitStore
const { setModels, removeAllModels, setActiveModelInfo, clearAllActiveModelInfo } = modelsStore
const { removeAllEditors } = editorStore
const { initFileData, clearFileData, updateRootPath, getFileById } = uploadFileDataStore
const { compressFiles } = useFileUpload()
const { initWebContainer } = webContainerStore
const { splitState, menuSplitSize, activeMenu, isMenuCollapsed, customMenuSizeState } = storeToRefs(splitStore)
const { modelInfos } = storeToRefs(modelsStore)
const { fileData, rootPath } = storeToRefs(uploadFileDataStore)

// Add browser tab close confirmation when unsaved changes exist
useEditorBeforeUnload(modelInfos, isReadOnly)

const protocolContent = computed(() => {
  const protocolFile = getFileById("airalogy_protocol")
  if (!protocolFile) {
    return ""
  }

  return protocolFile.content
})

const menusRef = ref<(InstanceType<typeof NTab> & { barElRef: HTMLDivElement }) | null>(null)

// const dragIconRef = ref<HTMLDivElement>()
const { dragIconRef } = storeToRefs(useDragIconStore())
// Methods
// function handleFileDrop(event: any) {
//   const el = dragIconRef.value?.element
//   if (!el) {
//     return
//   }

//   el.style.display = "none"
//   el.style.left = "0px"
//   el.style.top = "0px"
//   el.innerHTML = ""

//   const { file, monacos } = event.active.data.current
//   const editor = event.over.data.current.editorInstance

//   const willChangeEditor = editor
//   const willChangeEditorId = event.over.id

//   const matchModel = models.value.find(model => model.id === file.id)

//   if (matchModel?.model) {
//     setActiveModelInfo(matchModel.id, matchModel, willChangeEditorId)
//     setModels(
//       { filename: matchModel.filename, value: "", language: "typescript", id: file.id },
//       matchModel.model,
//       willChangeEditorId,
//     )
//     willChangeEditor?.setModel(matchModel.model)
//   }
//   else {
//     const monaco = monacos[willChangeEditorId]
//     addNewModel(
//       file,
//       monaco,
//       willChangeEditor as Monaco.editor.IStandaloneCodeEditor,
//       setModels,
//       setActiveModelInfo,
//       willChangeEditorId,
//     )
//   }
// }

async function handleSideMenuClick(item: ISideMenuItem) {
  const { barElRef } = menusRef.value || {}
  const targetMenu = props.sideMenus.find(menu => menu.key === item.key)
  if (targetMenu?.panelSize) {
    customMenuSizeState.value = targetMenu.panelSize
  }
  else {
    customMenuSizeState.value = null
  }

  await nextTick()
  if (item.key === activeMenu.value) {
    activeMenu.value = undefined
    if (barElRef) {
      barElRef.style.opacity = "0"
    }
  }
  else {
    activeMenu.value = item.key
    if (barElRef) {
      barElRef.style.opacity = "1"
    }
  }
}

watch([activeMenu, () => menusRef.value?.barElRef], async ([newVal, barElRef]) => {
  if (!barElRef) {
    return
  }

  if (newVal) {
    barElRef.style.opacity = "1"
    barElRef.style.display = "block"
  }
  else {
    barElRef.style.opacity = "0"
    barElRef.style.display = "none"
  }
}, { immediate: true, flush: "post" })

function handleClearFileData(projectId?: string) {
  try {
    clearFileData(Boolean(projectId), projectId)
  }
  catch (error) {
    console.error(error)
  }
}

async function initProtocolFile(editor: Monaco.editor.IStandaloneCodeEditor, protocolFile: FileInterface) {
  if (!editor || !monaco.value) {
    return
  }

  const { name, content, id, path } = protocolFile
  const modelInfo: Omit<ModelInfo, "model"> = {
    name,
    content: content && typeof content !== "string" ? arrayBufferToString(content) : content || "",
    language: "aimd",
    id,
    isDirty: false,
    path,
    usedBy: [0],
    lastSavedVersionId: 1,
    type: "normal",
  }

  addNewModel(
    modelInfo,
    monaco.value,
    editor,
    setModels,
    setActiveModelInfo,
    0,
  )

  // Set editor option for readonly mode
  if (isReadOnly.value) {
    editor.updateOptions({ readOnly: true })
  }
}

watch(packageId, async (newVal) => {
  isReadOnly.value = !newVal
}, { immediate: true })

async function handleSave() {
  if (props.emitZip) {
    const result = await compressFiles()
    if (!result) {
      return
    }

    const tomlContent = getFileById(DEFAULT_FILE_ID_MAP.toml_config)

    if (!tomlContent) {
      return
    }

    assert(typeof tomlContent.content === "string")
    emit("save", result, tomlContent.content || "")
  }
  else {
    emit("save:dry")
  }
}

function handleClean(resist = true, id?: string | null) {
  removeAllModels()
  clearAllActiveModelInfo()
  clearSplit()
  clearFileData(resist, id || "")
  removeAllEditors()
}

async function saveData(id: string, data: FileSystemItem[]) {
  await saveProjectData(id, data, props.uploadPackage)
}

// const uploadPackage = () => Promise.resolve()
async function handleInit(id: string, prevId?: string | null, resist = false) {
  if (!monaco.value) {
    if (!loadingState.loading.value) {
      init()
    }

    await new Promise((resolve) => {
      watchOnce(monaco, () => {
        resolve(true)
      })
    })
    return
  }

  if (prevId) {
    await handleClearFileData(prevId)
  }

  if (!Array.isArray(fileData.value) || fileData.value.length === 0) {
    try {
      const result = await initFileData(id, props.protocolInfo || null)

      // If no protocol data was found and the template dialog should be shown,
      // redirect to landing page with query param to show the template dialog
      if (!result) {
        emit("showTemplateDialog", true)
        return
      }
    }
    catch (error) {
      console.error("Error initializing file data:", error)
      emit("redirect", id)

      return
    }
  }
  else {
    updateRootPath(fileData.value.map(item => item.path))
  }

  await initWebContainer(id, fileData, rootPath.value, saveData)

  // Use recursive search to find protocol.aimd file
  const protocolFile = fileData.value ? findByFilename(fileData.value, "protocol.aimd") : null

  if (!protocolFile || !isFile(protocolFile)) {
    return
  }

  const activeEditor = editorStore.getFirstNormalEditor()
  const handleEditorChange = async (editorInfo: EditorInfo<"normal">) => {
    const { editor } = editorInfo
    if (isDiffEditor(editor)) {
      return
    }

    await initProtocolFile(editor, protocolFile)
    if (resist && fileData.value) {
      await saveData(id, fileData.value)
    }
  }

  if (activeEditor) {
    await handleEditorChange(activeEditor)
  }
  else {
    const stop = watch(() => editorStore.getFirstNormalEditor(), async (editorInfo) => {
      if (editorInfo) {
        stop()
        await handleEditorChange(editorInfo)
      }
    })
    await addSplit()
  }
}

function handleOpenPreviewAsText() {
  const currentFile = filePreviewStore.currentPreviewFile
  if (!currentFile)
    return

  // Clear the preview mode
  filePreviewStore.clearPreview()

  // Open the file in Monaco editor as text
  const fileItem = {
    id: currentFile.id,
    name: currentFile.name,
    content: "", // Will be loaded from the file
    path: currentFile.path,
    url: currentFile.fileUrl,
  }

  // Use the existing openEditor logic but force it to open as text
  const activeEditor = editorStore.getFirstNormalEditor()
  if (activeEditor && monaco.value) {
    addNewModel(
      {
        ...fileItem,
        language: "plaintext", // Force as plain text
        content: fileItem.content || "",
        type: "normal",
      },
      monaco.value,
      activeEditor.editor,
      modelsStore.setModels,
      modelsStore.setActiveModelInfo,
      activeEditor.id,
    )
  }
}

// Lifecycle hooks
onMounted(() => {
  init()
})

onBeforeUnmount(() => {
  handleClean(false, packageId.value)
})

watch(() => props.reloadFlag, (val) => {
  if (val) {
    handleClean(false, packageId.value)
  }
})

export interface ExposeState {
  handleInit: (id: string, prevId?: string | null, resist?: boolean) => void
  handleClean: (resist?: boolean, id?: string | null) => void
  monaco: ShallowRef<typeof Monaco | null>
  loadingState: ReturnType<typeof useLoading>
}

defineExpose<ExposeState>({
  handleInit,
  handleClean,
  monaco,
  loadingState,
})
</script>

<style lang="sass" scoped>
.n-layout-sider
  @apply transition-all duration-300 ease-in-out

  :deep(.n-layout-sider-scroll-container)
    @apply h-full

:deep(.n-tree .n-tree-node-content .n-tree-node-content__text)
  @apply overflow-hidden

.n-divider
  @apply m-0
</style>
