import type { ChatProviderContext, ChatProviderProps, ContextDialogState, CurrentEditorProtocolContext, CurrentRecorderRecordContext } from "@airalogy/components/chat/providers/useChatProvider"
import { postAddAttachments } from "@/service/api/attachments"
import { baseURL } from "@/service/request"
import { useAuthStore } from "@/store/modules/auth"
import { createDefaultRendererContext } from "@airalogy/components/chat/providers/useChatProvider"
import { postToolResultChat as _postToolResultChat, stopStream as _stopStream } from "../service/api/chat"

export enum ToolType {
  INJECT_PROTOCOLS = "inject_airalogy_protocols",
  INJECT_RECORDS = "inject_airalogy_records",
  INJECT_DISCUSSIONS = "inject_airalogy_discussions",
  INJECT_DOCUMENTS = "inject_ref_protocol",
}
export enum InjectIdType {
  PROTOCOLS = "airalogy_protocol_ids",
  RECORDS = "airalogy_record_ids",
  DISCUSSIONS = "airalogy_discussion_ids",
  DOCUMENTS = "file_id",
}

export interface ChatMessage {
  role: "assistant" | "user" | "tool"
  content: string | { type: "text" | "image_url", text?: string, image_url?: { url: string } }[]
  tool_calls?: {
    id: string
    type: "function"
    function: {
      name: ToolType
      arguments: string
    }
  }[]
}

export interface ToolArguments {
  [ToolType.INJECT_PROTOCOLS]: {
    [InjectIdType.PROTOCOLS]: string[]
  }
  [ToolType.INJECT_RECORDS]: {
    [InjectIdType.RECORDS]: string[]
  }
  [ToolType.INJECT_DISCUSSIONS]: {
    [InjectIdType.DISCUSSIONS]: string[]
  }
}

export interface ChatInjectContext {
  [ToolType.INJECT_PROTOCOLS]?: {
    enabled: boolean
    [InjectIdType.PROTOCOLS]: string[]
  }
  [ToolType.INJECT_RECORDS]?: {
    enabled: boolean
    [InjectIdType.RECORDS]: string[]
  }
  [ToolType.INJECT_DISCUSSIONS]?: {
    enabled: boolean
    scope?: "protocol" | "project" | "lab" | "public"
    [InjectIdType.DISCUSSIONS]?: string[]
  }
  [ToolType.INJECT_DOCUMENTS]?: {
    enabled: boolean
    [InjectIdType.DOCUMENTS]: string[]
  }
  ephemeral_context?: {
    current_editor_protocol?: CurrentEditorProtocolContext
    current_recorder_record?: CurrentRecorderRecordContext
  }
}

/**
 * Extract context IDs for API requests
 */
function extractContextIds(context?: Chat.ChatSession["context"] | null) {
  const currContext = context
  if (!currContext) {
    return { recordIds: [], protocolIds: [], documentIds: [] }
  }

  const recordIds: string[] = []
  const protocolIds: string[] = []
  const documentIds: string[] = []

  currContext.forEach((item: Chat.ChatContext) => {
    if (item.type === "record") {
      const id = `airalogy.id.record.${item.id}`
      recordIds.push(id)
    }
    else if (item.type === "protocol") {
      const id = `airalogy.id.protocol.${item.id}`
      protocolIds.push(id)
    }
    else if (item.type === "document") {
      const { airalogyFileId } = item as any
      if (airalogyFileId) {
        documentIds.push(airalogyFileId)
      }
    }
  })

  // TODO: no ids for discussion
  return { recordIds, protocolIds, documentIds, discussionIds: [] }
}

/**
 * Creates a context structure for the chat according to the Record QA specification
 * @param payload Configuration object containing protocol, record, and discussion IDs
 * @returns A properly formatted context object following the Record QA specification
 */
