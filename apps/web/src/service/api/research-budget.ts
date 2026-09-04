import type { ResearchScope } from "./research-tasks"
import { request } from "../request"

export type ResearchBudgetEntryKind = "reserve" | "release" | "expense" | "credit"

export interface ResearchBudgetEntry {
  id: string
  task_id: string
  run_id?: string | null
  action_id?: string | null
  kind: ResearchBudgetEntryKind
  amount: string
  currency: string
  source_type: string
  source_ref?: string | null
  description: string
  created_by_user_id?: string | null
  idempotency_key: string
  command_digest: string
  created_at: string
}

export interface ResearchBudgetSnapshot {
  enabled: boolean
  currency?: string | null
  limit?: string | null
  reserved: string
  actual: string
  committed: string
  remaining?: string | null
  entries: ResearchBudgetEntry[]
}

export interface ResearchBudgetEntryDraft {
  expected_task_revision: number
  kind: ResearchBudgetEntryKind
  amount: string
  currency: string
  description: string
  idempotency_key: string
}

export interface ResearchBudgetPreview {
  preview_digest: string
  destination: {
    lab: ResearchScope
    project: ResearchScope
    task: { id: string, title: string }
  }
  current: ResearchBudgetSnapshot
  projected: Omit<ResearchBudgetSnapshot, "entries">
  effect: string
}

export interface ResearchOperationalLimitAmendment {
  id: string
  task_id: string
  kind: "task.operational_limits_amended"
  actor_user_id?: string | null
  payload: {
    preview_digest: string
    reason: string
    previous_revision: number
    task_revision: number
    current: ResearchOperationalLimitValues
    projected: ResearchOperationalLimitProjection
    resume_required: boolean
  }
  created_at: string
}

export interface ResearchOperationalLimitValues {
  deadline_at?: string | null
  budget_limit?: string | null
  budget_currency?: string | null
  budget_committed?: string | null
  budget_remaining?: string | null
}

export interface ResearchOperationalLimitProjection extends ResearchOperationalLimitValues {
  resume_eligible: boolean
  checked_at: string
}

export interface ResearchOperationalLimitsSnapshot {
  task_revision: number
  deadline_at?: string | null
  budget: ResearchBudgetSnapshot
  amendments: ResearchOperationalLimitAmendment[]
}

export interface ResearchOperationalLimitsDraft {
  expected_task_revision: number
  deadline_at: string | null
  budget_limit: string | null
  budget_currency: string | null
  reason: string
  idempotency_key: string
}

export interface ResearchOperationalLimitsPreview {
  preview_digest: string
  destination: {
    lab: ResearchScope
    project: ResearchScope
    task: { id: string, title: string }
  }
  current: ResearchOperationalLimitValues
  projected: ResearchOperationalLimitProjection
  resume_required: boolean
  effect: string
}

async function getData<T>(options: Parameters<typeof request<T>>[0]): Promise<T> {
  const { data, error } = await request<T>(options)
  if (error)
    throw error
  if (data === null)
    throw new Error("Research Budget service returned no data")
  return data
}

export function fetchResearchBudget(taskId: string) {
  return getData<ResearchBudgetSnapshot>({
    url: `/research-tasks/${taskId}/budget`,
  })
}

export function fetchResearchOperationalLimits(taskId: string) {
  return getData<ResearchOperationalLimitsSnapshot>({
    url: `/research-tasks/${taskId}/operational-limits`,
  })
}

export function previewResearchOperationalLimits(
  taskId: string,
  payload: ResearchOperationalLimitsDraft,
) {
  return getData<ResearchOperationalLimitsPreview>({
    url: `/research-tasks/${taskId}/operational-limits/preview`,
    method: "POST",
    data: payload,
  })
}

export function amendResearchOperationalLimits(
  taskId: string,
  payload: ResearchOperationalLimitsDraft & { preview_digest: string },
) {
  return getData<{
    amendment: ResearchOperationalLimitAmendment
    operational_limits: ResearchOperationalLimitsSnapshot
  }>({
    url: `/research-tasks/${taskId}/operational-limits`,
    method: "POST",
    data: payload,
  })
}

export function previewResearchBudgetEntry(
  taskId: string,
  payload: ResearchBudgetEntryDraft,
) {
  return getData<ResearchBudgetPreview>({
    url: `/research-tasks/${taskId}/budget/entries/preview`,
    method: "POST",
    data: payload,
  })
}

export function createResearchBudgetEntry(
  taskId: string,
  payload: ResearchBudgetEntryDraft & { preview_digest: string },
) {
  return getData<{
    entry: ResearchBudgetEntry
    budget: ResearchBudgetSnapshot
    task_revision: number
  }>({
    url: `/research-tasks/${taskId}/budget/entries`,
    method: "POST",
    data: payload,
  })
}
