import { request } from "../request"

export interface ActivationDraft {
  id: string
  qualification_id: string
  expected_active_id: string | null
  commands: string[]
  expires_at: string
  reason: string
  activation_confirmed: boolean
}
export interface ActivationRecord {
  id: string
  binding_id: string
  qualification_id?: string
  effective_state: "authorized" | "invalid" | "revoked" | "redacted"
  details_redacted?: boolean
  plan?: { expires_at: string, reason: string, target: Record<string, string>, descriptor: { archive_digest: string, installation_id: string }, previous_activation_id: string | null }
  commands?: { key: string, version: string, revision: number }[]
}
async function call<T>(id: string, path: string, data?: unknown, params?: Record<string, number>) {
  const result = await request<T>({ url: `/instrument-installations/${id}/activations${path}`, method: data === undefined ? "GET" : "POST", data, params })
  if (result.error)
    throw result.error
  if (!result.data)
    throw new Error("No activation response")
  return result.data
}
export const fetchActivations = (id: string, offset = 0) => call<{ items: ActivationRecord[], has_more: boolean, next_offset: number, current_id: string | null }>(id, "", undefined, { offset })
export const previewActivation = (id: string, draft: ActivationDraft) => call<Record<string, unknown> & { preview_digest: string }>(id, "/preview", draft)
export const confirmActivation = (id: string, draft: ActivationDraft, digest: string) => call<ActivationRecord>(id, "", { ...draft, preview_digest: digest })
export const previewActivationRevocation = (id: string, activationId: string, reason: string) => call<{ preview_digest: string }>(id, `/${activationId}/revoke/preview`, { expected_revision: 1, reason })
export const confirmActivationRevocation = (id: string, activationId: string, reason: string, digest: string) => call(id, `/${activationId}/revoke`, { expected_revision: 1, reason, preview_digest: digest })
