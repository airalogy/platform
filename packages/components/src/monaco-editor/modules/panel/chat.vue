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
        <masterbrain-change-status
          v-if="latestAppliedEdit"
          data-testid="editor-ai-change-status"
          class="mb-2"
          :applied="latestAppliedEdit"
          :undoing="undoing"
          :changed-label="$t('chat.editorCodeEdit.appliedLabel')"
          :view-label="$t('chat.editorCodeEdit.viewChanges')"
          :undo-label="$t('chat.editorCodeEdit.undo')"
          :undoing-label="$t('chat.editorCodeEdit.undoing')"
          @view="openLatestChangeDetails"
          @undo="undoLatestEdit"
        />
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
      <template v-if="codeEditResult">
        <n-alert :type="reviewRequiresApproval ? 'warning' : 'info'" :bordered="false" class="mb-4">
          {{ reviewRequiresApproval
            ? $t("chat.editorCodeEdit.reviewRequiredDescription")
            : $t("chat.editorCodeEdit.reviewDescription") }}
        </n-alert>

        <masterbrain-change-review
          :result="codeEditResult"
          :applying="applyingAll"
          :show-header="false"
          :show-footer="false"
          :show-apply="false"
          :title="$t('chat.editorCodeEdit.reviewTitle')"
          :aria-label="$t('chat.editorCodeEdit.reviewTitle')"
          :summary-label="$t('chat.editorCodeEdit.summaryTitle')"
          :details-label="$t('chat.editorCodeEdit.details')"
          :created-label="$t('chat.editorCodeEdit.status.created')"
          :modified-label="$t('chat.editorCodeEdit.status.modified')"
          :deleted-label="$t('chat.editorCodeEdit.status.deleted')"
          class="platform-masterbrain-review"
        >
          <template #summary>
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
          </template>

          <template #warnings>
            <n-alert
              v-if="reviewWarnings.length"
              type="warning"
              :title="$t('chat.editorCodeEdit.warnings')"
            >
              <ul class="m-0 pl-5">
                <li v-for="warning in reviewWarnings" :key="warning">
                  {{ warning }}
                </li>
              </ul>
            </n-alert>
          </template>

          <template #file-header="{ change }">
            <div class="flex items-center justify-between gap-3 p-3">
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
            <p class="mb-3 mt-0 px-3 text-sm text-gray-600 leading-5">
              {{ getChangedFileSummary(change) }}
            </p>
          </template>

          <template #diff="{ change }">
            <n-collapse arrow-placement="right" class="border-t border-[var(--n-border-color)] px-3 py-2">
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
                <masterbrain-monaco-diff
                  :data-testid="`editor-ai-diff-${change.path}`"
                  :original="getOriginalContent(change)"
                  :modified="getModifiedContent(change)"
                  :language="getChangedFileLanguage(change)"
                  :side-by-side="getDiffViewMode(change.path) === 'side-by-side'"
                  height="360px"
                />
              </n-collapse-item>
            </n-collapse>
          </template>
        </masterbrain-change-review>

        <n-collapse v-if="codeEditResult.execution_log.length" arrow-placement="right" class="mt-4">
          <n-collapse-item :title="$t('chat.editorCodeEdit.executionLog')" name="execution-log">
            <pre class="code-edit-log">{{ codeEditResult.execution_log.join("\n") }}</pre>
          </n-collapse-item>
        </n-collapse>
      </template>
      <n-empty v-else :description="$t('chat.editorCodeEdit.emptyResult')" />

      <template #footer>
        <div class="flex items-center justify-end gap-3">
          <n-button @click="reviewModalVisible = false">
            {{ $t("chat.editorCodeEdit.close") }}
          </n-button>
          <n-button
            v-if="canApplyReviewedChanges"
            type="primary"
            data-testid="editor-ai-apply-all"
            :loading="applyingAll"
            @click="applyReviewedChanges"
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
import type {
  CodeEditChangedFile,
  CodeEditRequest,
  CodeEditResponse,
  WorkspaceAdapter,
  WorkspaceFile,
  WorkspaceMutation,
} from "@airalogy/masterbrain-client"
import type { ChatModelConfig } from "@airalogy/shared"
import { useScroll } from "@airalogy/components/chat/composables"
import { createThinkingMessage, createUserMessage, formatErrorMessage } from "@airalogy/components/chat/composables/utils"
import ChatComponent from "@airalogy/components/chat/index.vue"
import ChatWrapperActions from "@airalogy/components/chat/modules/chat-wrapper-actions.vue"
import { isNormalModelInfo, useActiveEditorStore, useModelsStore } from "@airalogy/components/monaco-editor/store/editorStore"
import { useUploadFileDataStore } from "@airalogy/components/monaco-editor/store/uploadFileDataStore"
import { useClosableMessage, useScrollTrap } from "@airalogy/composables"
import { normalizeCodeEditResponse, sha256Hex, WorkspaceConflictError } from "@airalogy/masterbrain-client"
import { MasterbrainChangeReview, MasterbrainChangeStatus, useCodeEditAssistant } from "@airalogy/masterbrain-vue"
import { MasterbrainMonacoDiff } from "@airalogy/masterbrain-vue/monaco"
import { DEFAULT_FILE_ID_MAP } from "@airalogy/shared/constants/protocol"
import { ChatModel } from "@airalogy/shared/enum/chat"
import { $t } from "@airalogy/shared/locales"
import { getFileLanguage } from "@airalogy/shared/utils"
import { nanoid } from "nanoid"
import { useOrProvideChatInfoStore } from "../../../chat/composables/useChatInfoStore"
import "@airalogy/masterbrain-vue/style.css"

