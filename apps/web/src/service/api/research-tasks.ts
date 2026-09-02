import { request } from "../request"

export type ResearchTaskStatus =
  | "draft"
  | "active"
  | "paused"
  | "review_required"
  | "completed"
  | "failed"
  | "cancelled"
  | "archived"

export type ResearchRunStatus =
  | "draft"
  | "planning"
  | "running"
  | "waiting_for_human"
  | "waiting_for_approval"
  | "validating"
  | "paused"
  | "completed"
  | "failed"
  | "cancelled"

export type ResearchActionStatus =
  | "proposed"
  | "approved"
  | "queued"
  | "running"
  | "waiting"
  | "submitted"
  | "validating"
  | "completed"
  | "failed"
  | "skipped"
  | "cancelled"

export type HumanWorkItemStatus =
  | "open"
  | "in_progress"
  | "submitted"
  | "accepted"
  | "changes_requested"
  | "cancelled"

export type ResearchApprovalStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "expired"
  | "revoked"

export interface ResearchUser {
  id: string
  username: string
  name: string
}

export interface ResearchScope {
  id: string
  uid: string
  name: string
}

export interface ResearchProtocolRef extends ResearchScope {
  version: string
  position?: number
  lab_uid?: string
  project_uid?: string
}

export interface ResearchRun {
  id: string
  task_id: string
  run_number: number
  status: ResearchRunStatus
  plan_version: number
  advance_generation: number
  environment_snapshot: Record<string, unknown>
  aira_state: Record<string, any>
  result_package: ResearchResultPackage | Record<string, never>
  last_error?: string | null
  started_at?: string | null
  completed_at?: string | null
  created_at: string
  updated_at: string
}

export interface ResearchResultPackage {
  schema?: string
  goal?: string
  goal_assessment?: string
  scientific_outcome?: string
  narrative_conclusion?: string
  reviewed_conclusion?: string
  claims?: Array<Record<string, unknown>>
  evidence?: Array<Record<string, unknown>>
  actions?: Array<Record<string, unknown>>
  failed_attempts?: string[]
  unresolved_questions?: string[]
  reproducibility?: Record<string, unknown>
}

export interface ResearchProtocolRun {
  id: string
  action_id: string
  protocol_id: string
  protocol_version: string
  initial_values: Record<string, unknown>
  record_id?: string | null
  record_version?: number | null
  validation_status: string
  validation_report: Record<string, unknown>
}

export interface ResearchHumanWorkItem {
  id: string
  action_id: string
  assignee_user_id: string
  status: HumanWorkItemStatus
  instructions: string
  submission_contract: Record<string, unknown>
  submission: Record<string, unknown>
  record_id?: string | null
  record_version?: number | null
  validation_issues: Array<Record<string, unknown>>
  revision: number
  due_at?: string | null
  created_at: string
  updated_at: string
  started_at?: string | null
  submitted_at?: string | null
  accepted_at?: string | null
}

export interface ResearchAction {
  id: string
  run_id: string
  sequence: number
  plan_version: number
  kind: string
  status: ResearchActionStatus
  title: string
  description: string
  executor_type: string
  assignee_user_id?: string | null
  assignee?: ResearchUser | null
  input_data: Record<string, any>
  output_data: Record<string, any>
  requirements: Record<string, unknown>
  policy_decision: string
  preview_digest: string
  revision: number
  due_at?: string | null
  created_at: string
  updated_at: string
  started_at?: string | null
  completed_at?: string | null
  error?: string | null
  protocol_run?: ResearchProtocolRun | null
  protocol?: ResearchProtocolRef | null
  work_item?: ResearchHumanWorkItem | null
  approval?: ResearchApproval | null
}

export interface ResearchApproval {
  id: string
  action_id: string
  approver_user_id: string
  requested_by_user_id: string
  decided_by_user_id?: string | null
  status: ResearchApprovalStatus
  preview_digest: string
  reason: string
  decision_reason: string
  revision: number
  requested_at: string
  decided_at?: string | null
  approver: ResearchUser
  requested_by: ResearchUser
  decided_by?: ResearchUser | null
}

