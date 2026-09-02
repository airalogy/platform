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
  return getData<{ entry: ResearchBudgetEntry, budget: ResearchBudgetSnapshot }>({
    url: `/research-tasks/${taskId}/budget/entries`,
    method: "POST",
    data: payload,
  })
}
