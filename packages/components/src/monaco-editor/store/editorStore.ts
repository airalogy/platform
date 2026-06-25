import type { PiniaStore } from "@airalogy/shared/types"
import type * as Monaco from "monaco-editor"
import type { Raw } from "vue"
import { defineStore } from "pinia"
import { computed, markRaw, ref, toRaw, watch } from "vue"
import { isDiffEditor, isDiffEditorModel, isTextEditorModel, writeFile } from "../utils"

export interface ModelInfoBase {
  name: string
  language: string
  content: string
  id: string
  path?: string
  options?: Partial<Monaco.editor.IEditorOptions>
}

export interface ModelInfoExtra {
  model: Monaco.editor.ITextModel
  usedBy: number[]
  isDirty?: boolean
  lastSavedVersionId: number
}

export interface ModelInfo extends ModelInfoBase, ModelInfoExtra {
  type: "normal"
}

export interface DiffModelInfo extends ModelInfoBase {
  source: Monaco.editor.ITextModel
  target: Monaco.editor.ITextModel
  type: "diff"
  diffOptions?: Partial<Monaco.editor.IDiffEditorOptions>
}

export function isDiffModelInfo(modelInfo: Partial<ModelInfo | DiffModelInfo>): modelInfo is DiffModelInfo {
  return modelInfo.type === "diff"
}

export function isNormalModelInfo(modelInfo: Partial<ModelInfo | DiffModelInfo>): modelInfo is ModelInfo {
  return modelInfo.type === "normal"
}

