<template>
  <div class="relative h-full flex flex-col" data-testid="editor-ai-edit-panel">
    <div class="px-4 pt-1">
      <h3 class="mb-2 min-h-8 pr-22 text-xl font-semibold leading-7">
        {{ props.codeEdit ? $t("chat.editorCodeEdit.panelTitle") : $t("chat.askAira") }}
      </h3>

      <div
        v-if="props.codeEdit"
        class="mb-3 border border-blue-100 rounded-xl bg-blue-50/70 px-3 py-2.5"
      >
        <p class="m-0 text-sm text-slate-700 leading-5">
          {{ $t("chat.editorCodeEdit.panelDescription") }}
        </p>
        <p class="mb-0 mt-1.5 flex items-center gap-1.5 text-xs text-blue-700 leading-5">
          <span class="size-1.5 shrink-0 rounded-full bg-blue-500" aria-hidden="true" />
          {{ $t("chat.editorCodeEdit.panelSafetyHint") }}
        </p>
      </div>

      <chat-wrapper-actions v-bind="chatWrapperActionProps" v-on="chatWrapperActionEventHandlers" />
    </div>

    <chat-component
      ref="scrollRef"
      class="flex-1 overflow-x-hidden overflow-y-auto px-4"
      :protocol-id="props.protocolId || null"
      :airalogy-id="props.airalogyId || null"
      source="editor"
      :submit-handler="props.codeEdit ? handleEditorSubmit : undefined"
      :show-scroll-button="arrivedState.bottom"
      @scroll-to-bottom="handleScrollToBottom"
    >
      <template #input-prefix>
        <div
          v-if="latestAppliedEdit"
          data-testid="editor-ai-change-status"
          class="mb-2 flex items-center gap-2 border border-emerald-200 rounded-xl bg-emerald-50 px-3 py-2 text-sm"
        >
          <span class="min-w-0 flex-1 text-emerald-800">
            {{ $t("chat.editorCodeEdit.appliedStatus", { count: latestAppliedEdit.result.changed_files.length }) }}
          </span>
          <n-button
            data-testid="editor-ai-view-changes"
            size="tiny"
            text
            type="primary"
            @click="openLatestChangeDetails"
          >
            {{ $t("chat.editorCodeEdit.viewChanges") }}
          </n-button>
          <n-button
            data-testid="editor-ai-undo"
            size="tiny"
            secondary
            type="primary"
            :loading="undoing"
            @click="undoLatestEdit"
          >
            {{ $t("chat.editorCodeEdit.undo") }}
          </n-button>
        </div>
      </template>
    </chat-component>

    <n-modal
      v-model:show="reviewModalVisible"
      data-testid="editor-ai-review"
      preset="card"
      :title="$t('chat.editorCodeEdit.reviewTitle')"
      class="max-w-5xl w-85vw"
      content-class="max-h-70vh overflow-y-auto"
    >
      <div v-if="codeEditResult" class="space-y-4">
        <n-alert :type="reviewRequiresApproval ? 'warning' : 'info'" :bordered="false">
          {{ reviewRequiresApproval
            ? $t("chat.editorCodeEdit.reviewRequiredDescription")
            : $t("chat.editorCodeEdit.reviewDescription") }}
        </n-alert>

        <section
          data-testid="editor-ai-change-summary"
          class="border border-blue-100 rounded-xl bg-blue-50 px-4 py-3"
        >
          <div class="mb-1 flex items-center justify-between gap-3">
            <h4 class="m-0 text-sm text-blue-900 font-semibold">
              {{ $t("chat.editorCodeEdit.summaryTitle") }}
            </h4>
            <n-tag size="small" round type="info">
              {{ $t("chat.editorCodeEdit.filesChanged", { count: codeEditResult.changed_files.length }) }}
            </n-tag>
          </div>
          <p class="m-0 whitespace-pre-wrap text-sm text-blue-800 leading-6">
            {{ codeEditResult.message || $t("chat.editorCodeEdit.summaryFallback") }}
          </p>
        </section>

        <n-alert v-if="codeEditResult.warnings.length" type="warning" :title="$t('chat.editorCodeEdit.warnings')">
          <ul class="m-0 pl-5">
            <li v-for="warning in codeEditResult.warnings" :key="warning">
              {{ warning }}
            </li>
          </ul>
        </n-alert>

        <div
          v-for="change in codeEditResult.changed_files"
          :key="change.path"
          class="border border-[var(--n-border-color)] rounded-2 p-3"
        >
          <div class="mb-3 flex items-center justify-between gap-3">
            <div class="min-w-0 flex items-center gap-2">
              <n-tag size="small" :type="getStatusTagType(change.status)">
                {{ $t(`chat.editorCodeEdit.status.${change.status}`) }}
              </n-tag>
              <div class="min-w-0">
                <div class="truncate text-sm font-medium">
                  {{ getChangedFileLabel(change) }}
                </div>
                <div class="truncate text-xs text-gray-400 font-mono">
                  {{ change.path }}
                </div>
              </div>
            </div>
          </div>
          <p class="mb-3 mt-0 text-sm text-gray-600 leading-5">
            {{ getChangedFileSummary(change) }}
          </p>
          <n-collapse arrow-placement="right">
            <n-collapse-item :title="$t('chat.editorCodeEdit.details')" :name="`diff-${change.path}`">
              <div class="mb-2 flex items-center justify-between gap-3">
                <span class="text-xs text-gray-500">
                  {{ $t("chat.editorCodeEdit.diffModeHint") }}
                </span>
                <n-radio-group
                  :value="getDiffViewMode(change.path)"
                  size="small"
                  @update:value="setDiffViewMode(change.path, $event)"
                >
                  <n-radio-button
                    value="inline"
                    :data-testid="`editor-ai-diff-inline-${change.path}`"
                  >
                    {{ $t("chat.editorCodeEdit.inlineDiff") }}
                  </n-radio-button>
                  <n-radio-button
                    value="side-by-side"
                    :data-testid="`editor-ai-diff-side-by-side-${change.path}`"
                  >
                    {{ $t("chat.editorCodeEdit.sideBySideDiff") }}
                  </n-radio-button>
                </n-radio-group>
              </div>
              <code-edit-diff-view
                :data-testid="`editor-ai-diff-${change.path}`"
                :original="getOriginalContent(change)"
                :modified="getModifiedContent(change)"
                :language="getChangedFileLanguage(change)"
                :side-by-side="getDiffViewMode(change.path) === 'side-by-side'"
              />
            </n-collapse-item>
          </n-collapse>
        </div>

        <n-collapse v-if="codeEditResult.execution_log.length" arrow-placement="right">
          <n-collapse-item :title="$t('chat.editorCodeEdit.executionLog')" name="execution-log">
            <pre class="code-edit-log">{{ codeEditResult.execution_log.join("\n") }}</pre>
          </n-collapse-item>
        </n-collapse>
      </div>
      <n-empty v-else :description="$t('chat.editorCodeEdit.emptyResult')" />

      <template #footer>
        <div class="flex items-center justify-end gap-3">
          <n-button @click="reviewModalVisible = false">
            {{ $t("chat.editorCodeEdit.close") }}
          </n-button>
          <n-button
            v-if="reviewRequiresApproval"
            type="primary"
            data-testid="editor-ai-apply-all"
            :loading="applyingAll"
            :disabled="!codeEditResult?.changed_files.length"
            @click="applyAllChangedFiles"
          >
            {{ $t("chat.editorCodeEdit.applyAnyway") }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import type { ModelInfo } from "@airalogy/components/monaco-editor/store/editorStore"
import type { ChatModelConfig } from "@airalogy/shared"
import { useScroll } from "@airalogy/components/chat/composables"
import { createThinkingMessage, createUserMessage, formatErrorMessage } from "@airalogy/components/chat/composables/utils"
import ChatComponent from "@airalogy/components/chat/index.vue"
import ChatWrapperActions from "@airalogy/components/chat/modules/chat-wrapper-actions.vue"
import { isNormalModelInfo, useActiveEditorStore, useModelsStore } from "@airalogy/components/monaco-editor/store/editorStore"
import { useUploadFileDataStore } from "@airalogy/components/monaco-editor/store/uploadFileDataStore"
import { useClosableMessage, useScrollTrap } from "@airalogy/composables"
import { DEFAULT_FILE_ID_MAP } from "@airalogy/shared/constants/protocol"
import { $t } from "@airalogy/shared/locales"
import { getFileLanguage } from "@airalogy/shared/utils"
import { nanoid } from "nanoid"
import { useOrProvideChatInfoStore } from "../../../chat/composables/useChatInfoStore"
import CodeEditDiffView from "./code-edit-diff-view.vue"

type EditorCodeEditFileType = "aimd" | "py" | "toml" | "other"
type EditorCodeEditChangedFileStatus = "created" | "modified" | "deleted"

interface EditorCodeEditWorkspaceFile {
  path: string
  content: string
  type: EditorCodeEditFileType
}

interface EditorCodeEditSelection {
  text: string
  start_offset: number
  end_offset: number
}

interface EditorCodeEditHistoryMessage {
  role: "user" | "assistant"
  content: string
}

interface EditorCodeEditChangedFile {
  path: string
  name: string
  type: "aimd" | "py" | "toml"
  status: EditorCodeEditChangedFileStatus
  content: string
  diff: string
}

interface EditorCodeEditResponse {
  runtime: "opencode"
  message: string
  edit_status: "changed" | "no_changes"
  changed_files: EditorCodeEditChangedFile[]
  warnings: string[]
  execution_log: string[]
}

interface EditorCodeEditPayload {
  prompt: string
  workspace_id?: string
  files: EditorCodeEditWorkspaceFile[]
  active_file_path?: string
  selection?: EditorCodeEditSelection
  chat_history?: EditorCodeEditHistoryMessage[]
  model: ChatModelConfig
}

interface CodeEditFileDef {
  id: string
  path: string
  type: Exclude<EditorCodeEditFileType, "other">
}

interface EditorCodeEditFileSnapshot {
  fileDef: CodeEditFileDef
  content: string
}

interface AppliedCodeEdit {
  id: string
  result: EditorCodeEditResponse
  before: EditorCodeEditFileSnapshot[]
}

const props = withDefaults(defineProps<{
  protocolId?: string | null
  airalogyId?: string | null
  codeEdit?: (payload: EditorCodeEditPayload) => Promise<{ data?: EditorCodeEditResponse | null, error?: unknown }>
}>(), {
  protocolId: null,
  airalogyId: null,
  codeEdit: undefined,
})

const CODE_EDIT_FILES: CodeEditFileDef[] = [
  { id: DEFAULT_FILE_ID_MAP.protocol, path: "protocol.aimd", type: "aimd" },
  { id: DEFAULT_FILE_ID_MAP.model, path: "model.py", type: "py" },
  { id: DEFAULT_FILE_ID_MAP.assigner, path: "assigner.py", type: "py" },
  { id: DEFAULT_FILE_ID_MAP.toml_config, path: "protocol.toml", type: "toml" },
]

const modelsStore = useModelsStore()
const activeEditorStore = useActiveEditorStore()
const uploadFileDataStore = useUploadFileDataStore()
const message = useClosableMessage()
const codeEditLoading = ref(false)
const applyingAll = ref(false)
const undoing = ref(false)
const reviewModalVisible = ref(false)
const reviewRequiresApproval = ref(false)
const codeEditResult = ref<EditorCodeEditResponse | null>(null)
const codeEditOriginalContents = ref<Record<string, string>>({})
const diffViewModes = ref<Record<string, "inline" | "side-by-side">>({})
const appliedEditHistory = ref<AppliedCodeEdit[]>([])
const latestAppliedEdit = computed(() => appliedEditHistory.value[appliedEditHistory.value.length - 1] || null)

// Add scroll trapping to prevent parent scrolling
const { measure, scrollToBottom, scrollRef, arrivedState } = useScroll()
useScrollTrap(scrollRef)

const contentRef = ref<HTMLElement | null>(null)
watch([() => scrollRef.value?.clientHeight, () => contentRef.value?.clientHeight], () => {
  setTimeout(() => {
    measure()
    scrollToBottom({ smart: false, instant: true })
  }, 200)
}, { flush: "post", immediate: true })

function handleScrollToBottom(smart?: boolean) {
  scrollToBottom({ smart: smart ?? false, instant: true })
}

const chatInfoProps = reactive({
  source: "editor" as Chat.ChatSource,
  airalogyId: "",
  protocolId: null as string | null,
})

watchEffect(() => {
  chatInfoProps.airalogyId = props.airalogyId || ""
  chatInfoProps.protocolId = props.protocolId || null
})

const {
  session,
  prompt,
  clearActive,
  selectedModel,
  enableThinking,
  startLoading,
  endLoading,
  chatStore,
  chatId,
  emptyDraftId,
} = useOrProvideChatInfoStore(toRefs(chatInfoProps), (event, smart) => {
  if (event === "scrollToBottom") {
    handleScrollToBottom(smart)
  }
})

function handleStartNewChat() {
  if (session.value) {
    prompt.value = ""
  }

  clearActive()
}

const chatWrapperActionProps = computed(() => ({
  fullScreen: false,
  docked: false,
  collapsed: false,
  hideCollapse: false,
  containerClass: "absolute right-4 top-0 space-x-1",
  actions: ["newChat"],
}))

const chatWrapperActionEventHandlers = computed(() => ({
  toggleCollapse: () => ({}),
  toggleDock: () => ({}),
  toggleFullscreen: () => ({}),
  newChat: handleStartNewChat,
}))

function normalizeFileContent(content: unknown): string {
  if (typeof content === "string") {
    return content
  }
  if (content instanceof ArrayBuffer) {
    return new TextDecoder().decode(new Uint8Array(content))
  }
  if (ArrayBuffer.isView(content)) {
    return new TextDecoder().decode(content)
  }
  return ""
}

function matchesFileDef(modelInfo: { id?: string, name?: string, path?: string } | null | undefined, fileDef: CodeEditFileDef) {
  if (!modelInfo) {
    return false
  }
  return modelInfo.id === fileDef.id
    || modelInfo.name === fileDef.path
    || modelInfo.path === fileDef.path
    || Boolean(modelInfo.path?.endsWith(`/${fileDef.path}`))
}

function findModelInfoForFile(fileDef: CodeEditFileDef): ModelInfo | null {
  return modelsStore.modelInfos.find((modelInfo): modelInfo is ModelInfo => isNormalModelInfo(modelInfo) && matchesFileDef(modelInfo, fileDef)) || null
}

function getActiveCodeEditFileDef() {
  if (activeEditorStore.activeEditorId < 0) {
    return null
  }
  const activeModelInfo = modelsStore.getActiveModelInfo(activeEditorStore.activeEditorId, "normal")
  return CODE_EDIT_FILES.find(fileDef => matchesFileDef(activeModelInfo, fileDef)) || null
}

function readFileContent(fileDef: CodeEditFileDef): string {
  const modelInfo = findModelInfoForFile(fileDef)
  if (modelInfo?.model && !modelInfo.model.isDisposed()) {
    return modelInfo.model.getValue()
  }

  const storeFile = uploadFileDataStore.getFileById(fileDef.id) || uploadFileDataStore.getFileByFilename(fileDef.path)
  return normalizeFileContent(storeFile?.content)
}

function collectWorkspaceFiles(): EditorCodeEditWorkspaceFile[] {
  return CODE_EDIT_FILES.map(fileDef => ({
    path: fileDef.path,
    content: readFileContent(fileDef),
    type: fileDef.type,
  }))
}

function collectEditorSelection(): EditorCodeEditSelection | undefined {
  const activeFileDef = getActiveCodeEditFileDef()
  if (!activeFileDef) {
    return undefined
  }

  const activeModelInfo = modelsStore.getActiveModelInfo(activeEditorStore.activeEditorId, "normal")
  const activeEditor = activeEditorStore.activeEditor as any
  const selection = activeEditor?.getSelection?.()
  if (!activeModelInfo?.model || !selection || selection.isEmpty?.()) {
    return undefined
  }

  const text = activeModelInfo.model.getValueInRange(selection)
  if (!text.trim()) {
    return undefined
  }

  return {
    text,
    start_offset: activeModelInfo.model.getOffsetAt(selection.getStartPosition()),
    end_offset: activeModelInfo.model.getOffsetAt(selection.getEndPosition()),
  }
}

function collectChatHistory(): EditorCodeEditHistoryMessage[] {
  return (session.value?.data || [])
    .filter(item => !item.loading && !item.error && item.text.trim())
    .slice(-12)
    .map(item => ({
      role: item.inversion ? "user" : "assistant",
      content: item.text,
    }))
}

function ensureCodeEditSession() {
  const uuid = chatId.value || emptyDraftId.value || nanoid()
  if (!chatStore.findSessionByUUID(uuid)) {
    chatStore.createEmptySession(uuid, "editor", props.airalogyId)
  }
  else {
    chatStore.setActive(uuid)
  }
  return uuid
}

function buildCodeEditModelConfig(): ChatModelConfig {
  return {
    model_type: selectedModel.value,
    enable_thinking: enableThinking.value,
    enable_search: false,
  }
}

function summarizeCodeEditResult(result: EditorCodeEditResponse, autoApplied: boolean) {
  const statusSummary = result.changed_files.length
    ? autoApplied
      ? $t("chat.editorCodeEdit.autoAppliedSummary", { count: result.changed_files.length })
      : $t("chat.editorCodeEdit.reviewRequiredSummary", { count: result.changed_files.length })
    : result.message.trim()
      ? ""
      : $t("chat.editorCodeEdit.noChanges")
  const warningSummary = result.warnings.length
    ? `${$t("chat.editorCodeEdit.warnings")}:\n${result.warnings.map(warning => `- ${warning}`).join("\n")}`
    : ""

  return [result.message.trim(), statusSummary, warningSummary].filter(Boolean).join("\n\n")
}

async function handleEditorSubmit(instruction: string) {
  if (!props.codeEdit) {
    return
  }
  if (codeEditLoading.value) {
    return
  }

  const normalizedInstruction = instruction.trim()
  if (!normalizedInstruction) {
    message.error($t("chat.editorCodeEdit.emptyPrompt"))
    return
  }

  const files = collectWorkspaceFiles()
  if (!files.some(file => file.content.trim())) {
    message.error($t("chat.editorCodeEdit.noFiles"))
    return
  }

  const history = collectChatHistory()
  const uuid = ensureCodeEditSession()
  const userIndex = chatStore.addMessageToSessionByUUID(
    uuid,
    createUserMessage(normalizedInstruction, null),
    "editor",
    props.airalogyId,
  )
  const assistantIndex = chatStore.addMessageToSessionByUUID(
    uuid,
    createThinkingMessage(normalizedInstruction, selectedModel.value, userIndex),
    "editor",
    props.airalogyId,
  )

  codeEditLoading.value = true
  startLoading()

  try {
    const { data, error } = await props.codeEdit({
      prompt: normalizedInstruction,
      workspace_id: uuid,
      files,
      active_file_path: getActiveCodeEditFileDef()?.path,
      selection: collectEditorSelection(),
      chat_history: history,
      model: buildCodeEditModelConfig(),
    })

    if (error) {
      throw error
    }
    if (!data) {
      throw new Error($t("chat.editorCodeEdit.emptyResult"))
    }

    const reviewSnapshots = captureSnapshots(data.changed_files)
    codeEditResult.value = data
    codeEditOriginalContents.value = snapshotsToOriginalContents(reviewSnapshots)
    diffViewModes.value = {}
    const requiresApproval = shouldRequireReview(data)
    reviewRequiresApproval.value = requiresApproval
    let autoApplied = false
    if (data.changed_files.length && requiresApproval) {
      reviewModalVisible.value = true
    }
    else if (data.changed_files.length) {
      await applyCodeEditResult(data)
      autoApplied = true
    }
    chatStore.updateMessageByUUID(uuid, assistantIndex, {
      text: summarizeCodeEditResult(data, autoApplied),
      loading: false,
      error: false,
    })
  }
  catch (error) {
    chatStore.updateMessageByUUID(uuid, assistantIndex, {
      text: `${$t("chat.editorCodeEdit.failed")}: ${formatErrorMessage(error)}`,
      loading: false,
      error: true,
    })
  }
  finally {
    codeEditLoading.value = false
    endLoading()
    await nextTick()
    handleScrollToBottom(true)
  }
}

function findFileDefForChange(change: EditorCodeEditChangedFile) {
  return CODE_EDIT_FILES.find(fileDef => fileDef.path === change.path) || null
}

function getStoreFilePath(fileDef: CodeEditFileDef) {
  const existingFile = uploadFileDataStore.getFileById(fileDef.id) || uploadFileDataStore.getFileByFilename(fileDef.path)
  if (existingFile?.path) {
    return existingFile.path
  }
  return uploadFileDataStore.rootPath
    ? `${uploadFileDataStore.rootPath}/${fileDef.path}`
    : fileDef.path
}

async function applyChangedFile(change: EditorCodeEditChangedFile) {
  const fileDef = findFileDefForChange(change)
  if (!fileDef) {
    throw new Error($t("chat.editorCodeEdit.unsupportedFile"))
  }

  const content = change.status === "deleted" ? "" : change.content
  await writeFileContent(fileDef, content)
}

function shouldRequireReview(result: EditorCodeEditResponse) {
  return result.warnings.length > 0
    || result.changed_files.some(change => change.status === "deleted")
}

function captureSnapshots(changes: EditorCodeEditChangedFile[]): EditorCodeEditFileSnapshot[] {
  return changes.map((change) => {
    const fileDef = findFileDefForChange(change)
    if (!fileDef) {
      throw new Error($t("chat.editorCodeEdit.unsupportedFile"))
    }
    return {
      fileDef,
      content: readFileContent(fileDef),
    }
  })
}

function snapshotsToOriginalContents(snapshots: EditorCodeEditFileSnapshot[]) {
  return Object.fromEntries(snapshots.map(snapshot => [snapshot.fileDef.path, snapshot.content]))
}

async function restoreSnapshots(snapshots: EditorCodeEditFileSnapshot[]) {
  for (const snapshot of snapshots) {
    await writeFileContent(snapshot.fileDef, snapshot.content)
  }
}

async function writeFileContent(fileDef: CodeEditFileDef, content: string) {
  const modelInfo = findModelInfoForFile(fileDef)
  if (modelInfo?.model && !modelInfo.model.isDisposed()) {
    modelInfo.model.setValue(content)
    modelInfo.content = content
    modelsStore.setModelDirty(modelInfo.id, true)
  }

  await uploadFileDataStore.updateFileItem(fileDef.id, {
    id: fileDef.id,
    name: fileDef.path,
    path: getStoreFilePath(fileDef),
    kind: "file",
    status: "success",
    content,
    isEditable: true,
  }, false)
}

async function applyCodeEditResult(result: EditorCodeEditResponse) {
  const before = captureSnapshots(result.changed_files)
  try {
    for (const change of result.changed_files) {
      await applyChangedFile(change)
    }
  }
  catch (error) {
    await restoreSnapshots(before)
    throw error
  }

  appliedEditHistory.value.push({
    id: nanoid(),
    result,
    before,
  })
}

function openLatestChangeDetails() {
  if (!latestAppliedEdit.value) {
    return
  }
  codeEditResult.value = latestAppliedEdit.value.result
  codeEditOriginalContents.value = snapshotsToOriginalContents(latestAppliedEdit.value.before)
  diffViewModes.value = {}
  reviewRequiresApproval.value = false
  reviewModalVisible.value = true
}

function canSafelyUndo(edit: AppliedCodeEdit) {
  return edit.result.changed_files.every((change) => {
    const fileDef = findFileDefForChange(change)
    if (!fileDef) {
      return false
    }
    const expectedContent = change.status === "deleted" ? "" : change.content
    return readFileContent(fileDef) === expectedContent
  })
}

async function undoLatestEdit() {
  const edit = latestAppliedEdit.value
  if (!edit) {
    return
  }
  if (!canSafelyUndo(edit)) {
    message.warning($t("chat.editorCodeEdit.undoConflict"))
    return
  }

  undoing.value = true
  try {
    await restoreSnapshots(edit.before)
    appliedEditHistory.value.pop()
    reviewModalVisible.value = false
    message.success($t("chat.editorCodeEdit.undoSuccess"))
  }
  finally {
    undoing.value = false
  }
}

async function applyAllChangedFiles() {
  if (!codeEditResult.value?.changed_files.length) {
    message.error($t("chat.editorCodeEdit.emptyResult"))
    return
  }

  applyingAll.value = true
  try {
    await applyCodeEditResult(codeEditResult.value)
    reviewModalVisible.value = false
    reviewRequiresApproval.value = false
    message.success($t("chat.editorCodeEdit.applyAllSuccess"))
  }
  finally {
    applyingAll.value = false
  }
}

function getStatusTagType(status: EditorCodeEditChangedFileStatus) {
  if (status === "created") {
    return "success"
  }
  if (status === "deleted") {
    return "error"
  }
  return "info"
}

function getChangedFileLabel(change: EditorCodeEditChangedFile) {
  if (change.path === "protocol.aimd") {
    return $t("chat.editorCodeEdit.fileLabels.aimd")
  }
  if (change.path === "model.py") {
    return $t("chat.editorCodeEdit.fileLabels.model")
  }
  if (change.path === "assigner.py") {
    return $t("chat.editorCodeEdit.fileLabels.assigner")
  }
  if (change.path === "protocol.toml") {
    return $t("chat.editorCodeEdit.fileLabels.toml")
  }
  return change.name || change.path
}

function getDiffStats(change: EditorCodeEditChangedFile) {
  const lines = change.diff.split("\n")
  return {
    added: lines.filter(line => line.startsWith("+") && !line.startsWith("+++")).length,
    removed: lines.filter(line => line.startsWith("-") && !line.startsWith("---")).length,
  }
}

function getChangedFileSummary(change: EditorCodeEditChangedFile) {
  const file = getChangedFileLabel(change)
  const { added, removed } = getDiffStats(change)
  if (change.status === "created") {
    return $t("chat.editorCodeEdit.fileSummary.created", { file, added })
  }
  if (change.status === "deleted") {
    return $t("chat.editorCodeEdit.fileSummary.deleted", { file, removed })
  }
  return $t("chat.editorCodeEdit.fileSummary.modified", { file, added, removed })
}

function getOriginalContent(change: EditorCodeEditChangedFile) {
  return codeEditOriginalContents.value[change.path] || ""
}

function getModifiedContent(change: EditorCodeEditChangedFile) {
  return change.status === "deleted" ? "" : change.content
}

function getChangedFileLanguage(change: EditorCodeEditChangedFile) {
  return getFileLanguage(change.path)
}

function getDiffViewMode(path: string) {
  return diffViewModes.value[path] || "inline"
}

function setDiffViewMode(path: string, mode: string | number) {
  if (mode !== "inline" && mode !== "side-by-side") {
    return
  }
  diffViewModes.value[path] = mode
}
</script>

<style scoped>
.code-edit-log {
  max-height: 36vh;
  margin: 0;
  overflow: auto;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.04);
  padding: 12px;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
