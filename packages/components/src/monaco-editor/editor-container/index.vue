<template>
  <n-spin :show="!isEditorReady" content-class="size-full">
    <template #description>
      {{ loading }}
    </template>
    <div ref="containerRef" :style="{ width: '100%', height: '100%', display: isEditorReady ? 'block' : 'none' }" />
  </n-spin>
</template>

<script setup lang="ts">
import type * as Monaco from "monaco-editor"
import type { Raw, ShallowRef } from "vue"

import { getOrCreateNormalModel, isDiffEditor, isDiffEditorModel } from "@airalogy/components/monaco-editor/utils"

interface EditorProps {
  defaultValue?: string
  defaultLanguage?: string
  defaultPath?: string
  value?: string
  language?: string
  path?: string
  theme?: string
  line?: number
  loading?: string
  options?: Monaco.editor.IStandaloneEditorConstructionOptions
  diffOptions?: Monaco.editor.IStandaloneDiffEditorConstructionOptions
  overrideServices?: Monaco.editor.IEditorOverrideServices
  saveViewState?: boolean
  keepCurrentModel?: boolean
  width?: string | number
  height?: string | number
  mode?: "normal" | "diff"
  monaco?: typeof Monaco | null
}

const props = withDefaults(defineProps<EditorProps>(), {
  theme: "light-plus",
  loading: "Loading...",
  options: () => ({}),
  diffOptions: () => ({}),
  overrideServices: () => ({}),
  saveViewState: true,
  keepCurrentModel: false,
  width: "100%",
  height: "100%",
  mode: "normal",
  monaco: null,
})

const emit = defineEmits<{
  (e: "mount:editor", editor: Monaco.editor.IStandaloneCodeEditor | Monaco.editor.IStandaloneDiffEditor, monaco: typeof Monaco): void
  (e: "change", value: string, event: Monaco.editor.IModelContentChangedEvent): void
  (e: "validate", markers: Monaco.editor.IMarker[]): void
  (e: "dirty:change", isDirty: boolean): void
  (e: "selection:change", event: Monaco.editor.ICursorSelectionChangedEvent): void
}>()

// Refs
const isEditorReady = ref(false)
const editorRef = shallowRef<Raw<Monaco.editor.IStandaloneCodeEditor | Monaco.editor.IStandaloneDiffEditor> | null>(null)

const containerRef = ref<HTMLElement | null>(null)
const preventTriggerChangeEvent = ref(false)
const preventCreation = ref(false)
const subscriptionRef = ref<Monaco.IDisposable[]>([])
const isReadOnly = injectLocal<Ref<boolean>>("isEditorReadOnly", ref(false))
// ViewStates storage
const viewStates = ref(new Map())

const { mode, value, language, path, theme, line, loading, defaultValue, defaultLanguage, defaultPath, options, overrideServices, saveViewState, keepCurrentModel, diffOptions } = toRefs(props)
const monacoRef = injectLocal<ShallowRef<typeof Monaco | null>>("monaco", shallowRef(null))

// Editor creation and initialization
async function createEditor() {
  const monaco = monacoRef.value
  const container = containerRef.value

  if (preventCreation.value) {
    return
  }

  if (!container || !monaco) {
    const stop = watch([monacoRef, containerRef], ([newMonaco, newContainer]) => {
      if (newMonaco && newContainer) {
        createEditor()
        stop()
      }
    })
    return
  }

  preventCreation.value = true

  let editor: Monaco.editor.IStandaloneCodeEditor | Monaco.editor.IStandaloneDiffEditor | null = null
  if (mode.value === "diff") {
    editor = monaco.editor.createDiffEditor(
      container,
      {
        renderSideBySide: true,
        ...options.value,
        ...diffOptions.value,
      },
    )
  }
  else {
    const autoCreatedModelPath = path.value || defaultPath.value
    const defaultModel = getOrCreateNormalModel(
      monaco,
      value.value || defaultValue.value || "",
      language.value || defaultLanguage.value || "",
      autoCreatedModelPath || "",
    )

    editor = monaco.editor.create(
      container,
      {
        model: defaultModel,
        automaticLayout: true,
        ...options.value,
      },
      overrideServices.value,
    )

    if (saveViewState.value) {
      const state = viewStates.value.get(autoCreatedModelPath)
      if (state) {
        editor.restoreViewState(state)
      }
    }
  }

  editorRef.value = markRaw(editor)

  monaco.editor.setTheme(theme.value)

  if (line.value !== undefined) {
    editor.revealLine(line.value)
  }

  isEditorReady.value = true

  await nextTick()
  emit("mount:editor", editor, monaco)
  preventCreation.value = false
}