export const useModelsStore = defineStore("models", () => {
  const modelInfos = ref<(ModelInfo | DiffModelInfo)[]>([])
  const activeMap = ref<Map<number, string>>(new Map())

  // eslint-disable-next-line ts/no-use-before-define
  const editorStore = useEditorStore()

  function updateUsedEditorModel(modelInfo: ModelInfo) {
    const { usedBy } = modelInfo
    const rawModel = toRaw(modelInfo.model)
    modelInfo.model = rawModel

    if (usedBy?.length) {
      usedBy.forEach((editorId) => {
        const editorInfo = editorStore.getEditorInfo(editorId)
        if (editorInfo && !isDiffEditor(editorInfo.editor)) {
          editorInfo.editor.setModel(rawModel)
        }
      })
    }
  }

  function addModelInfo(modelInfo: ModelInfo | DiffModelInfo) {
    if (!modelInfo || typeof modelInfo !== "object" || !modelInfo.name) {
      return null
    }

    const existingModel = getModelInfo(modelInfo.id, "normal")
    if (existingModel && isNormalModelInfo(modelInfo)) {
      updateUsedEditorModel(existingModel)
      return existingModel
    }

    modelInfos.value.push(modelInfo)

    return modelInfo
  }

  function setModels(modelInfo: CommonType.MakePartial<ModelInfo, "model">, model: Monaco.editor.ITextModel | Monaco.editor.IDiffEditorModel, editorId?: number): ModelInfo | null {
    if (!modelInfo || typeof modelInfo !== "object" || !modelInfo.name) {
      return null
    }

    if (isDiffEditorModel(model)) {
      return null
    }

    const currModelInfo = initModelInfo(modelInfo, editorId, model)

    return currModelInfo as ModelInfo
  }

  function removeModelById(id: string, editorId: number): ModelInfo | DiffModelInfo | null {
    const existingModelInfo = getModelInfo(id, "normal")
    if (!existingModelInfo) {
      return null
    }

    return removeModel(existingModelInfo, editorId)
  }

  function removeModel(modelInfo: ModelInfo | DiffModelInfo, editorId: number): ModelInfo | DiffModelInfo | null {
    if (isNormalModelInfo(modelInfo) && modelInfo.usedBy.includes(editorId)) {
      modelInfo.usedBy = modelInfo.usedBy.filter(eid => eid !== editorId)

      if (modelInfo.usedBy.length === 0) {
        if (!modelInfos.value.find(info => isDiffModelInfo(info) && info.source.id === modelInfo.model.id)) {
          toRaw(modelInfo.model).dispose()
        }

        modelInfos.value = modelInfos.value.filter(model => model.id !== modelInfo.id)
      }
    }
    else if (isDiffModelInfo(modelInfo)) {
      const editorInfo = editorStore.getEditorInfo(editorId)
      // Fix: TextModel got disposed before DiffEditorWidget model got reset
      // We need to reset the model on the diff editor before disposing the models
      if (editorInfo && isDiffEditor(editorInfo.editor)) {
        editorInfo.editor.setModel(null)
      }

      // Only dispose the models after we've reset the editor's model
      const { source, target } = modelInfo

      // Check if the source model is used by other editors before disposing
      const sourceIsUsedElsewhere = modelInfos.value.some(
        info => isNormalModelInfo(info) && info.model.id === source.id && info.usedBy.length > 0,
      )

      if (!sourceIsUsedElsewhere && !source.isDisposed()) {
        source.dispose()
      }

      if (!target.isDisposed()) {
        target.dispose()
      }

      modelInfos.value = modelInfos.value.filter(model => model.id !== modelInfo.id)
    }

    return modelInfos.value.findLast((info) => {
      if (isDiffModelInfo(info)) {
        return true
      }

      return info.usedBy.includes(editorId)
    }) || null
  }

  function removeAllModels() {
    modelInfos.value.forEach((modelInfo) => {
      if (isDiffModelInfo(modelInfo)) {
        modelInfo.source.dispose()
        modelInfo.target.dispose()
      }
      else if (!modelInfo.model?.isDisposed()) {
        modelInfo.model.dispose()
      }
    })

    modelInfos.value = []
  }

  function removeAllEditorModels(editorId: number) {
    modelInfos.value = modelInfos.value
      .map((model) => {
        if (isDiffModelInfo(model)) {
          return null
        }
        if (model.usedBy.includes(editorId)) {
          const newUsedBy = model.usedBy.filter(id => id !== editorId)
          if (newUsedBy.length === 0) {
            model.model.dispose()
            return null
          }
          return {
            ...model,
            usedBy: newUsedBy,
          }
        }
        return model
      })
      .filter((model): model is ModelInfo => model !== null)
  }

  function getReactiveModelInfo(id: string): ModelInfo | DiffModelInfo | null {
    return modelInfos.value.find(model => model.id === id) || null
  }
  function getRawModelInfo(id: string): ModelInfo | DiffModelInfo | null {
    const info = getReactiveModelInfo(id)
    if (!info) {
      return null
    }

    return toRaw(info)
  }

  function getModelInfo(id: string): ModelInfo | DiffModelInfo | null

  function getModelInfo<T extends "normal" | "diff" | "all">(id: string, type: T, raw?: boolean): (T extends "normal" ? ModelInfo : DiffModelInfo) | null
  function getModelInfo<T extends "normal" | "diff" | "all">(id: string, type?: T, raw?: boolean): ModelInfo | DiffModelInfo | null {
    const info = raw ? getRawModelInfo(id) : getReactiveModelInfo(id)
    if (info && type) {
      if (type === "diff" && isDiffModelInfo(info)) {
        return info
      }

      if (type === "normal" && isNormalModelInfo(info)) {
        return info
      }
    }

    return info || null
  }

  function setModelDirty(id: string, isDirty: boolean = true) {
    const model = getModelInfo(id, "normal")
    if (model) {
      model.isDirty = isDirty
    }
  }

  function saveModelInfoById(id: string, webContainerInstance?: any, updateFileDataFn?: (id: string, value: Partial<any>) => void) {
    const modelInfo = getModelInfo(id, "normal")

    if (!modelInfo) {
      return
    }

    saveModelInfo(modelInfo, webContainerInstance, updateFileDataFn)
  }

  function saveModelInfo(modelInfo: ModelInfo, webContainerInstance?: any, updateFileDataFn?: (id: string, value: Partial<any>) => void) {
    if (!modelInfo || !modelInfo.isDirty) {
      return
    }

    const { id, name: filename, model, path } = modelInfo
    const content = toRaw(model).getValue()

    // Update file value in file data if updateFileDataFn is provided
    if (updateFileDataFn && id) {
      updateFileDataFn(id, { value: content, filename })
    }

    // Write to web container if path and webContainerInstance provided
    if (path && webContainerInstance) {
      try {
        writeFile(path!, content, webContainerInstance)
      }
      catch (error) {
        console.error(`Error saving file ${path}:`, error)
      }
    }

    // Reset dirty flag and lastSavedVersionId
    modelInfo.isDirty = false
    modelInfo.lastSavedVersionId = toRaw(model).getAlternativeVersionId()
    modelInfo.content = content
    updateUsedEditorModel(modelInfo)

    return content
  }
  function setActiveModelInfo(modelInfo: ModelInfo | DiffModelInfo, editorId: number, init = true) {
    if (init) {
      initModelInfo(modelInfo, editorId)
    }

    // Set in activeMap
    activeMap.value.set(editorId, modelInfo.id)
  }

  function initModelInfo<T extends CommonType.MakePartial<ModelInfo, "model"> | DiffModelInfo, K = T extends DiffModelInfo ? Monaco.editor.IDiffEditorModel : Monaco.editor.ITextModel >(modelInfo: T, editorId?: number, model?: Raw<K>) {
    const existingModelInfo = getModelInfo(modelInfo.id)

    const hasTargetEditor = typeof editorId === "number"
    if (existingModelInfo) {
      if (hasTargetEditor && isNormalModelInfo(existingModelInfo)) {
        if (!existingModelInfo.usedBy) {
          existingModelInfo.usedBy = hasTargetEditor ? [editorId] : []
        }
        else if (!existingModelInfo.usedBy.includes(editorId)) {
          existingModelInfo.usedBy.push(editorId)
        }
      }

      return existingModelInfo
    }

    if (isDiffModelInfo(modelInfo)) {
      modelInfos.value.push(modelInfo)
      return modelInfo
    }

    const modelToAdd = isTextEditorModel(model)
      ? model
      : modelInfo.model
        ? markRaw(toRaw(modelInfo.model))
        : null

    const modelInfoToAdd = (modelToAdd
      ? {
          ...modelInfo,
          model: modelToAdd,
          // usedBy: [editorId], // Initialize with this editor
          lastSavedVersionId: modelToAdd.getAlternativeVersionId(),
          type: "normal",
        }
      : modelInfo) as ModelInfo

    if (hasTargetEditor) {
      if (!modelInfoToAdd.usedBy) {
        modelInfoToAdd.usedBy = hasTargetEditor ? [editorId] : []
      }
      else if (!modelInfoToAdd.usedBy.includes(editorId)) {
        modelInfoToAdd.usedBy.push(editorId)
      }
    }

    // Add to modelInfos
    modelInfos.value.push(modelInfoToAdd)

    return modelInfoToAdd
  }

  function clearActiveModelInfo(editorId: number) {
    activeMap.value.delete(editorId)
  }

  function clearAllActiveModelInfo() {
    activeMap.value.clear()
  }

  function getActiveModelInfo(editorId: number): ModelInfo | DiffModelInfo | null
  function getActiveModelInfo<T extends "normal" | "diff" | "all">(editorId: number, type: T, raw?: boolean): (T extends "normal" ? ModelInfo : T extends "diff" ? DiffModelInfo : ModelInfo | DiffModelInfo) | null
  function getActiveModelInfo(editorId: number, type?: "normal" | "diff" | "all", raw?: boolean): ModelInfo | DiffModelInfo | null {
    const modelId = activeMap.value.get(editorId)
    if (!modelId)
      return null

    const modelInfo = type ? getModelInfo(modelId, type, raw) : getModelInfo(modelId, "all", raw)

    return modelInfo
  }

  watch(() => editorStore.editorMap, (editorMap) => {
    modelInfos.value.forEach((it) => {
      if (isNormalModelInfo(it)) {
        it.usedBy = it.usedBy.filter(editorId => editorMap.has(editorId))
      }
    })
  }, { flush: "post" })
  return {
    modelInfos,
    activeMap,
    addModelInfo,
    setModels,
    removeModelById,
    removeModel,
    removeAllModels,
    removeAllEditorModels,
    getModelInfo,
    setModelDirty,
    saveModelInfoById,
    saveModelInfo,
    updateUsedEditorModel,
    setActiveModelInfo,
    clearActiveModelInfo,
    getActiveModelInfo,
    clearAllActiveModelInfo,
  }
})

