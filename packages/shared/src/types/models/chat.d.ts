import type { ChatModelConfig, ChatModel as ChatModelEnum, ChatModelType, ChatType as ChatTypeEnum } from "@airalogy/shared/enum/chat"

export type ChatModel = ChatModelEnum
export type ChatType = ChatTypeEnum
export type { ChatModelConfig, ChatModelType }
export interface ChatResponse {
  created_at: string
  messages: History[]
  id: string
  protocol_id: string
  updated_at: string
  user_id: string
  type: number
  context?: {
    inject_airalogy_protocols?: {
      airalogy_protocol_ids: string[]
    }
    inject_airalogy_records?: {
      airalogy_record_ids: string[]
    }
    inject_airalogy_discussions?: {
      airalogy_discussion_ids: string[]
    }
  }
  [property: string]: any
}

export interface History {
  content: null | string
  role: string
  tool_calls?: ToolCall[]
  parent_id?: string
  message_id?: string
  [property: string]: any
}

export interface ToolCall {
  function?: Function
  id?: string
  type?: string
  [property: string]: any
}

export interface Function {
  arguments: string
  name: string
  [property: string]: any
}
