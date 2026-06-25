export interface AttachmentItemResponse {
  id: string
  filename: string
  url: string
  content_type?: string | null
  size_bytes?: number | null
  sha256?: string | null
  storage_backend?: string | null
  storage_namespace?: string | null
}

export interface AttachmentItem {
  id: string
  filename: string
  url: string
  airalogy_file_id: string
  content_type?: string | null
  size_bytes?: number | null
  sha256?: string | null
  storage_backend?: string | null
  storage_namespace?: string | null
}
