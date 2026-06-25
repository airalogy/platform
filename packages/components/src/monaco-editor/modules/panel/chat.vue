<template>
  <div class="relative h-full flex flex-col">
    <div>
      <h3 class="leading-10 !text-6">
        {{ $t("chat.askAira") }}
      </h3>

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
    />

    <n-modal
      v-model:show="reviewModalVisible"
      preset="card"
      :title="$t('chat.editorCodeEdit.reviewTitle')"
      class="max-w-5xl w-85vw"
      content-class="max-h-70vh overflow-y-auto"
    >
      <div v-if="codeEditResult" class="space-y-4">
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
              <span class="truncate font-mono text-sm">{{ change.path }}</span>
            </div>
            <n-button size="small" type="primary" secondary @click="applyChangedFile(change)">
              {{ $t("chat.editorCodeEdit.apply") }}
            </n-button>
          </div>
          <pre class="code-edit-diff">{{ change.diff || $t("chat.editorCodeEdit.diffFallback") }}</pre>
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
            type="primary"
            :loading="applyingAll"
            :disabled="!codeEditResult?.changed_files.length"
            @click="applyAllChangedFiles"
          >
            {{ $t("chat.editorCodeEdit.applyAll") }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import type { ChatModelConfig } from "@airalogy/shared"
import type { ModelInfo } from "@airalogy/components/monaco-editor/store/editorStore"
import { useScroll } from "@airalogy/components/chat/composables"
import { createThinkingMessage, createUserMessage, formatErrorMessage } from "@airalogy/components/chat/composables/utils"
import ChatComponent from "@airalogy/components/chat/index.vue"
import ChatWrapperActions from "@airalogy/components/chat/modules/chat-wrapper-actions.vue"
import { isNormalModelInfo, useActiveEditorStore, useModelsStore } from "@airalogy/components/monaco-editor/store/editorStore"
import { useUploadFileDataStore } from "@airalogy/components/monaco-editor/store/uploadFileDataStore"
import { useClosableMessage } from "@airalogy/composables"
import { useScrollTrap } from "@airalogy/composables"
import { DEFAULT_FILE_ID_MAP } from "@airalogy/shared/constants/protocol"
import { $t } from "@airalogy/shared/locales"
import { nanoid } from "nanoid"
import { useOrProvideChatInfoStore } from "../../../chat/composables/useChatInfoStore"

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

const CODE_EDIT_FILES: CodeEditFileDef[] = [
  { id: DEFAULT_FILE_ID_MAP.protocol, path: "protocol.aimd", type: "aimd" },
  { id: DEFAULT_FILE_ID_MAP.model, path: "model.py", type: "py" },
  { id: DEFAULT_FILE_ID_MAP.assigner, path: "assigner.py", type: "py" },
  { id: DEFAULT_FILE_ID_MAP.toml_config, path: "protocol.toml", type: "toml" },
]

const props = withDefaults(defineProps<{
  protocolId?: string | null
  airalogyId?: string | null
  codeEdit?: (payload: EditorCodeEditPayload) => Promise<{ data?: EditorCodeEditResponse | null, error?: unknown }>
}>(), {
  protocolId: null,
  airalogyId: null,
  codeEdit: undefined,
})

const modelsStore = useModelsStore()
const activeEditorStore = useActiveEditorStore()
const uploadFileDataStore = useUploadFileDataStore()
const message = useClosableMessage()
const codeEditLoading = ref(false)
const applyingAll = ref(false)
const reviewModalVisible = ref(false)
const codeEditResult = ref<EditorCodeEditResponse | null>(null)

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

function summarizeCodeEditResult(result: EditorCodeEditResponse) {
  const statusSummary = result.changed_files.length
    ? $t("chat.editorCodeEdit.changedSummary", { count: result.changed_files.length })
    : $t("chat.editorCodeEdit.noChanges")
  const warningSummary = result.warnings.length
    ? `\n\n${$t("chat.editorCodeEdit.warnings")}:\n${result.warnings.map(warning => `- ${warning}`).join("\n")}`
    : ""
  const modelMessage = result.message ? `${result.message}\n\n` : ""

  return `${modelMessage}${statusSummary}${warningSummary}`.trim()
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

    codeEditResult.value = data
    reviewModalVisible.value = data.changed_files.length > 0
    chatStore.updateMessageByUUID(uuid, assistantIndex, {
      text: summarizeCodeEditResult(data),
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
    message.error($t("chat.editorCodeEdit.unsupportedFile"))
    return
  }

  const content = change.status === "deleted" ? "" : change.content
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

  message.success($t("chat.editorCodeEdit.applySuccess"))
}

async function applyAllChangedFiles() {
  if (!codeEditResult.value?.changed_files.length) {
    message.error($t("chat.editorCodeEdit.emptyResult"))
    return
  }

  applyingAll.value = true
  try {
    for (const change of codeEditResult.value.changed_files) {
      await applyChangedFile(change)
    }
    reviewModalVisible.value = false
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
</script>

<style scoped>
.code-edit-diff,
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
