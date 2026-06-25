import type { ChatModels, ProtocolModels } from "@airalogy/shared"
import type { UseEventBusReturn } from "@vueuse/core"
import type { UploadFileInfo } from "naive-ui"
import type { ContextItem, ContextSubmenuItem, CustomCommand, FetchFunction, LoadSubmenuItemsArgs } from "../chat/providers/types"
import type MentionType from "../markdown-editor/modules/mention/type"

declare global {
  export namespace Chat {
    export type EventBus = UseEventBusReturn<any, any>
    export type ChatSource = "discussion" | "record" | "protocol" | "global" | "editor" | "hub"

    export type Example = string | { text: string, presetResponse?: string }

    export type ComboBoxItemType =
      | "contextProvider"
      | "slashCommand"
      | "file"
      | "query"
      | "folder"
      | "action"

    export type ComboBoxSubAction = MentionType.ComboBoxSubAction

    export type ComboBoxItem = MentionType.ComboBoxItem

    export interface ContextProviderExtras {
      config: Record<string, any>
      fullInput: string
      // embeddingsProvider: EmbeddingsProvider
      // reranker: Reranker | undefined
      // llm: ILLM
      // ide: IDE
      // selectedCode: RangeInFile[]
      fetch: FetchFunction
      eventBus: EventBus
      eventName: string
    }

    export type ContextProviderType = MentionType.ContextProviderType

    export interface ContextProvider {
      get description(): ContextProviderDescription

      getContextItems: (
        query: string,
        extras: Partial<ContextProviderExtras>,
      ) => Promise<ContextItem[]>

      loadSubmenuItems: (args: LoadSubmenuItemsArgs) => Promise<ContextSubmenuItem[]>
    }

    export interface ContextProviderDescription {
      title: string
      displayTitle: string
      description: string
      renderInlineAs?: string
      type: ContextProviderType
    }
    export interface ChatMessage {
      dateTime: number
      text: string
      /**
       * @description true - user message
       * @description false - assistant message
       */
      inversion?: boolean
      error?: boolean
      loading?: boolean
      editing?: boolean
      tool?: ChatModels.History | null
      conversationOptions?: ConversationRequest | null
      requestOptions: RequestOptions
      context?: ChatContext[]
      cancelled?: boolean
      attachments?: Attachment[]
      isDraft?: boolean
      errorMessage?: string
      resent?: boolean
      regenerate?: boolean
      presetAnswer?: string
      // childBranches?: number[]
      // Enhanced branching support
      // branchPath?: number[]
      // activeBranchIndex?: number
      // branchIndex?: number
      // depth: number
      originalIndex: number
      parentIndex: number | null
      childIndices: number[]
      currentChildIndex: number
    }

    export interface ChatConfig {
      customCommands: CustomCommand[]
      contextProviders: ContextProviderWithParams[]
      slashCommands: { title: string, description: string, type: ComboBoxItemType }[]
    }

    export type ContextProviderName = "variable" | "discussion" | "protocol" | "record"

    export interface ContextProviderWithParams extends ContextProvider {
      name: ContextProviderName
      id?: string
      params: { [key: string]: any }
    }

    export interface ChatHistory {
      title: string
      isEdit: boolean
      uuid: string
      source: ChatSource
      time: number
      airalogyId?: string | null
      serverId?: string
    }

    export interface ProtocolDocument {
      id: string
      name: string
      size: number
      type: string
      content?: string
      status: "init" | "modified" | "uploaded" | "error" | "pending" | "success"
      createdAt: Date
      airalogyFileId?: string
      url?: string
      protocolId?: string | number
      metadata?: Record<string, any>
      modelId?: string // Track associated Monaco model ID
      path: string // Path where document is stored in the WebContainer file system
    }

    export interface ChatBasicContext<T extends "record" | "protocol" | "document", R extends ProtocolModels.RecordInfo | Omit<ProtocolModels.ProjectProtocolInfo, "history" | "package"> | ProtocolDocument> {
      type: T
      /**
       * Airalogy ID with `airalogy.id.` prefix
       */
      airalogyId: string
      /**
       * UUID
       */
      id: string
      item: R
      lab?: {
        name: string
        uid: string
        id: string
      }
      project?: {
        name: string
        uid: string
        id: string
      }
      protocol?: {
        name: string
        uid: string
        id: string
      }
      isLocal?: boolean
      removable: boolean
    }

    export interface ChatRecordContext extends ChatBasicContext<"record", ProtocolModels.RecordInfo> {
    }

    export interface ChatProtocolContext extends ChatBasicContext<"protocol", Omit<ProtocolModels.ProjectProtocolInfo, "history" | "package">> {
    }

    export interface ChatDocumentContext extends ChatBasicContext<"document", ProtocolDocument> {
    }

    export type ChatContext = ChatRecordContext | ChatProtocolContext | ChatDocumentContext

    export interface ChatSession {
      uuid: string
      data: ChatMessage[]
      context?: ChatContext[]
      source: ChatSource
      airalogyId?: string | null
      serverId?: string
      role?: ChatModels.ChatType
      config: ChatConfig
      rootBranchIndex: number
      rootBranchIndices: number[]
    }

    interface ChatState {
      active: string | null
      isInit: boolean
      history: ChatHistory[]
      session: ChatSession[]
    }

    interface ConversationRequest {
      conversationId?: string
      parentMessageId?: string
      context?: {
        [key: string]: any
      }
      model?: string | ChatModels.ChatModel
    }

    export interface ConversationResponse {
      conversationId: string
      detail: {
        choices: { finish_reason: string, index: number, logprobs: any, text: string }[]
        created: number
        id: string
        model: string
        object: string
        usage: { completion_tokens: number, prompt_tokens: number, total_tokens: number }
      }
      id: string
      parentMessageId: string
      role: string
      text: string
    }

    export interface PromptState {
      promptList: string[]
    }

    export type Attachment = UploadFileInfo & {
      isUploading?: boolean
      serverId?: string
    }

    export interface RequestOptions {
      prompt: string
      options?: ConversationRequest | null
      role?: ChatModels.ChatType
      attachments?: Attachment[]
      parentId?: string
      id?: string
      done?: boolean
    }
    export interface Message {
      dateTime: number
      text: string
      inversion?: boolean
      error?: boolean
      loading?: boolean
      tool?: ChatModels.History | null
      conversationOptions?: ConversationRequest | null
      requestOptions: RequestOptions
      context?: string[]
      cancelled?: boolean
      attachments?: Attachment[]
      isDraft?: boolean
    }
  }
}

export { ChatModels, ProtocolModels }