export interface ResearchTaskSummary {
  id: string
  lab_id: string
  project_id: string
  title: string
  goal: string
  success_criteria: string[]
  stop_conditions: string[]
  autonomy_level: "assisted" | "bounded_autopilot" | "autonomous_within_policy"
  status: ResearchTaskStatus
  outcome?: string | null
  scientific_outcome?: string | null
  conclusion: string
  result_package: ResearchResultPackage | Record<string, never>
  owner_user_id: string
  owner: ResearchUser
  created_by_user_id: string
  revision: number
  project: ResearchScope
  lab: ResearchScope
  latest_run?: ResearchRun | null
  open_work_items: number
  pending_approvals: number
  ai_available: boolean
  created_at: string
  updated_at: string
  completed_at?: string | null
}

export interface ResearchEvent {
  id: string
  task_id: string
  run_id?: string | null
  action_id?: string | null
  work_item_id?: string | null
  kind: string
  actor_user_id?: string | null
  payload: Record<string, unknown>
  created_at: string
}

export interface ResearchPlanVersion {
  id: string
  run_id: string
  version: number
  kind: string
  plan: Record<string, unknown>
  digest: string
  summary: string
  created_at: string
}

export interface ResearchTaskDetail extends ResearchTaskSummary {
  runs: ResearchRun[]
  actions: ResearchAction[]
  events: ResearchEvent[]
  plan_versions: ResearchPlanVersion[]
  protocols: ResearchProtocolRef[]
}

export interface ResearchWorkItemDetail extends ResearchHumanWorkItem {
  assignee: ResearchUser
  action: ResearchAction
  run: ResearchRun
  task: Pick<ResearchTaskSummary, "id" | "title" | "goal" | "status" | "revision">
  project: ResearchScope
  lab: ResearchScope
}

export interface ResearchApprovalDetail extends ResearchApproval {
  action: ResearchAction
  run: ResearchRun
  task: Pick<ResearchTaskSummary, "id" | "title" | "goal" | "status" | "revision">
  project: ResearchScope
  lab: ResearchScope
}

export interface ResearchTaskDraft {
  project_id: string
  title: string
  goal: string
  success_criteria: string[]
  stop_conditions: string[]
  autonomy_level: ResearchTaskSummary["autonomy_level"]
  protocol_ids: string[]
  owner_user_id?: string
  ai_model?: string
}

export interface ResearchTaskPreview {
  preview_digest: string
  command: Record<string, unknown>
  destination: { lab: ResearchScope, project: ResearchScope }
  owner: ResearchUser
  protocols: ResearchProtocolRef[]
  effects: string[]
  warnings: string[]
  ai_path_available: boolean
}

export interface ManualProtocolActionDraft {
  protocol_id: string
  assignee_user_id?: string
  title?: string
  instructions: string
  initial_values: Record<string, unknown>
  due_at?: string
  idempotency_key: string
}

export interface ManualProtocolActionPreview {
  preview_digest: string
  command: Record<string, unknown>
  destination: {
    lab: ResearchScope
    project: ResearchScope
    task: Pick<ResearchTaskSummary, "id" | "title">
    run: { id: string, number: number }
  }
  protocol: ResearchProtocolRef
  assignee: ResearchUser
  effects: string[]
}

async function getData<T>(options: Parameters<typeof request<T>>[0]): Promise<T> {
  const { data, error } = await request<T>(options)
  if (error)
    throw error
  if (data === null)
    throw new Error("Research Task service returned no data")
  return data
}

export function previewResearchTask(payload: ResearchTaskDraft) {
  return getData<ResearchTaskPreview>({
    url: "/research-tasks/preview",
    method: "POST",
    data: payload,
  })
}

export function createResearchTask(payload: ResearchTaskDraft & { preview_digest: string }) {
  return getData<ResearchTaskDetail>({ url: "/research-tasks", method: "POST", data: payload })
}

export function fetchResearchTasks(params: {
  projectId?: string
  status?: ResearchTaskStatus[]
  page?: number
  pageSize?: number
} = {}) {
  return getData<{ tasks: ResearchTaskSummary[], total_count: number }>({
    url: "/research-tasks",
    params: {
      project_id: params.projectId,
      status: params.status,
      page: params.page || 1,
      page_size: params.pageSize || 20,
    },
    metadata: { showError: false },
  })
}

