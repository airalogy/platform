declare namespace Api {
  namespace ProtocolFolder {
    interface Folder {
      id: number
      project_id: string
      name: string
      description: string
      create_user_id: string
      created_at: string
      updated_at: string
      protocols_count?: number
    }
  }
}
