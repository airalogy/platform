import { request } from "../request"

export type RecordExportScope = "lab" | "project" | "protocol"
export type RecordExportFormat = "aira" | "jsonl" | "csv"
export type RecordExportStatus = "pending" | "running" | "succeeded" | "failed" | "cancelled" | "expired"

export interface RecordExportRequest {
  scope_type: RecordExportScope
  lab_id: string
  project_id?: string
  protocol_id?: string
  export_format: RecordExportFormat
  include_revision_history: boolean
  include_attachments?: boolean
  date_from?: string
  date_to?: string
  submitter_user_id?: string
  protocol_version?: string
  record_number?: number
  record_version?: number
  query?: string
}

export interface RecordExportPreview {
  record_count: number
  protocol_count: number
  protocol_version_count: number
  protocol_versions: string[]
  attachment_count: number
  attachment_bytes: number
  csv_eligible: boolean
  warnings: Array<{ code: string, [key: string]: unknown }>
}

export interface RecordExportItem {
  id: string
  lab_id: string
  project_id?: string | null
  protocol_id?: string | null
  scope_type: RecordExportScope
  export_format: RecordExportFormat
  include_revision_history: boolean
  include_attachments: boolean
  options: Record<string, unknown>
  snapshot_at: string
  requested_by_user_id: string
  status: RecordExportStatus
  progress_current: number
  progress_total: number
  progress_percent: number
  record_count: number
  protocol_count: number
  attachment_count: number
  attachment_bytes: number
  output_filename?: string | null
  output_size_bytes?: number | null
  checksum_sha256?: string | null
  warnings: Array<{ code: string, [key: string]: unknown }>
  error?: string | null
  started_at?: string | null
  finished_at?: string | null
  expires_at?: string | null
  seen_at?: string | null
  created_at: string
  download_available: boolean
}

export function previewRecordExport(payload: RecordExportRequest) {
  return request<RecordExportPreview>({
    url: "/record-exports/preview",
    method: "POST",
    data: payload,
    metadata: { showError: false },
  })
}

export function createRecordExport(payload: RecordExportRequest & { idempotency_key: string }) {
  return request<RecordExportItem>({
    url: "/record-exports",
    method: "POST",
    data: payload,
  })
}

export function fetchRecordExports(params: { page?: number, pageSize?: number, unseenOnly?: boolean } = {}) {
  return request<{ items: RecordExportItem[], total_count: number }>({
    url: "/record-exports",
    params: {
      page: params.page || 1,
      page_size: params.pageSize || 20,
      unseen_only: params.unseenOnly || undefined,
    },
    metadata: { showError: false },
  })
}

export function fetchRecordExport(exportId: string) {
  return request<RecordExportItem>({
    url: `/record-exports/${exportId}`,
    metadata: { showError: false },
  })
}

export function fetchRecordExportDownload(exportId: string) {
  return request<{
    url: string
    filename: string
    expires_in_seconds: number
    checksum_sha256?: string | null
  }>({
    url: `/record-exports/${exportId}/download-url`,
    method: "POST",
  })
}

export function markRecordExportSeen(exportId: string) {
  return request<{ seen: boolean }>({
    url: `/record-exports/${exportId}/seen`,
    method: "POST",
    metadata: { showError: false },
  })
}

export function deleteRecordExport(exportId: string) {
  return request<RecordExportItem>({
    url: `/record-exports/${exportId}`,
    method: "DELETE",
  })
}