export type ModelStore = PiniaStore<typeof useModelsStore>

export type EditorType = Monaco.editor.IStandaloneCodeEditor | Monaco.editor.IStandaloneDiffEditor

export interface EditorInfo<T extends "normal" | "diff" | "all" = "all"> {
  editor: T extends "normal" ? Monaco.editor.IStandaloneCodeEditor : T extends "diff" ? Monaco.editor.IStandaloneDiffEditor : EditorType
  id: number
}

export const useEditorStore = defineStore("editor", () => {
  const modelsStore = useModelsStore()

  const editorMap = ref<Map<number, EditorInfo>>(new Map())

  // function setMonaco(index: number, monaco: typeof Monaco) {
  //   monacos.value[index] = monaco
  // }

  // function getMonaco(index: number): typeof Monaco | null {
  //   return toRaw(monacos.value[index]) || null
  // }

  function setEditorInfo(index: number, editor: EditorType) {
    editorMap.value.set(index, { editor: markRaw(toRaw(editor)), id: index })
  }

  function getEditorInfo(index: number): EditorInfo | null {
    return toRaw(editorMap.value.get(index)) || null
  }

  function removeEditor(index: number) {
    const info = editorMap.value.get(index)
    if (info) {
      const { editor } = info
      try {
        // First check the model
        const model = editor.getModel()

        if (model) {
          if (isDiffEditorModel(model)) {
            return
          }

          // Get model URI
          const modelUri = model.uri.toString()

          // Get access to models store
          const allModels = modelsStore.modelInfos

          // Find the model in our models store to check its usedBy array
          const modelEntry = Object.values(allModels).find((m: ModelInfo | DiffModelInfo): m is ModelInfo => {
            if (isDiffModelInfo(m)) {
              return false
            }

            return m.model && m.model.uri && m.model.uri.toString() === modelUri
          })

          if (modelEntry) {
            // Remove this editor from the usedBy array
            modelEntry.usedBy = modelEntry.usedBy.filter((id: number) => id !== index)

            // Only dispose the model if no editor is using it anymore
            if (modelEntry.usedBy.length === 0) {
              // Now dispose the model properly
              console.log(`Disposing model ${modelUri} as it's no longer used`)
              model.dispose()
            }
            else {
              console.log(`Not disposing model ${modelUri} as it's still used by editors: ${modelEntry.usedBy.join(", ")}`)
            }
          }
          else {
            // If model isn't tracked in our store, we can dispose it
            model.dispose()
          }
        }

        // Then dispose the editor
        editor.dispose()
      }
      catch (error) {
        console.error(`Error disposing editor ${index}:`, error)
      }
    }
    // Finally set the reference to null
    editorMap.value.delete(index)
  }

  function removeAllEditors() {
    editorMap.value.forEach((info) => {
      const { editor } = info
      if (editor) {
        editor.dispose()
      }
    })

    editorMap.value.clear()
  }

  function getTargetEditor<T extends "normal" | "diff">(type: T): EditorInfo<T>[]
  function getTargetEditor<T extends "normal" | "diff">(type: T, method: "first"): EditorInfo<T> | null
  function getTargetEditor<T extends "normal" | "diff">(type: T, method: "all"): EditorInfo<T>[]
  function getTargetEditor<T extends "normal" | "diff">(type: T, method = "all"): EditorInfo<T> | EditorInfo<T>[] | null {
    const sortedList = Array.from(editorMap.value.values()).sort((a, b) => a.id - b.id)
    const predicate = type === "normal" ? (info: EditorInfo) => !isDiffEditor(info.editor) : (info: EditorInfo) => isDiffEditor(info.editor)

    if (method === "first") {
      return (sortedList.find(predicate) || null) as EditorInfo<T> | null
    }

    return sortedList.filter(predicate) as EditorInfo<T>[]
  }

  function getFirstNormalEditor() {
    return toRaw(getTargetEditor<"normal">("normal", "first"))
  }
  function getFirstDiffEditor() {
    return toRaw(getTargetEditor<"diff">("diff", "first"))
  }

  return {
    editorMap,
    setEditorInfo,
    getEditorInfo,
    removeEditor,
    removeAllEditors,
    getFirstDiffEditor,
    getFirstNormalEditor,
  }
})