watch(value, (newValue) => {
  const editor = editorRef.value
  const monaco = monacoRef.value

  if (!editor || newValue === undefined) {
    return
  }

  if (isDiffEditor(editor)) {
    return
  }

  if (editor.getOption(monaco!.editor.EditorOption.readOnly)) {
    editor.setValue(newValue)
  }
  else if (newValue !== editor.getValue()) {
    preventTriggerChangeEvent.value = true
    editor.executeEdits("", [
      {
        range: editor.getModel()!.getFullModelRange(),
        text: newValue,
        forceMoveMarkers: true,
      },
    ])
    editor.pushUndoStop()
    preventTriggerChangeEvent.value = false
  }
}, { deep: true })

watch(language, (newLanguage) => {
  const editor = editorRef.value
  const monaco = monacoRef.value
  const model = editor?.getModel()

  if (model && newLanguage && monaco) {
    if (isDiffEditorModel(model)) {
      return
    }

    monaco.editor.setModelLanguage(model, newLanguage)
  }
}, { immediate: true })

watch(line, (newLine) => {
  const editor = editorRef.value

  if (newLine !== undefined && editor) {
    editor.revealLine(newLine)
  }
})

watch(theme, (newTheme) => {
  const monaco = monacoRef.value

  if (monaco) {
    monaco.editor.setTheme(newTheme)
  }
})

// Event listeners
watch(isEditorReady, (ready) => {
  const editor = editorRef.value
  const monaco = monacoRef.value

  if (!ready || !editor || !monaco || isDiffEditor(editor)) {
    return
  }

  // Content change subscription
  subscriptionRef.value.forEach(subscription => subscription.dispose())
  subscriptionRef.value.push(editor.onDidChangeModelContent((event) => {
    if (!editor)
      return

    if (!preventTriggerChangeEvent.value) {
      const currentValue = editor.getValue()
      emit("change", currentValue, event)
    }
  }))

  // Validation markers
  subscriptionRef.value.push(monaco.editor.onDidChangeMarkers((uris) => {
    if (!editor)
      return

    const editorUri = editor.getModel()?.uri
    if (!editorUri)
      return

    const currentEditorHasMarkerChanges = uris.find(uri => uri.path === editorUri.path)
    if (currentEditorHasMarkerChanges) {
      if (!monaco)
        return

      const markers = monaco.editor.getModelMarkers({
        resource: editorUri,
      })
      emit("validate", markers)
    }
  }))

  subscriptionRef.value.push(editor.onWillChangeModel((event) => {
    if (!editor)
      return

    const { oldModelUrl } = event
    if (oldModelUrl) {
      viewStates.value.set(oldModelUrl.path, editor.saveViewState())
    }
  }))

  subscriptionRef.value.push(editor.onDidChangeModel((event) => {
    if (!editor)
      return

    const { newModelUrl } = event
    if (newModelUrl) {
      const state = viewStates.value.get(newModelUrl.path)
      if (state) {
        editor.restoreViewState(state)
      }
    }
  }))

  subscriptionRef.value.push(editor.onDidChangeCursorSelection((event) => {
    if (!editor)
      return

    emit("selection:change", event)
  }))
})

watch(isReadOnly, (newIsReadOnly) => {
  const editor = editorRef.value
  if (editor) {
    editor.updateOptions({
      readOnly: newIsReadOnly,
    })
  }
}, { immediate: true })

watch(mode, async () => {
  const editor = editorRef.value

  if (editor) {
    editor.dispose()
  }

  await createEditor()
}, { immediate: true })

watch(options, (newOptions) => {
  const editor = editorRef.value

  if (editor && newOptions) {
    if (!newOptions.readOnly) {
      editor.updateOptions({
        ...newOptions,
        readOnly: false,
      })
    }
    else {
      editor.updateOptions(newOptions)
    }
  }
}, { deep: true })

watch(diffOptions, (newDiffOptions) => {
  const editor = editorRef.value
  if (editor && isDiffEditor(editor)) {
    editor.updateOptions(newDiffOptions)
  }
}, { deep: true })

onBeforeUnmount(() => {
  const editor = editorRef.value

  subscriptionRef.value.forEach(subscription => subscription.dispose())

  if (!editor) {
    return
  }

  editor.dispose()
})
</script>

<style lang="scss" scoped>
.n-card {
  display: flex;
  flex-direction: column;

  :deep(.n-card__content) {
    flex: 1;
    padding: 0;
    height: 100%;
  }
}
</style>
