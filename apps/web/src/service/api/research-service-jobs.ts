import type { ResearchServiceJob, ResearchServiceRequirement } from "./research-tasks"
import { request } from "../request"

export interface ServiceActionDraft {
  service_offering_id: string
  request_payload: Record<string, unknown>
  title?: string
  description?: string
  idempotency_key: string
}

export interface ServiceActionPreview {
  preview_digest: string
  command: Record<string, any>
  service: ResearchServiceRequirement
  effects: string[]
}

export interface ServiceQuoteDraft {
  expected_revision: number
  amount: string
  currency: string
  provider_quote_ref?: string
  valid_until?: string | null
  terms?: string
}

export interface ServiceProgressDraft {
  expected_revision: number
  status: "in_fulfillment" | "failed"
  external_order_ref?: string
  provider_status?: string
  expected_completion_at?: string | null
  reason?: string
}

export interface ServiceCustodyDraft {
  expected_revision: number
  kind: "prepared" | "released_to_carrier" | "received_by_provider" | "returned_to_lab" | "disposed_by_provider"
  resource_id: string
  container_id?: string | null
  from_party: string
  to_party: string
  location?: string
  carrier?: string
  tracking_ref?: string
  condition?: Record<string, unknown>
  notes?: string
  occurred_at: string
}

export interface ServiceResultDraft {
  expected_revision: number
  result: Record<string, unknown>
  data_asset_version_ids: string[]
  actual_amount?: string | null
}

export interface ServiceOperationPreview {
  preview_digest: string
  command: Record<string, any>
  effects: string[]
  budget_after_approval?: Record<string, unknown> | null
  resource?: Record<string, unknown>
}

async function getData<T>(options: Parameters<typeof request<T>>[0]): Promise<T> {
  const { data, error } = await request<T>(options)
  if (error)
    throw error
  if (data === null)
    throw new Error("Research service job returned no data")
  return data
}

function previewOperation<T>(jobId: string, operation: string, payload: T) {
  return getData<ServiceOperationPreview>({
    url: `/research-service-jobs/${jobId}/${operation}/preview`,
    method: "POST",
    data: payload,
  })
}

function confirmOperation<T>(jobId: string, operation: string, payload: T & { preview_digest: string }) {
  return getData<ResearchServiceJob>({
    url: `/research-service-jobs/${jobId}/${operation}`,
    method: "POST",
    data: payload,
  })
}

export function previewServiceAction(taskId: string, payload: ServiceActionDraft) {
  return getData<ServiceActionPreview>({
    url: `/research-tasks/${taskId}/service-actions/preview`,
    method: "POST",
    data: payload,
  })
}

export function createServiceAction(taskId: string, payload: ServiceActionDraft & { preview_digest: string }) {
  return getData<Record<string, unknown>>({
    url: `/research-tasks/${taskId}/service-actions`,
    method: "POST",
    data: payload,
  })
}

export const previewServiceQuote = (jobId: string, payload: ServiceQuoteDraft) => previewOperation(jobId, "quotes", payload)
export const recordServiceQuote = (jobId: string, payload: ServiceQuoteDraft & { preview_digest: string }) => confirmOperation(jobId, "quotes", payload)
export const previewServiceProgress = (jobId: string, payload: ServiceProgressDraft) => previewOperation(jobId, "progress", payload)
export const recordServiceProgress = (jobId: string, payload: ServiceProgressDraft & { preview_digest: string }) => confirmOperation(jobId, "progress", payload)
export const previewServiceCustody = (jobId: string, payload: ServiceCustodyDraft) => previewOperation(jobId, "custody", payload)
export const recordServiceCustody = (jobId: string, payload: ServiceCustodyDraft & { preview_digest: string }) => confirmOperation(jobId, "custody", payload)
export const previewServiceResult = (jobId: string, payload: ServiceResultDraft) => previewOperation(jobId, "result", payload)
export const recordServiceResult = (jobId: string, payload: ServiceResultDraft & { preview_digest: string }) => confirmOperation(jobId, "result", payload)