type PlatformCodeEditPayload = Omit<CodeEditRequest, "model"> & { model: ChatModelConfig }

interface CodeEditFileDef {
  id: string
  path: string
  type: "aimd" | "py" | "toml"
}

const props = withDefaults(defineProps<{
  protocolId?: string | null
  airalogyId?: string | null
  codeEdit?: (payload: PlatformCodeEditPayload) => Promise<{ data?: unknown | null, error?: unknown }>
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

const MASTERBRAIN_MODEL_NAME_BY_TYPE: Record<ChatModel, string> = {
  [ChatModel.BASIC]: "qwen3.5-flash",
  [ChatModel.PLUS]: "qwen3.5-plus",
  [ChatModel.PRO]: "qwen3-max",
  [ChatModel.GPT]: "gpt-4.1",
}

const PLATFORM_MODEL_TYPE_BY_NAME = Object.fromEntries(
  Object.entries(MASTERBRAIN_MODEL_NAME_BY_TYPE).map(([modelType, modelName]) => [modelName, Number(modelType)]),
) as Record<string, ChatModelConfig["model_type"]>

const modelsStore = useModelsStore()
const activeEditorStore = useActiveEditorStore()
const uploadFileDataStore = useUploadFileDataStore()
const message = useClosableMessage()
const reviewModalVisible = ref(false)
const reviewRequiresApproval = ref(false)
const codeEditResult = ref<CodeEditResponse | null>(null)
const codeEditOriginalContents = ref<Record<string, string>>({})
const diffViewModes = ref<Record<string, "inline" | "side-by-side">>({})
const deletedWorkspacePaths = new Set<string>()

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

function findFileDef(path: string) {
  return CODE_EDIT_FILES.find(fileDef => fileDef.path === path) || null
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

function readWorkspaceFile(path: string): WorkspaceFile | null {
  const fileDef = findFileDef(path)
  if (!fileDef) {
    return null
  }
  const modelInfo = findModelInfoForFile(fileDef)
  const storeFile = uploadFileDataStore.getFileById(fileDef.id) || uploadFileDataStore.getFileByFilename(fileDef.path)
  if (deletedWorkspacePaths.has(path)) {
    const liveContent = modelInfo?.model && !modelInfo.model.isDisposed()
      ? modelInfo.model.getValue()
      : ""
    if (!liveContent) {
      return null
    }
    deletedWorkspacePaths.delete(path)
  }
  if (!modelInfo && !storeFile) {
    return null
  }
  return {
    path: fileDef.path,
    content: readFileContent(fileDef),
    type: fileDef.type,
  }
}

function collectWorkspaceFiles(): WorkspaceFile[] {
  return CODE_EDIT_FILES
    .map(fileDef => readWorkspaceFile(fileDef.path))
    .filter((file): file is WorkspaceFile => file !== null)
}

function collectEditorSelection() {
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

function collectChatHistory() {
  return (session.value?.data || [])
    .filter(item => !item.loading && !item.error && item.text.trim())
    .slice(-12)
    .map(item => ({
      role: item.inversion ? "user" as const : "assistant" as const,
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

function getStoreFilePath(fileDef: CodeEditFileDef) {
  const existingFile = uploadFileDataStore.getFileById(fileDef.id) || uploadFileDataStore.getFileByFilename(fileDef.path)
  if (existingFile?.path) {
    return existingFile.path
  }
  return uploadFileDataStore.rootPath
    ? `${uploadFileDataStore.rootPath}/${fileDef.path}`
    : fileDef.path
}

async function writeFileContent(fileDef: CodeEditFileDef, content: string) {
  deletedWorkspacePaths.delete(fileDef.path)
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

async function deleteFileContent(fileDef: CodeEditFileDef) {
  const modelInfo = findModelInfoForFile(fileDef)
  if (modelInfo?.model && !modelInfo.model.isDisposed()) {
    modelInfo.model.setValue("")
    modelInfo.content = ""
    modelsStore.setModelDirty(modelInfo.id, true)
  }
  uploadFileDataStore.removeFileById(fileDef.id)
  deletedWorkspacePaths.add(fileDef.path)
}

async function applyWorkspaceMutation(fileDef: CodeEditFileDef, mutation: WorkspaceMutation) {
  if (mutation.status === "deleted") {
    await deleteFileContent(fileDef)
    return
  }
  await writeFileContent(fileDef, mutation.content)
}

async function verifyMutationHashes(mutations: readonly WorkspaceMutation[]) {
  const conflicts: string[] = []
  for (const mutation of mutations) {
    if (mutation.expected_hash === undefined) {
      continue
    }
    const current = readWorkspaceFile(mutation.path)
    const currentHash = current ? await sha256Hex(current.content) : null
    if (currentHash !== mutation.expected_hash) {
      conflicts.push(mutation.path)
    }
  }
  if (conflicts.length) {
    throw new WorkspaceConflictError(
      `Workspace files changed before the operation: ${conflicts.join(", ")}`,
      conflicts,
    )
  }
}

const workspaceAdapter: WorkspaceAdapter = {
  readFile: readWorkspaceFile,
  async applyMutations(mutations) {
    const resolved = mutations.map((mutation) => {
      const fileDef = findFileDef(mutation.path)
      if (!fileDef) {
        throw new Error($t("chat.editorCodeEdit.unsupportedFile"))
      }
      return {
        mutation,
        fileDef,
        before: readWorkspaceFile(fileDef.path),
      }
    })

    await verifyMutationHashes(mutations)
    try {
      for (const { mutation, fileDef } of resolved) {
        await applyWorkspaceMutation(fileDef, mutation)
      }
    }
    catch (error) {
      for (const { fileDef, before } of resolved) {
        if (before) {
          await writeFileContent(fileDef, before.content)
        }
        else {
          await deleteFileContent(fileDef)
        }
      }
      throw error
    }
  },
}

const codeEditClient = {
  async runCodeEdit(request: CodeEditRequest): Promise<CodeEditResponse> {
    if (!props.codeEdit) {
      throw new Error($t("chat.editorCodeEdit.emptyResult"))
    }
    const { model, ...payload } = request
    const modelType = PLATFORM_MODEL_TYPE_BY_NAME[model.name]
    if (!modelType) {
      throw new Error(`Unsupported Platform chat model: ${model.name}`)
    }
    const { data, error } = await props.codeEdit({
      ...payload,
      model: {
        model_type: modelType,
        enable_thinking: model.enable_thinking,
        enable_search: false,
      },
    })
    if (error) {
      throw error
    }
    if (!data) {
      throw new Error($t("chat.editorCodeEdit.emptyResult"))
    }
    return normalizeCodeEditResponse(data)
  },
}

const codeEditAssistant = useCodeEditAssistant({
  client: codeEditClient,
  workspace: workspaceAdapter,
  autoApply: true,
})
const codeEditLoading = codeEditAssistant.loading
const applyingAll = codeEditAssistant.applying
const undoing = codeEditAssistant.undoing
const latestAppliedEdit = codeEditAssistant.latestApplied

const reviewWarnings = computed(() => {
  if (!codeEditResult.value) {
    return []
  }
  return [...new Set([
    ...codeEditResult.value.warnings,
    ...codeEditResult.value.risk.reasons,
  ])]
})

const canApplyReviewedChanges = computed(() => {
  return reviewRequiresApproval.value
    && codeEditResult.value?.risk.recommended_action !== "block"
    && Boolean(codeEditAssistant.pendingReview.value)
})

function handleStartNewChat() {
  if (session.value) {
    prompt.value = ""
  }
  codeEditAssistant.clear()
  reviewModalVisible.value = false
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

function summarizeCodeEditResult(result: CodeEditResponse, applicationStatus: string) {
  const statusSummary = result.changed_files.length
    ? applicationStatus === "applied"
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
  if (!props.codeEdit || codeEditLoading.value) {
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

  startLoading()
  codeEditOriginalContents.value = Object.fromEntries(files.map(file => [file.path, file.content]))
  diffViewModes.value = {}

  try {
    const application = await codeEditAssistant.submit({
      prompt: normalizedInstruction,
      workspace_id: uuid,
      files,
      active_file_path: getActiveCodeEditFileDef()?.path,
      selection: collectEditorSelection(),
      chat_history: history,
      model: {
        name: MASTERBRAIN_MODEL_NAME_BY_TYPE[selectedModel.value],
        enable_thinking: enableThinking.value,
      },
    })

    codeEditResult.value = application.response
    reviewRequiresApproval.value = application.status === "review" || application.status === "blocked"
    if (reviewRequiresApproval.value) {
      reviewModalVisible.value = true
    }
    chatStore.updateMessageByUUID(uuid, assistantIndex, {
      text: summarizeCodeEditResult(application.response, application.status),
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
    endLoading()
    await nextTick()
    handleScrollToBottom(true)
  }
}

function openLatestChangeDetails() {
  const edit = latestAppliedEdit.value
  if (!edit) {
    return
  }
  codeEditResult.value = edit.response
  codeEditOriginalContents.value = Object.fromEntries(
    edit.files.map(snapshot => [snapshot.path, snapshot.before?.content || ""]),
  )
  diffViewModes.value = {}
  reviewRequiresApproval.value = false
  reviewModalVisible.value = true
}

async function undoLatestEdit() {
  try {
    const undone = await codeEditAssistant.undoLatest()
    if (undone) {
      reviewModalVisible.value = false
      message.success($t("chat.editorCodeEdit.undoSuccess"))
    }
  }
  catch (error) {
    if (error instanceof WorkspaceConflictError) {
      message.warning($t("chat.editorCodeEdit.undoConflict"))
      return
    }
    message.error(formatErrorMessage(error))
  }
}

async function applyReviewedChanges() {
  try {
    const applied = await codeEditAssistant.applyPending()
    if (!applied) {
      message.error($t("chat.editorCodeEdit.emptyResult"))
      return
    }
    reviewModalVisible.value = false
    reviewRequiresApproval.value = false
    message.success($t("chat.editorCodeEdit.applyAllSuccess"))
  }
  catch (error) {
    message.error(formatErrorMessage(error))
  }
}

function getStatusTagType(status: CodeEditChangedFile["status"]) {
  if (status === "created") {
    return "success"
  }
  if (status === "deleted") {
    return "error"
  }
  return "info"
}

function getChangedFileLabel(change: CodeEditChangedFile) {
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

function getDiffStats(change: CodeEditChangedFile) {
  const lines = change.diff.split("\n")
  return {
    added: lines.filter(line => line.startsWith("+") && !line.startsWith("+++")).length,
    removed: lines.filter(line => line.startsWith("-") && !line.startsWith("---")).length,
  }
}

function getChangedFileSummary(change: CodeEditChangedFile) {
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

function getOriginalContent(change: CodeEditChangedFile) {
  return codeEditOriginalContents.value[change.path] || ""
}

function getModifiedContent(change: CodeEditChangedFile) {
  return change.status === "deleted" ? "" : change.content
}

function getChangedFileLanguage(change: CodeEditChangedFile) {
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
.platform-masterbrain-review {
  --masterbrain-text: var(--n-text-color);
  --masterbrain-border: var(--n-border-color);
  --masterbrain-muted: var(--n-text-color-3);
}

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
