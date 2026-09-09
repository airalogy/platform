import { request } from "../request"

export interface ExplorationRequest {
  schema: "airalogy.interface-exploration.v1"
  id: string
  gateway_id: string
  resource_id: string
  credential_digest: string
  fingerprint: string
  max_iterations: number
  duration_seconds: number
  spec: {
    goal: string
    local_preview_digest: string
    target: { application: string, version: string, kind: "file" | "url" }
    controls: Array<{ id: string, label: string, read: string }>
    states: Array<Record<string, unknown>>
    actions: Array<Record<string, unknown>>
    success: Array<Record<string, unknown>>
  }
}
export interface ExplorationSummary {
  id: string
  goal: string
  state: "open" | "cancelled" | "expired"
  expires_at: string
}
export interface ExplorationSession {
  id: string
  request: ExplorationRequest
  effective_state: ExplorationSummary["state"]
  expires_at: string
  turns: Array<{
    id: string
    ordinal: number
    effective_state: "generating" | "generated" | "failed" | "interrupted"
    proposal: { kind: "act" | "finish" | "needs_information", action_index: number | null, summary: string, missing_information: string[] } | null
    report: { outcome: string, after: unknown } | null
    input: unknown
    error: string | null
  }>
}
export interface ExplorationDraft {
  request: ExplorationRequest
  reason: string
  model_processing_consent: boolean
  local_actions_reviewed: boolean
}
async function call<T>(path: string, data?: unknown, params?: Record<string, string | number>) {
  const result = await request<T>({ url: `/instrument-exploration${path}`, method: data === undefined ? "GET" : "POST", data, params })
  if (result.error)
    throw result.error
  if (!result.data)
    throw new Error("Missing interface-development response")
  return result.data
}
export const listExplorations = (gatewayId: string, resourceId: string, offset = 0) => call<{ items: ExplorationSummary[], has_more: boolean, next_offset: number }>("", undefined, { gateway_id: gatewayId, resource_id: resourceId, offset })
export const previewExploration = (data: ExplorationDraft) => call<{ preview_digest: string }>("/preview", data)
export const confirmExploration = (data: ExplorationDraft & { preview_digest: string }) => call<ExplorationSession>("", data)
export const getExploration = (id: string) => call<ExplorationSession>(`/${id}`)
export const cancelExploration = (id: string, fingerprint: string, reason: string) => call<ExplorationSession>(`/${id}/cancel`, { request_fingerprint: fingerprint, reason })
