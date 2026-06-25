declare namespace Api.Hub {
  type ProjectProtocolInfo = import("@airalogy/shared/types/models/protocol").ProjectProtocolInfo
  interface Protocol extends ProjectProtocolInfo {
    view_count: number
    download_count: number
    created_at: string
  }
  interface Category {
    id: number
    name: string
    description: string
    parent_id: number
    children_count: number
  }
}
