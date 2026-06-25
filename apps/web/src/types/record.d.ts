declare namespace Api {

  namespace Record {
    interface RecordData {
      id: string
      protocol_id: string
      user_id: string
      protocol_version: string
      number: number
      version: number
      research_variable?: Record<string, any>
      research_step?: Record<string, any>
      research_check?: Record<string, any>
      research_result?: Record<string, any>
      created_at: string
      updated_at: string
    }
  }
}
