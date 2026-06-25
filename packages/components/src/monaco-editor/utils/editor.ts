import type * as Monaco from "monaco-editor"
import type { Ref } from "vue"

import type { ActiveEditorStore, DiffModelInfo, EditorStore, EditorType, ModelInfo, ModelStore } from "../store/editorStore"
import type { FileSystemItem } from "../types"
import { assert, getFileLanguage } from "@airalogy/shared/utils"
import { isDiffModelInfo } from "../store/editorStore"
import { isFile } from "./filesystem"

export function setModelsFromInfo(
  modelsInfo: ModelInfo[],
  monaco: typeof Monaco,
  editor: Monaco.editor.IStandaloneCodeEditor,
  setModels: ModelStore["setModels"],
  setActiveModelInfo: ModelStore["setActiveModelInfo"],
  editorId: number,
) {
  modelsInfo.forEach((modelInfo) => {
    addNewModel(modelInfo, monaco, editor, setModels, setActiveModelInfo, editorId)
  })
}

export function addNewModel(
  modelInfo: Partial<ModelInfo | DiffModelInfo> & { type: "normal" | "diff", id: string },
  monaco: typeof Monaco,
  editor: Monaco.editor.IStandaloneCodeEditor | Monaco.editor.IStandaloneDiffEditor,
  setModels: ModelStore["setModels"],
  setActiveModelInfo: ModelStore["setActiveModelInfo"],
  editorId: number,
) {
  if (isDiffModelInfo(modelInfo) || isDiffEditor(editor)) {
    return
  }

  const { content: value, language, id } = modelInfo
  const model = getOrCreateNormalModel(monaco, value || "", language || "", id || "")

  setActiveModelInfo({ isDirty: false, ...modelInfo, model } as ModelInfo, editorId)
  // setModels(modelInfo as ModelInfo, model, editorId, modelInfo.id)
  editor.setModel(model)

  return model
}

export function getOrCreateNormalModel(monaco: typeof Monaco, value: string, language: string, path: string) {
  return markRaw(toRaw(getModel(monaco, path) || createModel(monaco, value, language, path)))
}

export function getModel(monaco: typeof Monaco, path: string) {
  return monaco.editor.getModel(createModelUri(monaco, path))
}

export function createModel(monaco: typeof Monaco, value: string, language?: string, path?: string) {
  return monaco.editor.createModel(
    value,
    language,
    path ? createModelUri(monaco, path) : undefined,
  )
}

export function createModelUri(monaco: typeof Monaco, path: string) {
  return monaco.Uri.parse(path)
}

export async function openEditor(payload: {
  activeEditor: Ref<EditorType | null>
  activeEditorId: Ref<number>
  splitState: Ref<boolean[]>
  id: string
  item: FileSystemItem
  monaco: typeof Monaco
  getEditorInfo: EditorStore["getEditorInfo"]
  getModelInfo: ModelStore["getModelInfo"]
  setActiveEditor: ActiveEditorStore["setActiveEditor"]
  addSplit: () => number
  setActiveModelInfo: ModelStore["setActiveModelInfo"]
  setModels: ModelStore["setModels"]
  // openFilePreview?: (fileInfo: any) => void
}) {
  const { activeEditor, activeEditorId, splitState, getEditorInfo, getModelInfo, setActiveEditor, addSplit, id, item, setActiveModelInfo, setModels, monaco } = payload

  if (!monaco || !isFile(item)) {
    return
  }

  const willChangeEditorId = activeEditor.value ? activeEditorId.value : splitState.value.findIndex(Boolean)
  const willChangeEditorInfo = getEditorInfo(willChangeEditorId)

  const matchModel = getModelInfo(id, "normal")

  if (matchModel && matchModel.model) {
    setActiveModelInfo(matchModel, willChangeEditorId)
    if (willChangeEditorInfo) {
      if (isDiffEditor(willChangeEditorInfo.editor)) {
        return
      }
      willChangeEditorInfo.editor.setModel(toRaw(matchModel.model))
      return
    }
  }

  if (willChangeEditorInfo) {
    if (item.content) {
      assert(typeof item.content === "string")
    }
    addNewModel(
      {
        ...item,
        language: getFileLanguage(item.name),
        content: item.content || "",
        type: "normal",
      },
      monaco,
      willChangeEditorInfo.editor,
      setModels,
      setActiveModelInfo,
      willChangeEditorId,
    )
  }
  else {
    await addSplit()

    await new Promise((resolve) => {
      const unwatch = watch(() => getEditorInfo(0)?.editor, (newEditor) => {
        if (newEditor) {
          const editor = toRaw(newEditor)
          unwatch() // Stop watching once we get the editor
          setActiveEditor(editor, 0)
          if (item.content) {
            assert(typeof item.content === "string")
          }

          addNewModel(
            {
              ...item,
              language: getFileLanguage(item.name),
              content: item.content || "",
              type: "normal",
            },
            monaco,
            editor,
            setModels,
            setActiveModelInfo,
            0,
          )

          resolve(true)
        }
        else {
          resolve(false)
        }
      }, { immediate: true })
    })
  }
}

export function isCodeEditor(editor: EditorType): editor is Monaco.editor.IStandaloneCodeEditor {
  // Diff editor has getOriginalEditor method, code editor doesn't
  return !("getOriginalEditor" in editor)
}

export function isDiffEditor(editor: Monaco.editor.IStandaloneCodeEditor | Monaco.editor.IStandaloneDiffEditor): editor is Monaco.editor.IStandaloneDiffEditor {
  // Diff editor has getOriginalEditor method
  return "getOriginalEditor" in editor
}

export function isDiffEditorModel(model: any): model is Monaco.editor.IDiffEditorModel {
  return Boolean(model && (model as unknown as Monaco.editor.IDiffEditorModel).original)
}

export function isTextEditorModel(model: any): model is Monaco.editor.ITextModel {
  return !isDiffEditorModel(model)
}
