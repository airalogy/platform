import type {
  ResearchAction,
  ResearchResourceReservation,
  ResearchScope,
} from "./research-tasks"
import { request } from "../request"

export interface ResearchResourceActionDraft {
  kind: "inventory" | "equipment"
  resource_id: string
  container_id?: string
  quantity?: string
  unit?: string
  expires_at?: string
  starts_at?: string
  ends_at?: string
  purpose: string
  idempotency_key: string
}

export interface ResearchResourceActionPreview {
  preview_digest: string
  command: Record<string, unknown>
  destination: {
    lab: ResearchScope
    project: ResearchScope
    task: { id: string, title: string }
    run: { id: string, number: number }
  }
  resource: { id: string, name: string, code: string, revision: number }
  effects: string[]
}

export interface ResearchResourceAction extends ResearchAction {
  resource_reservation: ResearchResourceReservation
  resource?: {
    id: string
    name: string
    code: string
    resource_type_id: string
  } | null
}

export interface ResearchResourceReleaseDraft {
  expected_revision: number
  reason: string
}

export interface ResearchResourceReleasePreview {
  preview_digest: string
  effect: string
  resource: { id: string, name: string }
}

async function getData<T>(options: Parameters<typeof request<T>>[0]): Promise<T> {
  const { data, error } = await request<T>(options)
  if (error)
    throw error
  if (data === null)
    throw new Error("Research Resource service returned no data")
  return data
}

export function previewResearchResourceAction(
  taskId: string,
  payload: ResearchResourceActionDraft,
) {
  return getData<ResearchResourceActionPreview>({
    url: `/research-tasks/${taskId}/resource-actions/preview`,
    method: "POST",
    data: payload,
  })
}

export function createResearchResourceAction(
  taskId: string,
  payload: ResearchResourceActionDraft & { preview_digest: string },
) {
  return getData<ResearchResourceAction>({
    url: `/research-tasks/${taskId}/resource-actions`,
    method: "POST",
    data: payload,
  })
}

export function syncResearchResourceReservation(reservationId: string) {
  return getData<ResearchResourceAction>({
    url: `/research-resource-reservations/${reservationId}/sync`,
    method: "POST",
  })
}

export function previewResearchResourceRelease(
  reservationId: string,
  payload: ResearchResourceReleaseDraft,
) {
  return getData<ResearchResourceReleasePreview>({
    url: `/research-resource-reservations/${reservationId}/release/preview`,
    method: "POST",
    data: payload,
  })
}

export function releaseResearchResourceReservation(
  reservationId: string,
  payload: ResearchResourceReleaseDraft & { preview_digest: string },
) {
  return getData<ResearchResourceAction>({
    url: `/research-resource-reservations/${reservationId}/release`,
    method: "POST",
    data: payload,
  })
}
