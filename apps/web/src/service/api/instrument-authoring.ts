import { request } from "../request"

export interface AuthoringRequest {
  schema: "airalogy.authoring-request.v1"
  id: string
  gateway_id: string
  resource_id: string
  credential_digest: string
  fingerprint: string
  max_iterations: number
  duration_seconds: number
  sandbox: { sdk_digest: string, image: string, timeout_seconds: number }
  spec: { goal: string, factory: string, materials: Array<{ name: string, text: string }>, tests: Record<string, string>, licenses: Record<string, string>, initial_sources: Record<string, string>, manifest: Record<string, unknown> }
}
export interface AuthoringDraft {
  request: AuthoringRequest
  reason: string
  model_processing_consent: boolean
}
export interface AuthoringSummary {
  id: string
  goal: string
  state: "open" | "cancelled" | "expired"
  expires_at: string
  created_at: string
}
export interface AuthoringSession {
  id: string
  request: AuthoringRequest
  effective_state: AuthoringSummary["state"]
  expires_at: string
  turns: Array<{
    id: string
    ordinal: number
    effective_state: "generating" | "generated" | "failed" | "interrupted"
    proposal: { summary: string, sources: Record<string, string>, assumptions: string[], missing_information: string[] } | null
    candidate_digest: string | null
    error: string | null
    report: { passed: boolean, failure_reason: string, untrusted_test_output: string, archive_digest: string | null } | null
  }>
}
async function call<T>(path: string, data?: unknown, params?: Record<string, string | number>) {
  const response = await request<T>({ url: `/instrument-authoring${path}`, method: data === undefined ? "GET" : "POST", data, params })
  if (response.error)
    throw response.error
  if (!response.data)
    throw new Error("Missing authoring response")
  return response.data
}
export const fetchAuthoringSessions = (gatewayId: string, resourceId: string, offset = 0) => call<{ items: AuthoringSummary[], has_more: boolean, next_offset: number }>("", undefined, { gateway_id: gatewayId, resource_id: resourceId, offset })
export const previewAuthoring = (draft: AuthoringDraft) => call<{ preview_digest: string }>("/preview", draft)
export const confirmAuthoring = (draft: AuthoringDraft & { preview_digest: string }) => call<AuthoringSession>("", draft)
export const fetchAuthoringSession = (id: string) => call<AuthoringSession>(`/${id}`)
export const cancelAuthoring = (id: string, fingerprint: string, reason: string) => call<AuthoringSession>(`/${id}/cancel`, { request_fingerprint: fingerprint, reason })
