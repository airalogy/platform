import { request } from "../request"

export interface InstallationDescriptor {
  archive_digest: string
  manifest_digest: string
  sdk_digest: string
  configuration_digest: string
  python_version: string
  platform: string
  architecture: string
  interpreter_digest: string
  entry_point: string
  installation_id: string
  local_preview_digest: string
}
export interface PublicInstallationRequest {
  schema: "airalogy.installation-request.v1"
  id: string
  lab_id: string
  gateway_id: string
  credential_digest: string
  descriptor: InstallationDescriptor
  fingerprint: string
}
export interface InstallationDraft {
  request: PublicInstallationRequest
  resource_id: string
  release_id: string
  reason: string
  fingerprint_confirmed: boolean
}
export interface DeviceBinding {
  id: string
  gateway_id: string
  resource_id: string
  release_id: string
  resource_revision: number
  release_revision: number
  state: "authorized" | "installing" | "installed" | "expired" | "revoked"
  revision: number
  descriptor: InstallationDescriptor
  installer_fingerprint: string
  reason: string
  expires_at: string
  installed_at: string | null
}
export interface InstallationPreview {
  preview_digest: string
  resource_revision: number
  release_revision: number
}
async function call<T>(path: string, data?: unknown, params?: Record<string, string | number>) {
  const result = await request<T>({ url: `/instrument-installations${path}`, method: data === undefined ? "GET" : "POST", data, params })
  if (result.error)
    throw result.error
  if (!result.data)
    throw new Error("No installation response")
  return result.data
}
export const fetchInstallations = (gatewayId: string, offset = 0) => call<{ items: DeviceBinding[], has_more: boolean, next_offset: number }>("", undefined, { gateway_id: gatewayId, offset })
export const previewInstallation = (draft: InstallationDraft) => call<InstallationPreview>("/preview", draft)
export const confirmInstallation = (draft: InstallationDraft & { preview_digest: string }) => call<DeviceBinding>("", draft)
export const fetchInstallationHistory = (id: string) => call<{ items: { revision: number, action: "authorized" | "claimed" | "package_downloaded" | "installed" | "expired" | "revoked", reason: string, created_at: string }[] }>(`/${id}/history`)
export const previewInstallationRevocation = (id: string, expected_revision: number, reason: string) => call<{ preview_digest: string }>(`/${id}/revoke/preview`, { expected_revision, reason })
export const confirmInstallationRevocation = (id: string, expected_revision: number, reason: string, preview_digest: string) => call<DeviceBinding>(`/${id}/revoke`, { expected_revision, reason, preview_digest })
