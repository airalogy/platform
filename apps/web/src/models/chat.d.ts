declare namespace Api {
  namespace Chat {

    interface ChatResponse {
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

    interface History {
      content: null | string
      role: string
      tool_calls?: ToolCall[]
      parent_id?: string
      message_id?: string
      [property: string]: any
    }

    interface ToolCall {
      function?: Function
      id?: string
      type?: string
      [property: string]: any
    }

    interface Function {
      arguments: string
      name: string
      [property: string]: any
    }
  }
}
