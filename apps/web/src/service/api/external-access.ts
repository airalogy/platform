import { request } from "../request"

export interface ExternalPolicy { enabled: boolean, blocked_fields: string[], revision: number }
export interface ExternalGrant {
  id: string
  name: string
  project_id: string
  scopes: string[]
  token_prefix: string
  expires_at: string
  revoked_at: string | null
}
export interface ExternalOperation {
  id: string
  kind: string
  state: string
  grant_id?: string
  expires_at: string
  digest?: string
  tool_name?: string
  summary?: {
    project_name: string
    protocol_name: string
    protocol_version?: string
    row_count?: number
    record_id?: string
    expected_version?: number
    changes?: Record<string, { before: unknown, after: unknown }>
    reason?: string
  }
  payload?: { csv?: string, reason?: string, changes?: Record<string, unknown> }
  result?: { links?: string[] }
}
export interface ExternalDashboard {
  projects: Array<{ id: string, name: string, lab_id: string, enabled: boolean }>
  grants: ExternalGrant[]
  operations: ExternalOperation[]
  audit: Array<{ id: string, event: string, created_at: string, grant_id: string | null }>
}

async function data<T>(options: Parameters<typeof request<T>>[0]): Promise<T> {
  const result = await request<T>({ ...options, metadata: { showError: false } })
  if (result.error || result.data === null)
    throw result.error || new Error("No external access response")
  return result.data
}

export const getExternalDashboard = () => data<ExternalDashboard>({ url: "/external-access/dashboard" })
export function createExternalGrant(payload: { name: string, project_id: string, scopes: string[], expires_in_days: number }) {
  return data<{ grant: ExternalGrant, token: string }>({ url: "/external-access/grants", method: "POST", data: payload })
}
export const revokeExternalGrant = (id: string) => data<{ revoked: boolean }>({ url: `/external-access/grants/${id}`, method: "DELETE" })
export const getExternalOperation = (id: string) => data<ExternalOperation>({ url: `/external-access/operations/${id}` })
export function decideExternalOperation(id: string, digest: string, approve: boolean) {
  return data<ExternalOperation>({ url: `/external-access/operations/${id}/decision`, method: "POST", data: { digest, approve } })
}
export const getExternalPolicy = (id: string) => data<ExternalPolicy>({ url: `/external-access/labs/${id}/policy` })
export function saveExternalPolicy(id: string, payload: ExternalPolicy) {
  return data<ExternalPolicy>({
    url: `/external-access/labs/${id}/policy`,
    method: "PUT",
    data: { enabled: payload.enabled, blocked_fields: payload.blocked_fields, expected_revision: payload.revision },
  })
}
