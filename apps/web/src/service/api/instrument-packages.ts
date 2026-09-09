import { request } from "../request"

export interface AdapterInspection {
  archive_digest: string
  manifest_digest: string
  manifest: {
    id: string
    version: string
    entry_point: string
    provenance: { author: string, kind: string, license: string, build_reference: string, sources: string[] }
    commands: { key: string, version: string, risk: string }[]
    limitations: string[]
    files: { path: string, role: string, sha256: string, size_bytes: number }[]
  }
}
export interface AdapterRelease {
  id: string
  lab_id: string
  research_file_id: string
  package_key: string
  package_version: string
  archive_digest: string
  state: "imported" | "approved" | "revoked"
  revision: number
  inspection: AdapterInspection
}
export interface AdapterImportPreview {
  preview_digest: string
  inspection: AdapterInspection
  existing_release_id: string | null
}
export interface AdapterReview {
  expected_revision: number
  operation: "approve_source" | "revoke"
  reason: string
  source_reviewed: boolean
}
async function call<T>(path: string, data?: unknown, params?: Record<string, string | number>, headers?: Record<string, string>) {
  const result = await request<T>({ url: `/instrument-adapter-packages${path}`, method: data === undefined ? "GET" : "POST", data, params, headers, timeout: 150_000 })
  if (result.error)
    throw result.error
  if (!result.data)
    throw new Error("No adapter package response")
  return result.data
}
export const fetchAdapterPackages = (labId: string, offset = 0) => call<{ items: AdapterRelease[], has_more: boolean }>("", undefined, { lab_id: labId, offset })
export const previewAdapterImport = (labId: string, requestId: string, file: File) => call<AdapterImportPreview>("/preview", file, { lab_id: labId, request_id: requestId }, { "Content-Type": "application/zip" })
export const confirmAdapterImport = (labId: string, requestId: string, file: File, digest: string) => call<AdapterRelease>("", file, { lab_id: labId, request_id: requestId }, { "Content-Type": "application/zip", "X-Airalogy-Preview-Digest": digest })
export const previewAdapterReview = (id: string, data: AdapterReview) => call<{ preview_digest: string }>(`/${id}/review/preview`, data)
export const confirmAdapterReview = (id: string, data: AdapterReview & { preview_digest: string }) => call<AdapterRelease>(`/${id}/review`, data)
export const fetchAdapterHistory = (id: string) => call<{ items: { revision: number, action: string, reason: string, actor_user_id: string, created_at: string }[] }>(`/${id}/history`)