export function createChatInjectContext(payload: {
  protocolIds?: {
    ids: string[]
    enabled?: boolean
  }
  recordIds?: {
    ids: string[]
    enabled?: boolean
  }
  discussionIds?: {
    ids?: string[]
    enabled?: boolean
    scope?: "protocol" | "project" | "lab" | "public"
  }
  documentIds?: {
    ids: string[]
    enabled?: boolean
  }
  currentEditorProtocol?: CurrentEditorProtocolContext
  currentRecorderRecord?: CurrentRecorderRecordContext
}): ChatInjectContext {
  const context = {} as ChatInjectContext

  if (payload.protocolIds?.ids.length) {
    context[ToolType.INJECT_PROTOCOLS] = {
      enabled: payload.protocolIds.enabled ?? true,
      [InjectIdType.PROTOCOLS]: payload.protocolIds.ids,
    }
  }

  if (payload.recordIds?.ids.length) {
    context[ToolType.INJECT_RECORDS] = {
      enabled: payload.recordIds.enabled ?? true,
      [InjectIdType.RECORDS]: payload.recordIds.ids,
    }
  }

  if (Array.isArray(payload.discussionIds?.ids) && payload.discussionIds.ids.length) {
    context[ToolType.INJECT_DISCUSSIONS] = {
      enabled: payload.discussionIds.enabled ?? true,
      scope: payload.discussionIds.scope,
      [InjectIdType.DISCUSSIONS]: payload.discussionIds.ids,
    }
  }
  else if (payload.discussionIds?.enabled) {
    context[ToolType.INJECT_DISCUSSIONS] = {
      enabled: payload.discussionIds.enabled,
    }
  }

  if (payload.documentIds?.ids.length) {
    context[ToolType.INJECT_DOCUMENTS] = {
      enabled: payload.documentIds.enabled ?? true,
      [InjectIdType.DOCUMENTS]: payload.documentIds.ids,
    }
  }

  const ephemeralContext: NonNullable<ChatInjectContext["ephemeral_context"]> = {}

  if (payload.currentEditorProtocol?.enabled) {
    ephemeralContext.current_editor_protocol = payload.currentEditorProtocol
  }

  if (payload.currentRecorderRecord?.enabled) {
    ephemeralContext.current_recorder_record = payload.currentRecorderRecord
  }

  if (Object.keys(ephemeralContext).length) {
    context.ephemeral_context = ephemeralContext
  }

  return context
}
const [useProvideChatConfigStore, _useChatConfigStore] = createInjectionState((): ChatProviderContext & { enableDiscussion: Ref<boolean>, discussionScope: Ref<"protocol" | "project" | "lab"> } => {
  const authStore = useAuthStore()
  const baseUrl = computed(() => `${baseURL}/chats`)
  const token = computed(() => authStore.token)
  const enableDiscussion = ref<boolean>(true)
  const discussionScope = ref<"protocol" | "project" | "lab">("protocol")

  const contextDialog: Ref<ContextDialogState> = ref({
    selected: [],
    show: false,
    options: [],
  } as ContextDialogState)
  const contextOptions = ref([])
  const contextDialogEventHandlers = ref({
    "update:show": (show: boolean) => { contextDialog.value.show = show },
    "update:selected": (val: string[]) => { contextDialog.value.selected = val },
    "confirm": () => { /** NOPE */ },
    "selectType": (key: ContextDialogState["type"]) => {
      if (key === "discussion") {
        enableDiscussion.value = !enableDiscussion.value
        return
      }

      contextDialog.value.type = key
      contextDialog.value.show = true
    },
  })

  const userInfo = computed(() => {
    const { avatar_url } = authStore.userInfo || {}
    return {
      avatar: avatar_url,
    }
  })
  const mode = ref<ChatProviderProps["mode"]>("query")
  const postToolResultChat = shallowRef(_postToolResultChat)
  const uploadAttachment = shallowRef(async (file: File) => {
    const response = await postAddAttachments(file)

    return {
      id: response.data?.id || "",
      url: response.data?.url || "",
      filename: response.data?.filename || file.name,
    }
  })
  const stopStream = shallowRef(_stopStream)
  const protocolId = ref("")
  const currentEditorProtocolContext = ref<CurrentEditorProtocolContext>({
    enabled: false,
  })
  const currentRecorderRecordContext = ref<CurrentRecorderRecordContext>({
    enabled: false,
  })
  const createRendererContext = shallowRef(createDefaultRendererContext)

  const createChatContext = shallowRef((context?: Chat.ChatSession["context"] | null) => {
    const { documentIds, protocolIds, recordIds, discussionIds } = extractContextIds(context)

    return createChatInjectContext({
      protocolIds: { ids: protocolIds ?? [], enabled: true },
      recordIds: { ids: recordIds ?? [], enabled: true },
      discussionIds: { ids: discussionIds, enabled: enableDiscussion.value ?? true, scope: discussionScope.value || "protocol" },
      documentIds: { ids: documentIds ?? [], enabled: true },
      currentEditorProtocol: currentEditorProtocolContext.value,
      currentRecorderRecord: currentRecorderRecordContext.value,
    })
  })

  return {
    enableDiscussion,
    discussionScope,
    baseUrl,
    token,
    userInfo,
    contextDialog,
    contextOptions,
    contextDialogEventHandlers,
    postToolResultChat,
    uploadAttachment,
    stopStream,
    mode,
    protocolId,
    currentEditorProtocolContext,
    currentRecorderRecordContext,
    createRendererContext,
    createChatContext,
  }
})

function useChatConfigStore() {
  const state = _useChatConfigStore()
  if (!state)
    throw new Error("useProjectInfoStore must be used after useProvideProjectInfoStore")
  return state
}

function useOrProvideChatConfigStore() {
  try {
    return useChatConfigStore()
  }
  catch (e) {
    console.error(e)
    return useProvideChatConfigStore()
  }
}
export { useChatConfigStore, useOrProvideChatConfigStore, useProvideChatConfigStore }
