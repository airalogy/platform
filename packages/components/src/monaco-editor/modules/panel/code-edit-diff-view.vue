<template>
  <div
    class="code-edit-diff-view overflow-hidden border border-[var(--n-border-color)] rounded-lg"
    style="height: 360px"
    :data-view-mode="props.sideBySide ? 'side-by-side' : 'inline'"
  >
    <editor-container
      mode="diff"
      height="360px"
      :diff-options="diffOptions"
      @mount:editor="handleMount"
    />
  </div>
</template>

<script setup lang="ts">
import type * as Monaco from "monaco-editor"
import type { Raw } from "vue"
import EditorContainer from "@airalogy/components/monaco-editor/editor-container/index.vue"

const props = withDefaults(defineProps<{
  original: string
  modified: string
  language?: string
  sideBySide?: boolean
}>(), {
  language: "plaintext",
  sideBySide: false,
})

const editorRef = shallowRef<Raw<Monaco.editor.IStandaloneDiffEditor> | null>(null)
const monacoRef = shallowRef<typeof Monaco | null>(null)
const originalModel = shallowRef<Raw<Monaco.editor.ITextModel> | null>(null)
const modifiedModel = shallowRef<Raw<Monaco.editor.ITextModel> | null>(null)

const diffOptions = computed<Monaco.editor.IStandaloneDiffEditorConstructionOptions>(() => ({
  automaticLayout: true,
  enableSplitViewResizing: true,
  minimap: { enabled: false },
  originalEditable: false,
  readOnly: true,
  renderOverviewRuler: false,
  renderSideBySide: props.sideBySide,
  scrollBeyondLastLine: false,
  wordWrap: "on",
}))

function disposeModels() {
  originalModel.value?.dispose()
  modifiedModel.value?.dispose()
  originalModel.value = null
  modifiedModel.value = null
}

function createModels() {
  const editor = editorRef.value
  const monaco = monacoRef.value
  if (!editor || !monaco) {
    return
  }

  disposeModels()
  originalModel.value = markRaw(monaco.editor.createModel(props.original, props.language))
  modifiedModel.value = markRaw(monaco.editor.createModel(props.modified, props.language))
  editor.setModel({
    original: originalModel.value,
    modified: modifiedModel.value,
  })
}

function handleMount(editor: Monaco.editor.IStandaloneCodeEditor | Monaco.editor.IStandaloneDiffEditor, monaco: typeof Monaco) {
  if (!("getOriginalEditor" in editor)) {
    return
  }
  editorRef.value = markRaw(editor)
  monacoRef.value = markRaw(monaco)
  createModels()
}

watch(() => [props.original, props.modified, props.language], () => {
  createModels()
})

onBeforeUnmount(() => {
  editorRef.value?.setModel(null)
  disposeModels()
})
</script>
