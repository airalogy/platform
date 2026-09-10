import { request } from "../request"

export interface ApplicationCandidatesReport {
  schema: "airalogy.application-candidates.v1"
  id: string
  source_digest: string
  scope: "explicitly_selected_metadata_only"
  candidates: Array<{ id: string, name: string | null, display_name: string | null, bundle_id: string | null, version: string | null, build_version: string | null, info_sha256: string | null }>
}
export interface ApplicationSelectionAnalysis {
  summary: string
  recommendations: Array<{ candidate_id: string, rationale: string, evidence_fields: Array<"name" | "display_name" | "bundle_id" | "version" | "build_version"> }>
  limitations: string[]
  missing_information: string[]
}
export type SoftwareReport = SurveyReport | ApplicationCandidatesReport
export interface SurveyReport {
  schema: "airalogy.interface-survey.v1"
  id: string
  preview_digest: string
  target: { application: string, version: string, title: string, locale: string, kind: "file" | "url" | "native_macos" }
  capture_values: boolean
  controls: Array<{ id: string, label: string, role: string, locator: { kind: string, name: string, role?: string } | null, read: string | null, value: string | boolean | null, enabled: boolean }>
  omitted_private: number
  limitations: string[]
}
export interface SurveyAnalysis {
  summary: string
  features: Array<{ control_id: string, interpretation: string, basis: "observed" | "inferred", risk: "read_only" | "state_change" | "unknown" }>
  read_controls: string[]
  identity_control: string | null
  route: "browser" | "native_accessibility" | "api_or_sdk" | "manual" | "unknown"
  limitations: string[]
  missing_information: string[]
}
export interface SurveySummary {
  id: string
  goal: string
  state: "open" | "cancelled" | "expired"
  expires_at: string
}
export interface SurveySession {
  id: string
  request: { fingerprint: string, spec: { goal: string, report: SoftwareReport } }
  effective_state: SurveySummary["state"]
  expires_at: string
  can_analyze?: boolean
  turns: Array<{ id: string, effective_state: "generating" | "generated" | "failed" | "interrupted", proposal: SurveyAnalysis | ApplicationSelectionAnalysis | null, error: string | null }>
}
export interface SurveyDraft {
  id: string
  gateway_id: string
  resource_id: string
  goal: string
  report: SoftwareReport
  reason: string
  model_processing_consent: boolean
  capture_reviewed: boolean
}
async function call<T>(path: string, data?: unknown, params?: Record<string, string | number>) {
  const result = await request<T>({ url: `/instrument-surveys${path}`, method: data === undefined ? "GET" : "POST", data, params, timeout: path.endsWith("/analyze") ? 70000 : 10000, metadata: { noRetry: true, showError: false } })
  if (result.error)
    throw result.error
  if (!result.data)
    throw new Error("Missing survey response")
  return result.data
}
export const listSurveys = (gatewayId: string, resourceId: string, offset = 0) => call<{ items: SurveySummary[], has_more: boolean, next_offset: number }>("", undefined, { gateway_id: gatewayId, resource_id: resourceId, offset })
export const previewSurvey = (data: SurveyDraft) => call<{ preview_digest: string, capture_digest: string }>("/preview", data)
export const confirmSurvey = (data: SurveyDraft & { preview_digest: string }) => call<SurveySession>("", data)
export const getSurvey = (id: string) => call<SurveySession>(`/${id}`)
export const analyzeSurvey = (id: string, turnId: string) => call<SurveySession["turns"][number]>(`/${id}/analyze`, { id: turnId })
export const cancelSurvey = (id: string, fingerprint: string, reason: string) => call<SurveySession>(`/${id}/cancel`, { request_fingerprint: fingerprint, reason })
export const exportSurvey = (id: string) => call<{ schema: "airalogy.survey-analysis-export.v1" | "airalogy.application-selection-export.v1", session_id: string, turn_id: string, capture_digest: string, analysis: SurveyAnalysis | ApplicationSelectionAnalysis }>(`/${id}/export`)