export type EditorStore = PiniaStore<typeof useEditorStore>

export const useActiveEditorStore = defineStore("activeEditor", () => {
  const activeEditor = ref<EditorType | null>(null)
  const activeEditorId = ref<number>(-1)

  function setActiveEditor(editor: EditorType, index: number) {
    activeEditor.value = editor
    activeEditorId.value = index
  }

  return {
    activeEditor,
    activeEditorId,
    setActiveEditor,
  }
})

export type ActiveEditorStore = PiniaStore<typeof useActiveEditorStore>

const MIN_MENU_SIDEBAR_SIZE = 48
const MIN_MENU_PANE_SIZE = 240
const MIN_MENU_SPLIT_SIZE = MIN_MENU_SIDEBAR_SIZE + MIN_MENU_PANE_SIZE
const START_COLLAPSED_SIZE = MIN_MENU_SPLIT_SIZE - 100
const UNIT = "px"
export const DEFAULT_MENU_MIN_SPLIT_SIZE = `${MIN_MENU_SPLIT_SIZE}${UNIT}`
export const DEFAULT_MENU_COLLAPSED_SIZE = `${MIN_MENU_SIDEBAR_SIZE}${UNIT}`

export const useSplitStore = defineStore("editor-split", () => {
  // Get editor function from useEditorStore
  const { getEditorInfo } = useEditorStore()
  const activeEditorStore = useActiveEditorStore()

  const menuSplitSize = ref(DEFAULT_MENU_COLLAPSED_SIZE)
  const lastMenuSplitSize = ref<string | null>(null)
  const lastOpenedMenu = ref<string | null>(null)
  const activeMenu = ref<string | undefined>()
  const isMenuCollapsed = ref(true)

  const splitState = ref<boolean[]>([false, false, false])
  const currentSplitSize = computed(() => splitState.value.filter(Boolean).length)
  const customMenuSizeState = ref<Record<"minSplitSize" | "collapseThreshold", number> | null>(null)

  // Using custom menu size thresholds from customMenuSizeState
  const minSplitSize = computed(() => customMenuSizeState.value?.minSplitSize || MIN_MENU_SPLIT_SIZE)
  const collapseThreshold = computed(() => customMenuSizeState.value?.collapseThreshold || START_COLLAPSED_SIZE)

  function addSplit() {
    const index = splitState.value.findIndex(s => s === false)
    if (index === -1) {
      return -1
    }

    // Current active editor information
    const activeEditor = activeEditorStore.activeEditor
    const activeEditorId = activeEditorStore.activeEditorId

    // Check if we have a valid active editor with a model
    const activeEditorModel = activeEditor?.getModel()
    const hasValidActiveEditor = activeEditorId >= 0 && activeEditorModel && !isDiffEditorModel(activeEditorModel) && !activeEditorModel.isDisposed()

    // Now enable the split first
    splitState.value[index] = true

    // Before working with the new split, ensure any existing editor doesn't have a disposed model
    const editorInfo = getEditorInfo(index)
    if (editorInfo) {
      try {
        const currentModel = editorInfo.editor.getModel()
        if (currentModel && !isDiffEditorModel(currentModel) && currentModel.isDisposed()) {
          // If we have a disposed model, remove it to prevent errors
          console.warn(`Found disposed model in editor ${index}, removing it`)
          editorInfo.editor.setModel(null)
        }
      }
      catch (error) {
        console.error(`Error checking model state for editor ${index}:`, error)
      }
    }

    // We're enabling the split and getting it ready for model duplication
    // The actual model duplication will happen in the editor.vue component's handleEditorDidMount
    // where it checks for a newly created split

    // Find valid editors to set one as active (if no active editor exists)
    if (!hasValidActiveEditor) {
      // Look for the nearest valid editor to set as active
      for (let i = 0; i < splitState.value.length; i++) {
        if (i !== index && splitState.value[i]) {
          const nearEditor = getEditorInfo(i)
          const nearEditorModel = nearEditor?.editor.getModel()
          if (nearEditor && !isDiffEditorModel(nearEditorModel) && !nearEditorModel?.isDisposed()) {
            // Found a valid editor, set it as active
            console.log(`Setting editor ${i} as active for new split`)
            activeEditorStore.setActiveEditor(nearEditor.editor as EditorType, i)
            break
          }
        }
      }
    }

    return index
  }

  function addDiffSplit() {
    const index = splitState.value.findIndex(s => s === true)
    if (index === -1) {
      splitState.value[0] = true
      return 0
    }

    return index
  }

  function removeSplit(index: number) {
    if (index >= 0 && index < splitState.value.length)
      splitState.value[index] = false
  }

  function clearSplit() {
    splitState.value = splitState.value.map(() => false)
  }

  function handleUpdateSize(val: string) {
    if (val === DEFAULT_MENU_MIN_SPLIT_SIZE || val === DEFAULT_MENU_COLLAPSED_SIZE) {
      return
    }

    const size = Number.parseFloat(val)

    if (customMenuSizeState.value) {
      if (size === minSplitSize.value || size === collapseThreshold.value) {
        return
      }
    }

    if (size < minSplitSize.value) {
      if (isMenuCollapsed.value || size > collapseThreshold.value) {
        return
      }

      menuSplitSize.value = `${minSplitSize.value}${UNIT}`
      isMenuCollapsed.value = true
      activeMenu.value = undefined
    }
    else {
      isMenuCollapsed.value = false
      if (!activeMenu.value) {
        activeMenu.value = lastOpenedMenu.value || "file"
        menuSplitSize.value = `${minSplitSize.value}${UNIT}`
      }
      menuSplitSize.value = val
    }
  }

  watch(activeMenu, (val, prevVal) => {
    if (val && !prevVal) {
      if (customMenuSizeState.value) {
        menuSplitSize.value = `${minSplitSize.value}${UNIT}`
      }
      else {
        if (lastMenuSplitSize.value && lastMenuSplitSize.value !== DEFAULT_MENU_MIN_SPLIT_SIZE) {
          menuSplitSize.value = lastMenuSplitSize.value
        }
        else {
          menuSplitSize.value = `${minSplitSize.value}${UNIT}`
        }
      }
      lastMenuSplitSize.value = null
      lastOpenedMenu.value = null
      isMenuCollapsed.value = false
    }
    else if (!val && prevVal) {
      lastMenuSplitSize.value = menuSplitSize.value
      lastOpenedMenu.value = prevVal
      menuSplitSize.value = DEFAULT_MENU_COLLAPSED_SIZE
      isMenuCollapsed.value = true
    }
    else if (customMenuSizeState.value) {
      menuSplitSize.value = `${minSplitSize.value}${UNIT}`
    }
  })

  return {
    splitState,
    activeMenu,
    menuSplitSize,
    isMenuCollapsed,
    addSplit,
    addDiffSplit,
    removeSplit,
    clearSplit,
    handleUpdateSize,
    currentSplitSize,
    customMenuSizeState,
  }
})