export function fetchResearchTask(taskId: string) {
  return getData<ResearchTaskDetail>({
    url: `/research-tasks/${taskId}`,
    metadata: { showError: false },
  })
}

function transition(taskId: string, action: string, revision: number, reason = "") {
  return getData<ResearchTaskDetail>({
    url: `/research-tasks/${taskId}/${action}`,
    method: "POST",
    data: { expected_revision: revision, reason },
  })
}

export const startResearchTask = (taskId: string, revision: number) => transition(taskId, "start", revision)
export const pauseResearchTask = (taskId: string, revision: number, reason = "") => transition(taskId, "pause", revision, reason)
export const resumeResearchTask = (taskId: string, revision: number, reason = "") => transition(taskId, "resume", revision, reason)
export const cancelResearchTask = (taskId: string, revision: number, reason = "") => transition(taskId, "cancel", revision, reason)

export function completeResearchTask(taskId: string, payload: {
  expected_revision: number
  outcome: string
  scientific_outcome: string
  conclusion: string
  reason?: string
}) {
  return getData<ResearchTaskDetail>({
    url: `/research-tasks/${taskId}/complete`,
    method: "POST",
    data: payload,
  })
}

export function previewManualProtocolAction(taskId: string, payload: ManualProtocolActionDraft) {
  return getData<ManualProtocolActionPreview>({
    url: `/research-tasks/${taskId}/actions/preview`,
    method: "POST",
    data: payload,
  })
}

export function createManualProtocolAction(
  taskId: string,
  payload: ManualProtocolActionDraft & { preview_digest: string },
) {
  return getData<ResearchAction>({
    url: `/research-tasks/${taskId}/actions`,
    method: "POST",
    data: payload,
  })
}

export function fetchResearchWorkItems(params: {
  status?: HumanWorkItemStatus[]
  page?: number
  pageSize?: number
} = {}) {
  return getData<{ work_items: ResearchWorkItemDetail[], total_count: number }>({
    url: "/research-work-items",
    params: {
      status: params.status,
      page: params.page || 1,
      page_size: params.pageSize || 20,
    },
    metadata: { showError: false },
  })
}

export function fetchResearchWorkItem(workItemId: string) {
  return getData<ResearchWorkItemDetail>({
    url: `/research-work-items/${workItemId}`,
    metadata: { showError: false },
  })
}

export function startResearchWorkItem(workItemId: string, revision: number) {
  return getData<ResearchWorkItemDetail>({
    url: `/research-work-items/${workItemId}/start`,
    method: "POST",
    data: { expected_revision: revision },
  })
}

export function assignResearchWorkItem(
  workItemId: string,
  payload: { expected_revision: number, assignee_user_id: string, reason: string },
) {
  return getData<ResearchWorkItemDetail>({
    url: `/research-work-items/${workItemId}/assign`,
    method: "POST",
    data: payload,
  })
}

export function submitResearchWorkItem(
  workItemId: string,
  payload: { expected_revision: number, record_id: string, record_version?: number, note?: string },
) {
  return getData<ResearchWorkItemDetail>({
    url: `/research-work-items/${workItemId}/submit`,
    method: "POST",
    data: payload,
  })
}

export function fetchResearchApprovals(params: {
  status?: ResearchApprovalStatus[]
  page?: number
  pageSize?: number
} = {}) {
  return getData<{ approvals: ResearchApprovalDetail[], total_count: number }>({
    url: "/research-approvals",
    params: {
      status: params.status,
      page: params.page || 1,
      page_size: params.pageSize || 20,
    },
    metadata: { showError: false },
  })
}

export function approveResearchAction(
  approvalId: string,
  payload: {
    expected_revision: number
    expected_action_revision: number
    preview_digest: string
    reason?: string
  },
) {
  return getData<ResearchApprovalDetail>({
    url: `/research-approvals/${approvalId}/approve`,
    method: "POST",
    data: payload,
  })
}

export function rejectResearchAction(
  approvalId: string,
  payload: {
    expected_revision: number
    expected_action_revision: number
    preview_digest: string
    reason: string
  },
) {
  return getData<ResearchApprovalDetail>({
    url: `/research-approvals/${approvalId}/reject`,
    method: "POST",
    data: payload,
  })
}
