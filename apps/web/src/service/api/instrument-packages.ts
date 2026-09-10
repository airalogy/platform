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
export const adapterProfileFields = ["manufacturer", "model", "firmware", "application", "application_version", "os", "architecture", "gateway_version", "python_version"] as const
export type AdapterProfileField = typeof adapterProfileFields[number]
export type AdapterTargetProfile = Record<AdapterProfileField, string | null> & { manufacturer: string, model: string }
export type AdapterComparisonStatus = "declaration_match" | "needs_information" | "conflicts" | "no_declared_model"
export interface AdapterMatchCandidate {
  release: Pick<AdapterRelease, "id" | "lab_id" | "package_key" | "package_version" | "archive_digest" | "state" | "revision">
  comparison: {
    status: AdapterComparisonStatus
    combinations: {
      combination_index: number
      status: AdapterComparisonStatus
      checks: { field: AdapterProfileField, supplied: string | null, declared: string[], status: "matches" | "not_supplied" | "unresolved_declaration" | "conflicts" }[]
      test_declarations: { combination_index: number, reference: string, simulation_only: boolean }[]
    }[]
    hardware_authorized: false
    installation_authorized: false
    qualification_checked: false
  }
}
export interface AdapterMatchResult {
  profile: AdapterTargetProfile
  items: AdapterMatchCandidate[]
  has_more: boolean
  next_offset: number
  hardware_authorized: false
  installation_authorized: false
  qualification_checked: false
  model_called: false
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
export const fetchAdapterPackage = (id: string) => call<AdapterRelease>(`/${id}`)
export const matchAdapterPackages = (labId: string, profile: AdapterTargetProfile, includeRevoked = false, offset = 0) => call<AdapterMatchResult>("/match", { profile, include_revoked: includeRevoked }, { lab_id: labId, offset })
export const previewAdapterImport = (labId: string, requestId: string, file: File) => call<AdapterImportPreview>("/preview", file, { lab_id: labId, request_id: requestId }, { "Content-Type": "application/zip" })
export const confirmAdapterImport = (labId: string, requestId: string, file: File, digest: string) => call<AdapterRelease>("", file, { lab_id: labId, request_id: requestId }, { "Content-Type": "application/zip", "X-Airalogy-Preview-Digest": digest })
export const previewAdapterReview = (id: string, data: AdapterReview) => call<{ preview_digest: string }>(`/${id}/review/preview`, data)
export const confirmAdapterReview = (id: string, data: AdapterReview & { preview_digest: string }) => call<AdapterRelease>(`/${id}/review`, data)
export const fetchAdapterHistory = (id: string) => call<{ items: { revision: number, action: string, reason: string, actor_user_id: string, created_at: string }[] }>(`/${id}/history`)
