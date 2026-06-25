<template>
  <div class="protocol-document__panel size-full flex flex-col p-4">
    <protocol-generator
      :generate-aimd="props.generateAimd"
      :generate-model="props.generateModel"
      :generate-assigner="props.generateAssigner"
      :extract-instruction-file="props.extractInstructionFile"
      :current-aimd-content="currentAimdContent"
      :current-model-content="currentModelContent"
      @view-content="handleViewGeneratedContent"
      @save-file="handleSaveGeneratedFile"
    />
  </div>
</template>

<script setup lang="ts">
import type { ChatModelConfig } from "@airalogy/shared"
import type * as Monaco from "monaco-editor"
import { useMessage } from "naive-ui"
import { nanoid } from "nanoid"
import { computed, nextTick } from "vue"
import { isNormalModelInfo, useActiveEditorStore, useEditorStore, useModelsStore, useSplitStore } from "../../store/editorStore"
import { addNewModel, openEditor } from "../../utils"
import ProtocolGenerator from "./protocol-generator.vue"

// Props
interface IProps {
  monaco?: ShallowRef<typeof Monaco | null>
  // API functions for protocol generation
  generateAimd?: (payload: { instruction: string, model: ChatModelConfig }, requestId?: string) => Promise<{ data: string | null, error: any }>
  generateModel?: (payload: { protocol_aimd: string, model: ChatModelConfig }, requestId?: string) => Promise<{ data: string | null, error: any }>
  generateAssigner?: (payload: { protocol_aimd: string, protocol_model: string, model: ChatModelConfig }, requestId?: string) => Promise<{ data: string | null, error: any }>
  extractInstructionFile?: (file: File) => Promise<{ data: { filename: string, text: string, was_trimmed: boolean, content_type: string } | null, error: any }>
}

const props = withDefaults(defineProps<IProps>(), {
  generateAimd: () => Promise.reject(new Error("No generateAimd function provided")),
  generateModel: () => Promise.reject(new Error("No generateModel function provided")),
  generateAssigner: () => Promise.reject(new Error("No generateAssigner function provided")),
  extractInstructionFile: undefined,
})

// Stores
const modelsStore = useModelsStore()
const splitStore = useSplitStore()
const activeEditorStore = useActiveEditorStore()
const editorStore = useEditorStore()

// UI
const message = useMessage()

// Get monaco from editor store
const { monaco } = storeToRefs(editorStore)
const { splitState } = storeToRefs(splitStore)

// Get current AIMD and Model content from editor
const currentAimdContent = computed(() => {
  // Find protocol.aimd from currently opened files
  const aimdFile = modelsStore.modelInfos.find(m =>
    isNormalModelInfo(m) && (m.name?.endsWith(".aimd") || m.path?.includes("protocol.aimd")),
  )
  return aimdFile && isNormalModelInfo(aimdFile) ? aimdFile.model?.getValue() : undefined
})

const currentModelContent = computed(() => {
  // Find model.py from currently opened files
  const modelFile = modelsStore.modelInfos.find(m =>
    isNormalModelInfo(m) && (m.name === "model.py" || m.path?.includes("model.py")),
  )
  return modelFile && isNormalModelInfo(modelFile) ? modelFile.model?.getValue() : undefined
})

// Add a split if needed
function addSplit() {
  const { addSplit: addEditorSplit } = splitStore
  addEditorSplit()
}

// Handle viewing generated content
function handleViewGeneratedContent(content: string, filename: string, language: string) {
  if (!monaco.value) {
    message.error("Editor not initialized")
    return
  }

  try {
    // Create a temporary file to view the content
    const fileId = `temp-${nanoid()}`
    const modelInfo = addNewModel({
      monaco: monaco.value,
      content,
      id: fileId,
      name: filename,
      language,
      path: filename,
    })

    if (!modelInfo) {
      message.error("Failed to create temporary file")
      return
    }

    // Add to model store
    modelsStore.addModelInfo(modelInfo)

    // Open in editor
    if (!splitState.value.some(Boolean)) {
      addSplit()
      nextTick(() => {
        openEditor(activeEditorStore.activeEditorId, monaco.value, modelInfo)
      })
    }
    else {
      openEditor(activeEditorStore.activeEditorId, monaco.value, modelInfo)
    }

    message.success(`Opened ${filename} for viewing`)
  }
  catch (error) {
    console.error("Error viewing content:", error)
    message.error("Failed to open file for viewing")
  }
}

// Handle saving generated file
async function handleSaveGeneratedFile(content: string, filename: string, language: string) {
  if (!monaco.value) {
    message.error("Editor not initialized")
    return
  }

  try {
    // Determine the file path based on filename
    let targetPath = filename
    if (filename === "protocol.aimd") {
      targetPath = "protocol.aimd"
    }
    else if (filename === "model.py") {
      targetPath = "model.py"
    }
    else if (filename === "assigner.py") {
      targetPath = "assigner.py"
    }

    // Check if file already exists
    const existingModel = modelsStore.modelInfos.find(m =>
      isNormalModelInfo(m) && (m.name === filename || m.path === targetPath),
    )

    if (existingModel && isNormalModelInfo(existingModel)) {
      // Update existing file
      existingModel.model?.setValue(content)
      modelsStore.setModelDirty(existingModel.id, true)
      message.success(`Updated ${filename}`)
    }
    else {
      // Create new file
      const fileId = nanoid()
      const modelInfo = addNewModel({
        monaco: monaco.value,
        content,
        id: fileId,
        name: filename,
        language,
        path: targetPath,
      })

      if (!modelInfo) {
        message.error("Failed to create file")
        return
      }

      // Add to model store
      modelsStore.addModelInfo(modelInfo)

      // Open in editor
      if (!splitState.value.some(Boolean)) {
        addSplit()
        await nextTick()
      }

      await openEditor(activeEditorStore.activeEditorId, monaco.value, modelInfo)

      message.success(`Created and opened ${filename}`)
    }
  }
  catch (error) {
    console.error("Error saving file:", error)
    message.error("Failed to save file")
  }
}
</script>

<style lang="sass" scoped>
.protocol-document__panel
  background-color: var(--n-color)
</style>
