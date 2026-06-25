<template>
  <div
    :dir="direction"
    class="group relative w-full flex items-center justify-between p-[0.5px] pr-1 text-sm duration-200 ease-in-out hover:bg-[#3c4453]/60 rtl:pl-1 rtl:pr-0"
    :class="[
      {
        'bg-[#3c4453]': isSelected && isSelectable,
        'cursor-pointer': isSelectable,
        'opacity-50 cursor-not-allowed': !isSelectable,
      },
    ]"
    @click="handleFileItemClick"
    @mouseup="onMouseupFn && onMouseupFn()"
    @mousedown="handleMouseDown"
  >
    <div class="flex items-center gap-1">
      <!-- <img
        class="h-[14px] w-[14px]"
        :src="`/images/fileIcon/${getFileSpecificIcon(file.filename)}.svg`"
        alt=""
      > -->
      <!-- <n-icon :component="getFileSpecificIcon(props.file.filename)" /> -->
      <span
        ref="dragRef"
        class="overflow-ellipsis cursor-pointer overflow-hidden whitespace-nowrap"
      >{{ file.name }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type * as Monaco from "monaco-editor"
import type { ModelInfo } from "../../../store/editorStore"
import type { TreeViewElement } from "../types"
import { arrayBufferToString, getFileLanguage, shouldPreviewFile } from "@airalogy/shared/utils"
import { storeToRefs } from "pinia"
import { useDragIconStore } from "../../../store/dragIconStore"
import { useActiveEditorStore, useEditorStore, useModelsStore, useSplitStore } from "../../../store/editorStore"
import { useFilePreviewStore } from "../../../store/filePreviewStore"
import { useUploadFileDataStore } from "../../../store/uploadFileDataStore"
import { useWebContainerStore } from "../../../store/webContainerStore"
import { addNewModel, isDiffEditor, isFile } from "../../../utils"
import { useTreeContext } from "../composables/useTreeContext"

interface Props {
  file: TreeViewElement
  isSelectable?: boolean
  isSelect?: boolean
  onMouseupFn?: () => void
}

const props = withDefaults(defineProps<Props>(), {
  isSelectable: true,
})

// Tree context
const { direction, selectedId } = useTreeContext()
const isSelected = computed(() => props.isSelect ?? selectedId.value === props.file.id)

// Store refs
const webContainerStore = useWebContainerStore()
const uploadFileDataStore = useUploadFileDataStore()
const modelsStore = useModelsStore()
const activeEditorStore = useActiveEditorStore()
const editorStore = useEditorStore()
const dragIconStore = useDragIconStore()
const splitStore = useSplitStore()

const { setActiveModelInfo } = modelsStore

const { webContainerInstance } = storeToRefs(webContainerStore)
const { modelInfos } = storeToRefs(modelsStore)
const { activeEditorId } = storeToRefs(activeEditorStore)
const { editorMap } = storeToRefs(editorStore)
const { dragIconRef } = storeToRefs(dragIconStore)
const { activeEditor } = storeToRefs(activeEditorStore)
const { splitState } = storeToRefs(splitStore)

const { getModelInfo, setModels } = modelsStore

// Editor state
const { getFirstNormalEditor } = editorStore
// const keepedEditorCount = computed(() => splitState.value.filter((item: boolean) => item).length)
const monaco = injectLocal("monaco", shallowRef<typeof Monaco | null>(null))

// Click position for drag
const clickClient = ref({ x: 0, y: 0 })
const dragRef = ref<HTMLElement>()

// Methods
async function handleFileItemClick() {
  if (!isFile(props.file)) {
    return
  }
  // Import the file type utilities
  // Check if this file should be previewed
  if (shouldPreviewFile(props.file.name)) {
    const filePreviewStore = useFilePreviewStore()
    filePreviewStore.openFilePreview(props.file)
    return
  }

  // Original Monaco editor logic for text files
  let willChangeEditor: Monaco.editor.IStandaloneCodeEditor | null = null
  let willChangeEditorId = activeEditorId.value

  if (activeEditor.value) {
    if (isDiffEditor(activeEditor.value)) {
      const firstNormalEditor = getFirstNormalEditor()
      if (firstNormalEditor) {
        willChangeEditorId = firstNormalEditor.id
        willChangeEditor = firstNormalEditor.editor
      }
    }
    else {
      willChangeEditorId = activeEditorId.value
      willChangeEditor = activeEditor.value
    }
  }

  if (!willChangeEditor) {
    return
  }

  const matchModel = getModelInfo(props.file.id, "normal")
  if (matchModel) {
    if (matchModel.model) {
      setActiveModelInfo(matchModel, willChangeEditorId)
      setModels(
        {
          name: matchModel.name,
          content: "",
          language: getFileLanguage(matchModel.name),
          id: props.file.id,
          type: "normal",
          usedBy: [willChangeEditorId],
          lastSavedVersionId: matchModel.model.getAlternativeVersionId(),
        } as ModelInfo,
        matchModel.model,
        willChangeEditorId,
      )
      willChangeEditor.setModel(matchModel.model)
    }
  }
  else {
    const content = props.file.content && typeof props.file.content !== "string" ? arrayBufferToString(props.file.content) : props.file.content || ""
    addNewModel(
      {
        ...props.file,
        language: getFileLanguage(props.file.name),
        content,
        type: "normal",
      },
      monaco.value as typeof Monaco,
      willChangeEditor as Monaco.editor.IStandaloneCodeEditor,
      modelsStore.setModels,
      setActiveModelInfo,
      willChangeEditorId,
    )
  }
}
function handleMouseDown(e: MouseEvent) {
  clickClient.value = {
    x: e.clientX,
    y: e.clientY,
  }
}

const observer = ref<MutationObserver | null>(null)
// Watch drag position
watch(
  () => dragRef.value,
  (newRef) => {
    if (newRef) {
      observer.value = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
          if (mutation.type === "attributes" && mutation.attributeName === "style") {
            const transform = window.getComputedStyle(newRef).transform
            if (transform && transform !== "none") {
              const matrix = new DOMMatrix(transform)
              if (matrix.m41 > 10 && matrix.m42 > 10 && dragIconRef.value?.element) {
                dragIconRef.value.element.style.display = "block"
                dragIconRef.value.element.style.left = `${matrix.m41 + clickClient.value.x + 5}px`
                dragIconRef.value.element.style.top = `${matrix.m42 + clickClient.value.y + 5}px`
                dragIconRef.value.element.innerHTML = props.file.name
              }
            }
          }
        })
      })

      observer.value?.observe(newRef, { attributes: true })
    }
  },
)

onUnmounted(() => {
  observer.value?.disconnect()
})
</script>
