import { request } from "../request"

export interface SurveyReport {
  schema: "airalogy.interface-survey.v1"
  id: string
  preview_digest: string
  target: { application: string, version: string, title: string, locale: string, kind: "file" | "url" }
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
  route: "browser" | "api_or_sdk" | "manual" | "unknown"
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
  request: { fingerprint: string, spec: { goal: string, report: SurveyReport } }
  effective_state: SurveySummary["state"]
  expires_at: string
  can_analyze?: boolean
  turns: Array<{ id: string, effective_state: "generating" | "generated" | "failed" | "interrupted", proposal: SurveyAnalysis | null, error: string | null }>
}
export interface SurveyDraft {
  id: string
  gateway_id: string
  resource_id: string
  goal: string
  report: SurveyReport
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
export const exportSurvey = (id: string) => call<{ schema: "airalogy.survey-analysis-export.v1", session_id: string, turn_id: string, capture_digest: string, analysis: SurveyAnalysis }>(`/${id}/export`)
