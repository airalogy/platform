import { request } from "../request"

export type QualificationScope = "simulation" | "read_only" | "controlled"
export type QualificationCheckKind = "identity" | "output" | "completion" | "parameter_readback" | "safe_stop" | "manual_takeover" | "interlocks"
export interface QualificationCheck { kind: QualificationCheckKind, method: string, expected: string, observed: string, passed: boolean }
export interface QualificationReport {
  id: string
  scope: QualificationScope
  evidence_origin: "manual_observation" | "independent_test" | "package_self_test"
  target: Record<"identity_reference" | "firmware" | "application" | "application_version" | "driver_version" | "os_version", string>
  commands: { key: string, version: string, checks: QualificationCheck[] }[]
  evidence_file_ids: string[]
  assessed_at: string
  expires_at: string
  reason: string
  independent_review_confirmed: boolean
  physical_tests_authorized: boolean
}
export interface QualificationRecord {
  id: string
  scope: QualificationScope
  outcome: "passed" | "failed"
  effective_state: "qualified" | "simulation_only" | "failed" | "expired" | "revoked" | "installation_not_current" | "installation_changed" | "gateway_identity_changed" | "equipment_changed" | "source_changed" | "source_unavailable" | "evidence_unavailable"
  report?: QualificationReport
  assessor?: { id: string, name: string }
  assessed_at?: string
  details_redacted?: boolean
  created_at: string
  expires_at: string
  revoked_at: string | null
}
export interface QualificationContext {
  installed_at: string
  commands: { key: string, version: string, name: string, risk: string, simulation_only: boolean }[]
}
export interface QualificationPreview { preview_digest: string, report: QualificationReport, pins: Record<string, unknown> }
async function call<T>(bindingId: string, path: string, data?: unknown, params?: Record<string, number>) {
  const result = await request<T>({ url: `/instrument-installations/${bindingId}${path}`, method: data === undefined ? "GET" : "POST", data, params })
  if (result.error)
    throw result.error
  if (!result.data)
    throw new Error("No qualification response")
  return result.data
}
export const fetchQualificationContext = (id: string) => call<QualificationContext>(id, "/qualification-context")
export const fetchQualifications = (id: string, offset = 0) => call<{ items: QualificationRecord[], has_more: boolean, next_offset: number }>(id, "/qualifications", undefined, { offset })
export const previewQualification = (id: string, report: QualificationReport) => call<QualificationPreview>(id, "/qualifications/preview", report)
export const confirmQualification = (id: string, report: QualificationReport, digest: string) => call<QualificationRecord>(id, "/qualifications", { ...report, preview_digest: digest })
export const previewQualificationRevocation = (id: string, qualificationId: string, reason: string) => call<{ preview_digest: string }>(id, `/qualifications/${qualificationId}/revoke/preview`, { expected_revision: 1, reason })
export const confirmQualificationRevocation = (id: string, qualificationId: string, reason: string, digest: string) => call(id, `/qualifications/${qualificationId}/revoke`, { expected_revision: 1, reason, preview_digest: digest })
