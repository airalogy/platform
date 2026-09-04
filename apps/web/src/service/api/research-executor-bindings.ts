import { request } from "../request"

export type ExecutorApprovalPolicy = "always_ask" | "allow_read_only" | "deny"

export interface ResearchEligibleExecutor {
  id: string
  username: string
  name: string
}

export interface ResearchExecutorBinding {
  id: string
  revision: number
  source: "lab_policy"
  capability_key: string
  capability_version: string
  executor_type: "human" | "platform_tool"
  executor_ref: { type: string, id: string }
  mode: "protocol_record" | "structured_submission" | "durable_job"
  approval_policy: ExecutorApprovalPolicy
  constraints: Record<string, unknown>
  priority: number
  enabled: boolean
  created_by_user_id: string
  updated_by_user_id: string
  created_at: string
  updated_at: string
}

export interface ExecutorBindingDraft {
  lab_id: string
  capability_key: string
  capability_version: string
  executor_type: ResearchExecutorBinding["executor_type"]
  executor_ref_type: "task_role" | "user" | "skill_pool" | "platform_worker"
  executor_ref_id: string
  mode: ResearchExecutorBinding["mode"]
  approval_policy: ExecutorApprovalPolicy
  constraints: Record<string, unknown>
  priority: number
  enabled: boolean
  reason: string
}

export interface ExecutorBindingUpdateDraft {
  expected_revision: number
  approval_policy: ExecutorApprovalPolicy
  constraints: Record<string, unknown>
  priority: number
  enabled: boolean
  reason: string
}

export interface ExecutorBindingPreview {
  preview_digest: string
  command: Record<string, unknown>
  destination?: { lab_id: string, lab_uid: string, lab_name: string }
  capability?: { kind: string, name: string, risk: string }
  binding?: ResearchExecutorBinding
  effects: string[]
}

async function getData<T>(options: Parameters<typeof request<T>>[0]): Promise<T> {
  const { data, error } = await request<T>(options)
  if (error)
    throw error
  if (!data)
    throw new Error("Research Executor Binding service returned no data")
  return data
}

export function fetchExecutorBindings(labId: string) {
  return getData<{ items: ResearchExecutorBinding[], can_manage: boolean }>({
    url: "/research-executor-bindings",
    params: { lab_id: labId },
    metadata: { showError: false },
  })
}

export function fetchEligibleResearchExecutors(projectId: string) {
  return getData<{ items: ResearchEligibleExecutor[] }>({
    url: "/research-executor-bindings/eligible-users",
    params: { project_id: projectId },
    metadata: { showError: false },
  })
}

export function previewExecutorBinding(payload: ExecutorBindingDraft) {
  return getData<ExecutorBindingPreview>({
    url: "/research-executor-bindings/preview",
    method: "POST",
    data: payload,
  })
}

export function createExecutorBinding(
  payload: ExecutorBindingDraft & { preview_digest: string },
) {
  return getData<ResearchExecutorBinding>({
    url: "/research-executor-bindings",
    method: "POST",
    data: payload,
  })
}

export function previewExecutorBindingUpdate(
  bindingId: string,
  payload: ExecutorBindingUpdateDraft,
) {
  return getData<ExecutorBindingPreview>({
    url: `/research-executor-bindings/${bindingId}/preview`,
    method: "POST",
    data: payload,
  })
}

export function updateExecutorBinding(
  bindingId: string,
  payload: ExecutorBindingUpdateDraft & { preview_digest: string },
) {
  return getData<ResearchExecutorBinding>({
    url: `/research-executor-bindings/${bindingId}`,
    method: "PUT",
    data: payload,
  })
}
