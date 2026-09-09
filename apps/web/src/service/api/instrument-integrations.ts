import { request } from "../request"

export interface IntegrationBundle {
  package: Record<string, unknown>
  scenarios: unknown[]
}

export interface RehearsalReport {
  passed: boolean
  simulation_only: true
  hardware_authorized: false
  package_digest: string
  uncovered_commands: string[]
  cases: Array<{ name: string, passed: boolean, failure: null | { step: number, reason: string } }>
}

export interface IntegrationDraft {
  id: string
  gateway_id: string
  resource_id: string
  expected_revision: number
  goal: string
  bundle: IntegrationBundle
  reason: string
}

export interface SavedIntegration extends Omit<IntegrationDraft, "expected_revision" | "reason"> {
  revision: number
  content_digest: string
  report: RehearsalReport
  updated_at: string
}

export interface IntegrationPreview {
  preview_digest: string
  content_digest: string
  report: RehearsalReport
  source: { resource_id: string, gateway_id: string, resource_revision_id: string }
}

async function call<T>(path: string, data?: unknown, params?: Record<string, string>) {
  const result = await request<T>({ url: `/instrument-integrations${path}`, method: data ? "POST" : "GET", data, params })
  if (result.error)
    throw result.error
  if (!result.data)
    throw new Error("No integration response")
  return result.data
}

export const fetchIntegrationExample = () => call<IntegrationBundle>("/example")
export const fetchIntegrations = (gatewayId: string) => call<{ items: SavedIntegration[] }>("", undefined, { gateway_id: gatewayId })
export const previewIntegration = (data: IntegrationDraft) => call<IntegrationPreview>("/preview", data)
export const saveIntegration = (data: IntegrationDraft & { preview_digest: string }) => call<SavedIntegration>("", data)
export const draftIntegrationWithAira = (data: IntegrationDraft & { authorized_notes: string, model_processing_consent: boolean }) => call<{ package: Record<string, unknown> }>("/draft-with-aira", data)
export const fetchIntegrationHistory = (id: string) => call<{ items: Array<{ id: string, revision: number, reason: string, created_at: string, snapshot: { bundle: IntegrationBundle } }> }>(`/${id}/history`)
