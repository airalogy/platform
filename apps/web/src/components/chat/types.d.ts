import type { ProtocolModels } from "@airalogy/shared/types"

export interface ChatMessage {
  dateTime: string
  text: string
  inversion: boolean
  error: boolean
  loading: boolean
  conversationOptions?: {
    conversationId?: string
    parentMessageId?: string
    type?: 1 | 2
  } | null
  requestOptions: {
    prompt: string
    options: any
  }
  tool?: any
}

export interface ChatState {
  active: string | null
  history: Chat.ChatHistory[]
  chat: Record<string, ChatMessage[]>
}

export interface ExtendedRecordInfo extends ProtocolModels.RecordInfo {
  lab_uid: string
  project_uid: string
  research_uid: string
}
