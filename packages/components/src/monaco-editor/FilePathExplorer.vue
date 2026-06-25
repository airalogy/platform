<template>
  <n-auto-complete
    v-model:value="currentFilePath"
    :options="filePathOptions"
    class="flex-1"
    size="small"
    :placeholder="placeholder"
    :loading="pathLoading"
    @select="handlePathSelect"
    @keyup.enter="handlePathEnter"
    @update:value="handlePathUpdate"
  >
    <template #prefix>
      <n-icon>
        <icon-ion-folder-outline />
      </n-icon>
    </template>
    <template #suffix>
      <n-button
        v-if="currentFilePath !== displayedFilePath"
        quaternary
        size="tiny"
        @click="handlePathEnter"
      >
        <template #icon>
          <n-icon><icon-ion-enter-outline /></n-icon>
        </template>
      </n-button>
    </template>
  </n-auto-complete>
</template>

<script setup lang="ts">
import type { FileSystemItem } from "./types"
import { shouldPreviewFile } from "@airalogy/shared/utils"
import IconIonEnterOutline from "~icons/ion/enter-outline"
import IconIonFolderOutline from "~icons/ion/folder-outline"
import { NAutoComplete, NButton, NIcon, useMessage } from "naive-ui"
import { storeToRefs } from "pinia"
import { computed, ref, watch } from "vue"
import { useActiveEditorStore, useEditorStore, useModelsStore, useSplitStore } from "./store/editorStore"
import { useFilePreviewStore } from "./store/filePreviewStore"
import { useUploadFileDataStore } from "./store/uploadFileDataStore"
import { isDirectory, isFile, openEditor } from "./utils"
import { findByPath } from "./utils/file-tree"

// Props interface
interface Props {
  initialFilePath?: string
  placeholder?: string
}

// Define props with defaults
const props = withDefaults(defineProps<Props>(), {
  placeholder: "Enter file path...",
})

// Define emits for v-model support
const emit = defineEmits<{
  "update:modelValue": [value: string]
}>()

// Store instances
const filePreviewStore = useFilePreviewStore()
const uploadFileDataStore = useUploadFileDataStore()
const activeEditorStore = useActiveEditorStore()
const editorStore = useEditorStore()
const modelsStore = useModelsStore()
const splitStore = useSplitStore()
const message = useMessage()

// Get reactive refs from stores
const { fileData, rootPath } = storeToRefs(uploadFileDataStore)
const { splitState } = storeToRefs(splitStore)
const { activeEditor, activeEditorId } = storeToRefs(activeEditorStore)

// File Explorer functionality
const pathLoading = ref(false)

// Get current active file path from editor or model stores
function getCurrentActiveFilePath(): string {
  // Try to get from active editor model
  if (activeEditor.value && activeEditorId.value !== -1) {
    // Use getActiveModelInfo to get the model for this editor
    const modelInfo = modelsStore.getActiveModelInfo(activeEditorId.value)
    if (modelInfo?.path) {
      return modelInfo.path
    }
  }

  // Try to get from preview store
  if (filePreviewStore.currentPreviewFile?.path) {
    return filePreviewStore.currentPreviewFile.path
  }

  return ""
}

// Reactive current file path that considers props and application state
const currentFilePath = computed(
  () => {
    const activeFilePath = getCurrentActiveFilePath()
    if (activeFilePath) {
      return activeFilePath
    }

    if (props.initialFilePath) {
      return props.initialFilePath
    }

    return rootPath.value
  },
)

// Track the displayed file path separately for comparison
const displayedFilePath = ref(currentFilePath.value)

// Generate file path options for autocomplete
const filePathOptions = computed(() => {
  if (!fileData.value)
    return []

  const paths: { label: string, value: string }[] = []

  function collectPaths(items: FileSystemItem[], prefix = "") {
    items.forEach((item) => {
      // const fullPath = prefix ? `${prefix}/${item.name}` : `${props.rootPath}${item.name}`
      const { path } = item

      if (isFile(item)) {
        paths.push({
          label: path,
          value: path,
        })
      }

      if (isDirectory(item) && item.children && item.children.length > 0) {
        collectPaths(item.children, path)
      }
    })
  }

  collectPaths(fileData.value)

  // Filter based on current input
  const filterValue = currentFilePath.value.toLowerCase()
  return paths.filter(option =>
    option.value.toLowerCase().includes(filterValue),
  ).slice(0, 10) // Limit to 10 suggestions
})

// Navigate to file by path
async function navigateToFile(path: string) {
  if (!fileData.value)
    return false

  const targetFile = findByPath(fileData.value, path)

  if (targetFile && isFile(targetFile)) {
    displayedFilePath.value = path

    // Check if file should be previewed or opened in editor

    if (shouldPreviewFile(targetFile.name)) {
      filePreviewStore.openFilePreview(targetFile)
    }
    else {
      // Open in Monaco editor - use the openEditor utility
      await openEditor({
        activeEditor,
        activeEditorId,
        splitState,
        getEditorInfo: editorStore.getEditorInfo,
        getModelInfo: modelsStore.getModelInfo,
        setActiveModelInfo: modelsStore.setActiveModelInfo,
        setModels: modelsStore.setModels,
        setActiveEditor: activeEditorStore.setActiveEditor,
        addSplit: splitStore.addSplit,
        monaco: (window as any).monaco, // Access global Monaco instance
        id: targetFile.id,
        item: targetFile,
      })
    }

    message.success(`Opened ${targetFile.name}`)
    return true
  }
  else {
    message.error(`File not found: ${path}`)
    return false
  }
}

// Handler functions for the autocomplete
function handlePathSelect(value: string) {
  emit("update:modelValue", value)
  navigateToFile(value)
}

function handlePathUpdate(value: string) {
  emit("update:modelValue", value)
}

async function handlePathEnter() {
  if (currentFilePath.value === displayedFilePath.value)
    return

  pathLoading.value = true
  try {
    const success = await navigateToFile(currentFilePath.value)
    if (!success) {
      // Reset to displayed path on failure
      emit("update:modelValue", displayedFilePath.value)
    }
  }
  finally {
    pathLoading.value = false
  }
}

// Watch for changes in displayed file and update path
watch(
  () => filePreviewStore.currentPreviewFile,
  (newFile) => {
    if (newFile) {
      const newPath = newFile.path || `${rootPath.value}${newFile.name}`
      displayedFilePath.value = newPath
    }
  },
)

// Watch for changes in active editor
watch(
  [activeEditor, activeEditorId],
  () => {
    const activeFilePath = getCurrentActiveFilePath()
    if (activeFilePath) {
      displayedFilePath.value = activeFilePath
    }
  },
)

// Initialize displayed file path
watch(
  currentFilePath,
  (newPath) => {
    if (newPath && newPath !== displayedFilePath.value) {
      displayedFilePath.value = newPath
    }
  },
  { immediate: true },
)
</script>
