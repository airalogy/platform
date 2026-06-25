import type { ChatStoreState } from "@airalogy/components/chat/store"
import type { ChatEvent, ChatResponse, ChatType } from "@airalogy/components/chat/utils/api"
import type { ChatModel } from "@airalogy/shared/enum/chat"
import type { DialogOptions, SelectOption } from "naive-ui"
import type { MaybeRefOrGetter } from "vue"

export { ChatType as ChatRole }

export interface IProps {
  protocolId?: string | null
  enableToolAction?: boolean
  hubSearchDefault?: boolean
  role?: ChatType
  couldChangeRole?: boolean
  chatId?: string | null
  contextSelectOptions?: MaybeRefOrGetter<SelectOption[]>
  source?: Chat.ChatSource
  airalogyId?: string | null
  level?: number
}
export interface IEmits {
  (e: "scrollToBottom", isBottom?: boolean): void
}

export type InputMethod = "text" | "audio"

// Declare a custom type for our controller - we need our own type
// rather than AbortController since we're using different abort pattern
export interface ChatController {
  abort: () => void
}

export interface ChatStreamProcessorParams {
  generator: AsyncGenerator<ChatEvent, ChatResponse, unknown>
  content: string
  messageIndex: number
  requestOptions?: Chat.RequestOptions
}

// Define interface for FastAPI validation errors
export interface ValidationError {
  type: string
  loc: string[]
  msg: string
  input: any
}

export interface ChatState {
  chatId: ComputedRef<string | undefined | null>
  prompt: Ref<string>
  emptyDraftId: Ref<string | null>
  session: ComputedRef<Chat.ChatSession | null | undefined>
  messageList: Ref<Chat.ChatMessage[]>
  messageCount: Ref<number>
  selectedRole: Ref<ChatType>
  selectedModel: Ref<ChatModel>
  deepResearch: Ref<boolean>
  enableThinking: Ref<boolean>
  enableSearch: Ref<boolean>
  enableHubSearch: Ref<boolean>
  inputMethod: Ref<InputMethod>
  controller: Ref<ChatController | null>
  audioBase64: Ref<string | null>
  isEmptyDraft: Ref<boolean>
  context: ComputedRef<Chat.ChatSession["context"] | null>
  source: Ref<Chat.ChatSource>
  history: Ref<Chat.ChatHistory[]>
  allHistoryRecord: Ref<Record<Chat.ChatSource, Chat.ChatHistory[]>>
  modelOptions: Ref<SelectOption[]>
  modelName: ComputedRef<string | undefined>
  roleName: ComputedRef<string | undefined>
  conversationList: Ref<Chat.ChatSession["data"]>
  attachments: Ref<Chat.Attachment[] | null>
  chatStore: ChatStoreState
  defaultChatId: Ref<string | undefined | null>
  airalogyId: Ref<string | undefined | null>
  sourceRef: MaybeRefOrGetter<Chat.ChatSource>
  roleRef: MaybeRefOrGetter<ChatType>
  loading: Ref<boolean>
  startLoading: () => void
  endLoading: () => void
}

export interface ChatAPI {
  endpoint: Ref<string>
  fieldInputEndpoint: Ref<string>
  sttEndpoint: Ref<string>
  stopStream?: (payload: { chatId: string }) => Promise<void>
  baseUrl: Ref<string>
  token: Ref<string>
}

export interface ChatHistoryOperations {
  loadChat: (item: Chat.ChatHistory) => Promise<Chat.ChatSession | undefined>
  deleteHistory: (uuid: string, type?: "dialog" | "popconfirm", options?: DialogOptions) => void
  editHistory: (uuid: string, title: string) => void
  exportHistory: (uuid: string) => void
  clearHistory: () => void
  clearMessages: () => void
}

export interface ChatMutations {
  clearActive: () => void
  updateContext: (value: Chat.ChatContext[] | null) => void
  handleDraftMessage: (uuid: string, draftMessage?: Chat.ChatMessage) => void
}

export interface ChatHandlers {
  handleSubmit: (message: string, role?: ChatType, model?: ChatModel, parentIndex?: number | null) => Promise<void>
  handleRegenerate: (branch: Chat.ChatMessage) => Promise<void>
  handleContinue: (branch: Chat.ChatMessage) => Promise<void>
  handleCreateBranch: (branch: Chat.ChatMessage) => Promise<void>
  handleSwitchBranch: (branch: Chat.ChatMessage, targetBranchIndex?: number) => Promise<void>
  handleClear: () => void
  handleStop: () => void
  handleDeleteMessage: (branch: Chat.ChatMessage) => void
  handleAddNewSession: (targetUuid?: string, type?: Chat.ChatSource) => void
  handleResent: (branch: Chat.ChatMessage, text?: string) => Promise<void>
  handleCreateEditBranch: (branch: Chat.ChatMessage, editedText: string) => Promise<void>
}

export interface ChatSessionNavigation {
  currentMessagePath: ComputedRef<number[]>
  latestMessageId: ComputedRef<number | null>
  latestSentMessageId: ComputedRef<number | null>
  createBranch: (session: Chat.ChatSession, fromMessageIndex: number, content: string, attachments?: Chat.Attachment[]) => number | null
  switchBranch: (session: Chat.ChatSession, messageIndex: number, targetBranchIndex: number) => boolean
  deleteMessageWithHierarchy: (session: Chat.ChatSession, messageIndex: number) => boolean
  getBranchInfo: (session: Chat.ChatSession, messageIndex: number) => any
  getLatestMessageId: (session: Chat.ChatSession) => number | null
  getLatestSentMessageId: (session: Chat.ChatSession) => number | null
  getMessagePath: (session: Chat.ChatSession) => number[]
  getIsLastShowingUserMessage: (session: Chat.ChatSession, messageIndex: number) => boolean
  updateFakeMessageIndex: (session: Chat.ChatSession, oldIndex: number, newIndex: number) => boolean
}

export interface ChatStream {
  processChatStream: (params: ChatStreamProcessorParams & { chat: Chat.ChatSession }) => Promise<{
    id?: string | undefined
    chatId?: string | undefined
    conversationId?: string | undefined
    messages?: any[] | undefined
  }>
  processChatStreamByUUID: (params: ChatStreamProcessorParams & { chatUuid: string }) => Promise<{
    id?: string | undefined
    chatId?: string | undefined
    conversationId?: string | undefined
    messages?: any[] | undefined
  }>
}
