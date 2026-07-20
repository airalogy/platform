import type { RenderMode } from "@airalogy/aimd-core/types"
import type { ProtocolModels } from "@airalogy/shared"
import type { ChatModel } from "@airalogy/shared/enum/chat"
import type { CascaderOption, SelectOption } from "naive-ui"
import type { Component, InjectionKey, MaybeRefOrGetter, ToRefs } from "vue"
import { pick } from "lodash-es"
import { inject, provide } from "vue"

/**
 * @deprecated RendererContext is no longer used since markdown-preview migrated to unified system
 */
export interface LegacyRendererContext {
  md: null
  rules: Record<string, unknown>
  nodeRenderer: () => null
}
export interface CurrentEditorProtocolContext {
  enabled: boolean
  title?: string
  protocol_aimd?: string
  model_py?: string
  assigner_py?: string
  protocol_toml?: string
}

export interface CurrentRecorderRecordFieldSummary {
  scope: string
  field_id: string
  title?: string
  type?: string
  filled: boolean
  value?: unknown
}

export interface CurrentRecorderRecordContext {
  enabled: boolean
  title?: string
  protocol_id?: string
  protocol_uid?: string
  protocol_name?: string
  readonly?: boolean
  filled_count?: number
  empty_count?: number
  field_summary?: CurrentRecorderRecordFieldSummary[]
  record_data?: Record<string, unknown>
  truncated?: boolean
}

export interface ChatProviderProps<InjectContext = any> {
  postToolResultChat: (payload: any) => Promise<any>
  uploadAttachment: (file: File) => Promise<{ id: string, url?: string | null, filename?: string | null }>
  stopStream: (payload: { chatId: string }) => Promise<void>
  baseUrl: string
  token: string
  mode: "query" | "param"
  protocolId: string
  userInfo: {
    avatar?: string | null
  }
  contextDialog: ContextDialogState
  contextDialogEventHandlers: Record<string, (...args: any[]) => void>
  contextOptions: (SelectOption & { key: ContextDialogState["type"] })[]
  createChatContext: (context?: Chat.ChatContext[] | null) => InjectContext
  currentEditorProtocolContext: CurrentEditorProtocolContext
  currentRecorderRecordContext: CurrentRecorderRecordContext
  enabledModels: ChatModel[]
  /**
   * @deprecated This function is no longer used since markdown-preview migrated to unified system.
   * Kept for backward compatibility only.
   */
  createRendererContext?: (protocol?: Partial<ProtocolModels.ProtocolInfo>, mode?: MaybeRefOrGetter<RenderMode>) => LegacyRendererContext
}

export type ContextDialogStateOption = CascaderOption & { component?: Component, label: string, value: string, removable?: boolean }
export interface ContextDialogState {
  show: boolean
  selected: string[]
  type?: "record" | "protocol" | "document" | "discussion"
  options: ContextDialogStateOption[]
  defaultSelectedPath?: string
  defaultSelectedOptions?: CascaderOption[]
  readonlyList?: string[]
}
export type ChatProviderContext = ToRefs<Required<ChatProviderProps>>
export const ChatProviderKey: InjectionKey<ChatProviderContext> = Symbol("ChatProvider")

export function createDefaultRendererContext(): LegacyRendererContext {
  return {
    md: null,
    rules: {},
    nodeRenderer: () => null,
  }
}

export function createDefaultCurrentEditorProtocolContext(): CurrentEditorProtocolContext {
  return {
    enabled: false,
  }
}

export function createDefaultCurrentRecorderRecordContext(): CurrentRecorderRecordContext {
  return {
    enabled: false,
  }
}

export function useProvideChatProvider(config: ChatProviderContext) {
  const context = pick(config, ["postToolResultChat", "uploadAttachment", "stopStream", "baseUrl", "token", "mode", "protocolId", "userInfo", "contextDialog", "contextDialogEventHandlers", "contextOptions", "createChatContext", "currentEditorProtocolContext", "currentRecorderRecordContext", "enabledModels", "createRendererContext"])

  provide(ChatProviderKey, context)

  return context
}

export function useChatProvider() {
  const context = inject(ChatProviderKey)
  if (!context) {
    throw new Error("useChatProvider must be used within a ChatProvider")
  }
  return context
}

export function defaultReject(...args: any[]) {
  return Promise.reject("Function not implement.")
}
