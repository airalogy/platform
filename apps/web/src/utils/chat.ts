import type { ChatModelConfig, ChatModelType } from "@airalogy/shared/types/models/chat"
import { ChatModel } from "@/enum/model"
import { nanoid } from "nanoid"

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

/**
 * Converts ChatModel enum to ChatModelConfig object
 * @param model The ChatModel enum value
 * @param options Additional options for the model
 * @returns A properly formatted ChatModelConfig object
 */
export function chatModelToConfig(
  model?: ChatModel,
  options?: { enableThinking?: boolean, enableSearch?: boolean },
): ChatModelConfig {
  let modelType: ChatModelType = 1

  switch (model) {
    case ChatModel.BASIC:
      modelType = 1 // basic
      break
    case ChatModel.PLUS:
      modelType = 2 // plus
      break
    case ChatModel.PRO:
      modelType = 3 // pro
      break
    case ChatModel.GPT:
      modelType = 4 // gpt
      break
    default:
      modelType = 1 // basic
  }

  return {
    model_type: modelType,
    enable_thinking: options?.enableThinking ?? false,
    enable_search: options?.enableSearch ?? false,
  }
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

export interface ChatEphemeralContext {
  current_editor_protocol?: CurrentEditorProtocolContext
  current_recorder_record?: CurrentRecorderRecordContext
}

export interface ChatContext {
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
  ephemeral_context?: ChatEphemeralContext
}

/**
 * Creates a tool call message according to the Airalogy Record QA specification
 * @param type The type of tool to call (inject_airalogy_protocols, inject_airalogy_records, or inject_airalogy_discussions)
 * @param args The arguments for the tool, must match the corresponding type's argument structure
 * @returns A properly formatted tool call message following the Record QA specification
 */
export function createToolCallMessage<T extends keyof ToolArguments>(
  type: T,
  args: ToolArguments[T],
): ChatMessage {
  return {
    role: "assistant",
    content: "",
    tool_calls: [{
      id: `call_${nanoid()}`,
      type: "function",
      function: {
        name: type,
        arguments: JSON.stringify(args),
      },
    }],
  }
}

/**
 * Creates a tool response message
 * @param content The content of the tool response
 * @returns A properly formatted tool message
 */
export function createToolMessage(content: string): ChatMessage {
  return {
    role: "tool",
    content,
  }
}

/**
 * Creates a user message
 * @param content The content of the user message
 * @returns A properly formatted user message
 */
export function createUserMessage(content: string, attachments?: string[]): ChatMessage {
  if (attachments?.length) {
    return {
      role: "user",
      content: [{
        type: "text",
        text: content,
      }, {
        type: "image_url",
        image_url: {
          url: attachments[0],
        },
      }],
    }
  }
  return {
    role: "user",
    content,
  }
}

/**
 * Creates a complete message structure for injecting protocols
 * @param protocolIds Array of protocol IDs to inject
 * @returns Array of messages following the Record QA specification
 */
export function createProtocolInjectionMessages(protocolIds: string[]): ChatMessage[] {
  const toolCall = createToolCallMessage(ToolType.INJECT_PROTOCOLS, {
    airalogy_protocol_ids: protocolIds,
  })

  return [toolCall]
}

/**
 * Creates a complete message structure for injecting records
 * @param recordIds Array of record IDs to inject
 * @returns Array of messages following the Record QA specification
 */
export function createRecordInjectionMessages(recordIds: string[]): ChatMessage[] {
  const toolCall = createToolCallMessage(ToolType.INJECT_RECORDS, {
    airalogy_record_ids: recordIds,
  })

  return [toolCall]
}

/**
 * Creates a complete message structure for injecting discussions
 * @param discussionIds Array of discussion IDs to inject
 * @returns Array of messages following the Record QA specification
 */
export function createDiscussionInjectionMessages(discussionIds: string[]): ChatMessage[] {
  const toolCall = createToolCallMessage(ToolType.INJECT_DISCUSSIONS, {
    airalogy_discussion_ids: discussionIds,
  })

  return [toolCall]
}

/**
 * Creates a complete message structure for a conversation with protocol and record injection
 * @param userMessage The user's message content
 * @param protocolIds Array of protocol IDs to inject
 * @param recordIds Array of record IDs to inject
 * @returns Array of messages following the Record QA specification
 */
export function createCompleteConversationMessages(
  payload: {
    userMessage: string
    protocolIds?: string[]
    recordIds?: string[]
  },
  // discussionIds?: string[],
): ChatMessage[] {
  const { userMessage = "", protocolIds = [], recordIds = [] } = payload

  const messages: ChatMessage[] = [createUserMessage(userMessage)]

  if (protocolIds?.length) {
    messages.push(...createProtocolInjectionMessages(protocolIds))
  }

  if (recordIds?.length) {
    messages.push(...createRecordInjectionMessages(recordIds))
  }

  // if (discussionIds?.length) {
  //   messages.push(...createDiscussionInjectionMessages(discussionIds))
  // }

  return messages
}

/**
 * Creates a context structure for the chat according to the Record QA specification
 * @param payload Configuration object containing protocol, record, and discussion IDs
 * @returns A properly formatted context object following the Record QA specification
 */
export function createChatContext(payload: {
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
}): ChatContext {
  const context: ChatContext = {}

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

  const ephemeralContext: NonNullable<ChatContext["ephemeral_context"]> = {}

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
