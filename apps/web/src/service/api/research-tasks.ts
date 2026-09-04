import type { ResearchAutonomyPolicySnapshot } from "./research-autonomy-policies"
import type { ResearchComputeJob } from "./research-compute-jobs"
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
  | "waiting_for_tool"
  | "waiting_for_instrument"
  | "waiting_for_compute"
  | "waiting_for_event"
  | "waiting_for_approval"
  | "validating"
  | "paused"
  | "completed"
  | "failed"
  | "cancelled"

export type ResearchActionStatus =
  | "blocked"
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

export type ResearchActionKind =
  | "protocol_run"
  | "tool_job"
  | "human_work_item"
  | "instrument_job"
  | "compute_job"
  | "external_service_job"
  | "approval_request"
  | "resource_reservation"
  | "wait_event"

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

export type HumanWorkValueType
  = "text" | "long_text" | "number" | "boolean" | "date" | "choice"

export interface HumanWorkField {
  key: string
  label: string
  description: string
  value_type: HumanWorkValueType
  required: boolean
  options: string[]
  unit: string
}

export interface HumanWorkRequest {
  title: string
  instructions: string
  completion_criteria: string
  evidence_kind: "observation" | "measurement" | "analysis" | "citation" | "validation"
  fields: HumanWorkField[]
  data_asset_min_count: number
  data_asset_max_count: number
}

export interface HumanWorkSubmissionContract {
  schema: "airalogy.human-work-submission.v1"
  type: "structured_values"
  fields: HumanWorkField[]
  data_asset_min_count: number
  data_asset_max_count: number
  evidence_kind: HumanWorkRequest["evidence_kind"]
  completion_criteria: string
}

export interface HumanWorkSubmission {
  work_item_id?: string
  preview_digest?: string
  values?: Record<string, unknown>
  data_assets?: Array<{
    data_asset_id: string
    data_asset_version_id: string
    version: number
    name: string
    kind: string
    status: string
  }>
  note?: string
  review?: {
    decision: "accept" | "changes_requested"
    reason: string
    preview_digest: string
    reviewed_by_user_id: string
    reviewed_at: string
  }
}

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

export interface ResearchKnowledgeRef {
  id: string
  title: string
  kind: ResearchActionKind
  state?: string
  scope_type: "lab" | "project"
  revision: number
  position?: number
  body?: string
  tags?: string[]
}

export interface ResearchEnvironmentExecutorBinding {
  id?: string | null
  revision: number
  source: "platform_default" | "lab_policy"
  capability_key: string
  capability_version: string
  executor_type: "human" | "platform_tool"
  executor_ref: { type: string, id: string }
  resolved_executor_ref?: { type: string, id: string }
  mode: string
  approval_policy: "always_ask" | "allow_read_only" | "deny"
  constraints: Record<string, unknown>
  priority: number
}

export interface ResearchResourceRequirement {
  key: string
  version: string
  kind: "resource"
  name: string
  description: string
  source_id: string
  source_revision_id: string
  available: boolean
  metadata: {
    code?: string
    capabilities?: Record<string, boolean>
    booking_policy?: string
  }
  position?: number
}

export interface ResearchServiceRequirement {
  key: string
  version: string
  kind: "service"
  name: string
  description: string
  source_id: string
  source_revision_id: string
  risk: "low" | "medium" | "high"
  input_schema: Record<string, unknown>
  output_schema: Record<string, unknown>
  available: boolean
  metadata: {
    offering_key: string
    offering_revision: number
    quote_required: boolean
    base_price?: string | null
    currency?: string | null
    sla_hours?: number | null
    provider: {
      id: string
      name: string
      revision: number
    }
  }
  position?: number
}

export interface ResearchComputeRequirement {
  key: string
  version: string
  kind: "compute"
  name: string
  description: string
  source_id: string
  source_revision_id: string
  risk: "low" | "medium" | "high"
  input_schema: Record<string, unknown>
  output_schema: Record<string, unknown>
  available: boolean
  metadata: {
    environment_key: string
    environment_revision: number
    image_ref: string
    runtime_version: string
    allowed_languages: Array<"python" | "r">
    resource_limits: {
      cpu_millis: number
      memory_mb: number
      gpu_count: number
      timeout_seconds: number
      max_output_bytes: number
    }
    network_policy: "none" | "egress_allowlist"
    allowed_egress_hosts: string[]
    estimated_cost_per_hour?: string | null
    currency?: string | null
  }
  position?: number
}

export interface ResearchResourceReservation {
  id: string
  action_id: string
  kind: "inventory" | "equipment"
  resource_id: string
  resource_revision_id: string
  resource_revision: number
  container_id?: string | null
  inventory_reservation_id?: string | null
  equipment_booking_id?: string | null
  quantity?: string | null
  unit?: string | null
  starts_at?: string | null
  ends_at?: string | null
  status: string
  purpose: string
  revision: number
  created_at: string
  updated_at: string
  consumptions?: ResearchResourceConsumption[]
}

export interface ResearchResourceConsumption {
  id: string
  research_resource_reservation_id: string
  inventory_event_id: string
  record_id: string
  record_version: number
  record_number: number
  protocol_id: string
  protocol_uid: string
  protocol_version: string
  field_path: string
  quantity: string
  unit: string
  remaining_quantity: string
  remaining_unit: string
  actor_user_id: string
  created_at: string
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

export interface ResearchRunOrigin {
  kind: "retry" | "replication" | "continuation"
  purpose: string
  source_run_id: string
  source_run_number: number
  source_environment_digest: string
  source_result_digest: string
  created_at: string
}

export type ReproductionCriterionStatus
  = "reproduced" | "not_reproduced" | "inconclusive"

export type ReproductionOutcome
  = "reproduced" | "partially_reproduced" | "not_reproduced" | "inconclusive"

export interface ReproductionCriterionResult {
  criterion: string
  status: ReproductionCriterionStatus
  rationale: string
}

export interface ResearchReproductionAssessment {
  outcome: ReproductionOutcome
  summary: string
  criteria_results: ReproductionCriterionResult[]
  source_evidence_ids: string[]
  replication_evidence_ids: string[]
  deviations: string[]
  limitations: string[]
}

export interface ResearchReproductionEvidence {
  id: string
  run_id: string
  kind: string
  summary: string
  artifact_type: string
  artifact_id: string
  artifact_version: string
  quality_state: "validated"
}

export interface ResearchReproductionContext {
  schema: "airalogy.reproduction-context.v1"
  task_id: string
  kind: "replication"
  success_criteria: string[]
  source_run: {
    id: string
    run_number: number
    environment_digest: string
    effective_environment_digest: string
    result_digest: string
    snapshot_sealed: boolean
  }
  replication_run: {
    id: string
    run_number: number
    environment_digest: string
    effective_environment_digest: string
  }
  lineage_intact: boolean
  environment_equivalent: boolean
  source_evidence: ResearchReproductionEvidence[]
  replication_evidence: ResearchReproductionEvidence[]
}

export interface ResearchReplicationEvaluation {
  schema: "airalogy.replication-evaluation.v1"
  context_digest: string
  source_run: ResearchReproductionContext["source_run"]
  replication_run: ResearchReproductionContext["replication_run"]
  lineage_intact: boolean
  environment_equivalent: boolean
  assessment: ResearchReproductionAssessment
  reviewed_by_user_id: string
  reviewed_at: string
  review_recommendation_id?: string | null
}

export interface ResearchResultPackage {
  schema?: string
  goal?: string
  success_criteria?: string[]
  goal_assessment?: string
  scientific_outcome?: string
  narrative_conclusion?: string
  reviewed_conclusion?: string
  claims?: Array<Record<string, unknown>>
  evidence?: Array<Record<string, unknown>>
  data_assets?: Array<Record<string, unknown>>
  knowledge_items?: Array<Record<string, unknown>>
  protocol_improvements?: Array<Record<string, unknown>>
  actions?: Array<Record<string, unknown>>
  failed_attempts?: string[]
  unresolved_questions?: string[]
  reproducibility?: Record<string, unknown> & {
    replication_evaluation?: ResearchReplicationEvaluation
  }
  budget?: Record<string, unknown>
  reviewed_by_user_id?: string
  reviewed_at?: string
  generated_at?: string
}

export interface ResearchResultPackageEnvelope {
  snapshot: {
    id?: string | null
    sealed: boolean
    task_id: string
    run_id: string
    run_number: number
    task_revision?: number | null
    schema_version: string
    digest: string
    finalized_by_user_id?: string | null
    finalized_at?: string | null
  }
  package: ResearchResultPackage
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
  submission_contract: Record<string, unknown> | HumanWorkSubmissionContract
  submission: Record<string, unknown> | HumanWorkSubmission
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

export interface ResearchToolJob {
  id: string
  action_id: string
  tool_key: string
  tool_version: string
  arguments: Record<string, unknown>
  output: Record<string, any>
  status: "queued" | "running" | "completed" | "failed" | "cancelled"
  timeout_seconds: number
  error?: string | null
  created_at: string
  started_at?: string | null
  completed_at?: string | null
}

export interface ResearchWaitEvent {
  id: string
  action_id: string
  event_key: string
  expected_event_type: string
  payload_schema: Record<string, any>
  received_payload: Record<string, any>
  status: "waiting" | "received" | "expired" | "cancelled"
  revision: number
  due_at?: string | null
  created_at: string
  received_at?: string | null
  received_by_user_id?: string | null
}

export interface ResearchInstrumentJob {
  id: string
  action_id: string
  gateway_id: string
  command_id: string
  resource_id: string
  resource_revision_id: string
  resource_revision: number
  equipment_booking_id: string
  control_session_id?: string | null
  control_step_key?: string | null
  control_execution_index?: number | null
  command_key: string
  command_version: string
  command_revision: number
  arguments: Record<string, unknown>
  input_schema: Record<string, unknown>
  output_schema: Record<string, unknown>
  risk: "read_only" | "low" | "medium" | "high"
  device_confirmation_required: boolean
  safety_contract: {
    required_interlocks: string[]
    operator_presence_required: boolean
    emergency_stop_required: boolean
  }
  safety_attestation: Record<string, unknown>
  timeout_seconds: number
  status:
    | "queued"
    | "leased"
    | "running"
    | "stop_requested"
    | "completed"
    | "failed"
    | "cancelled"
    | "stopped"
  attempt_count: number
  device_confirmation: Record<string, unknown>
  result: Record<string, unknown>
  error?: string | null
  stop_reason?: string | null
  revision: number
  created_at: string
  leased_at?: string | null
  started_at?: string | null
  heartbeat_at?: string | null
  stop_requested_at?: string | null
  completed_at?: string | null
}

export type ResearchInstrumentControlStatus
  = "queued"
  | "running"
  | "paused_for_review"
  | "stop_requested"
  | "completed"
  | "failed"
  | "cancelled"
  | "stopped"

export interface ResearchInstrumentControlSession {
  id: string
  run_id: string
  gateway_id: string
  resource_id: string
  equipment_booking_id: string
  mode: "bounded_sequence" | "feedback_loop"
  status: ResearchInstrumentControlStatus
  title: string
  description: string
  program: Record<string, any>
  program_digest: string
  creation_digest: string
  idempotency_key: string
  entry_step_key: string
  current_step_key?: string | null
  pending_step_key?: string | null
  issued_steps: number
  executed_steps: number
  max_steps: number
  max_duration_seconds: number
  pause_reason: string
  error?: string | null
  stop_reason?: string | null
  revision: number
  created_at: string
  updated_at: string
  started_at?: string | null
  completed_at?: string | null
  jobs?: ResearchInstrumentJob[]
}

export type ResearchServiceJobStatus
  = "blocked"
  | "awaiting_quote"
  | "awaiting_approval"
  | "ordered"
  | "in_fulfillment"
  | "completed"
  | "failed"
  | "cancelled"

export interface ResearchServiceQuote {
  id: string
  service_job_id: string
  revision: number
  amount: string
  currency: string
  provider_quote_ref: string
  valid_until?: string | null
  terms: string
  source: "catalog" | "provider"
  quote_digest: string
  created_at: string
}

export interface ResearchServiceCustodyEvent {
  id: string
  service_job_id: string
  sequence: number
  kind: "prepared" | "released_to_carrier" | "received_by_provider" | "returned_to_lab" | "disposed_by_provider"
  resource_id: string
  container_id?: string | null
  from_party: string
  to_party: string
  location: string
  carrier: string
  tracking_ref: string
  condition: Record<string, unknown>
  notes: string
  occurred_at: string
  event_digest: string
  created_at: string
}

export interface ResearchServiceResultAsset {
  data_asset_version_id: string
  data_asset_id: string
  name: string
  kind: string
  status: string
  version: number
}

export interface ResearchServiceJob {
  id: string
  action_id: string
  provider_id: string
  service_offering_id: string
  service_offering_revision_id: string
  service_offering_revision: number
  service_version: string
  provider_snapshot: { id?: string, name?: string, revision?: number }
  offering_snapshot: ResearchServiceRequirement & Record<string, any>
  request_payload: Record<string, unknown>
  input_schema: Record<string, unknown>
  result_schema: Record<string, unknown>
  risk: "low" | "medium" | "high"
  quote_required: boolean
  status: ResearchServiceJobStatus
  current_quote_revision?: number | null
  external_order_ref: string
  provider_status: string
  expected_completion_at?: string | null
  result: Record<string, unknown>
  actual_amount?: string | null
  error?: string | null
  revision: number
  quote_requested_at?: string | null
  approved_at?: string | null
  ordered_at?: string | null
  started_at?: string | null
  completed_at?: string | null
  created_at: string
  updated_at: string
  quote?: ResearchServiceQuote | null
  custody_events: ResearchServiceCustodyEvent[]
  result_assets: ResearchServiceResultAsset[]
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
  policy_reason: string
  preview_digest: string
  revision: number
  due_at?: string | null
  created_at: string
  updated_at: string
  started_at?: string | null
  completed_at?: string | null
  error?: string | null
  dependencies: Array<{
    action_id: string
    condition: Record<string, unknown>
  }>
  dependent_action_ids: string[]
  protocol_run?: ResearchProtocolRun | null
  protocol?: ResearchProtocolRef | null
  work_item?: ResearchHumanWorkItem | null
  tool_job?: ResearchToolJob | null
  instrument_job?: ResearchInstrumentJob | null
  instrument_control?: ResearchInstrumentControlSession | null
  compute_job?: ResearchComputeJob | null
  service_job?: ResearchServiceJob | null
  wait_event?: ResearchWaitEvent | null
  resource_reservation?: ResearchResourceReservation | null
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
  deadline_at?: string | null
  budget_limit?: string | null
  budget_currency?: string | null
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

export interface ResearchReviewRecommendation {
  id: string
  task_id: string
  run_id?: string | null
  task_revision: number
  context_digest: string
  model_name: string
  recommendation: "accept" | "revise" | "collect_more_evidence"
  recommended_task_outcome: string
  recommended_scientific_outcome: string
  summary: string
  supporting_evidence_ids: string[]
  contradicting_evidence_ids: string[]
  uncertainties: string[]
  missing_checks: string[]
  risk_flags: string[]
  reproduction_assessment?: ResearchReproductionAssessment | null
  requested_by_user_id: string
  created_at: string
}

export interface ResearchTaskDetail extends ResearchTaskSummary {
  runs: ResearchRun[]
  actions: ResearchAction[]
  events: ResearchEvent[]
  plan_versions: ResearchPlanVersion[]
  protocols: ResearchProtocolRef[]
  knowledge: ResearchKnowledgeRef[]
  resources: ResearchResourceRequirement[]
  services: ResearchServiceRequirement[]
  compute: ResearchComputeRequirement[]
  review_recommendations: ResearchReviewRecommendation[]
  reproduction_context?: ResearchReproductionContext | null
  permissions: {
    can_run: boolean
    can_approve: boolean
    can_use_services: boolean
    can_manage_services: boolean
    can_use_compute: boolean
    can_manage_compute: boolean
  }
}

export interface ResearchWorkItemDetail extends ResearchHumanWorkItem {
  assignee: ResearchUser
  action: ResearchAction
  run: ResearchRun
  task: Pick<ResearchTaskSummary, "id" | "title" | "goal" | "status" | "revision" | "owner_user_id">
  project: ResearchScope
  lab: ResearchScope
  permissions: {
    can_assign: boolean
    can_start: boolean
    can_submit: boolean
    can_review: boolean
  }
}

export interface ResearchApprovalDetail extends ResearchApproval {
  action: ResearchAction
  run: ResearchRun
  task: Pick<ResearchTaskSummary, "id" | "title" | "goal" | "status" | "revision">
  project: ResearchScope
  lab: ResearchScope
}

export interface ResearchNotificationDelivery {
  id: string
  channel: "email"
  destination: string
  status: "pending" | "sent" | "failed" | "skipped"
  attempt_count: number
  delivered_at?: string | null
  updated_at: string
}

export interface ResearchNotification {
  id: string
  lab_id: string
  project_id: string
  task_id: string
  action_id?: string | null
  work_item_id?: string | null
  approval_id?: string | null
  recipient_user_id: string
  kind: "work_item_assigned" | "work_item_review_requested" | "approval_requested"
  priority: "normal" | "high"
  title: string
  message: string
  target_path: string
  read_at?: string | null
  created_at: string
  updated_at: string
  deliveries: ResearchNotificationDelivery[]
  task: Pick<ResearchTaskSummary, "id" | "title" | "status">
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
  tool_keys: string[]
  knowledge_ids: string[]
  resource_type_ids: string[]
  service_offering_ids: string[]
  compute_environment_ids: string[]
  deadline_at?: string
  budget_limit?: string
  budget_currency?: string
  owner_user_id?: string
  ai_model?: string
}

export interface AiraResearchTaskDraftRequest {
  project_id: string
  research_question: string
  additional_constraints?: string
  autonomy_level: ResearchTaskSummary["autonomy_level"]
}

export interface AiraResearchTaskDraftResponse {
  draft: ResearchTaskDraft
  rationale: string
  assumptions: string[]
  warnings: string[]
  model: string
  boundary: string
}

export interface ResearchTaskPreview {
  preview_digest: string
  command: Record<string, unknown>
  destination: { lab: ResearchScope, project: ResearchScope }
  owner: ResearchUser
  protocols: ResearchProtocolRef[]
  tools: Array<{
    key: string
    version: string
    name: string
    description: string
    risk: string
  }>
  executor_bindings: ResearchEnvironmentExecutorBinding[]
  autonomy_policy: ResearchAutonomyPolicySnapshot
  knowledge: ResearchKnowledgeRef[]
  resources: ResearchResourceRequirement[]
  services: ResearchServiceRequirement[]
  compute: ResearchComputeRequirement[]
  operational_limits: {
    deadline_at?: string | null
    budget_limit?: string | null
    budget_currency?: string | null
  }
  effects: string[]
  warnings: string[]
  ai_instance_available: boolean
  ai_path_available: boolean
}

export interface ResearchRunDraft {
  expected_task_revision: number
  source_run_id: string
  kind: ResearchRunOrigin["kind"]
  purpose: string
  idempotency_key: string
}

export interface ResearchRunPreview {
  preview_digest: string
  command: Record<string, unknown>
  destination: {
    lab: ResearchScope
    project: ResearchScope
    task: { id: string, title: string }
  }
  source_run: {
    id: string
    run_number: number
    status: ResearchRunStatus
    environment_digest: string
    result_digest: string
  }
  new_run: { run_number: number, kind: ResearchRunOrigin["kind"] }
  effects: string[]
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

export interface ManualHumanWorkActionDraft {
  assignee_user_id?: string
  request: HumanWorkRequest
  due_at?: string
  idempotency_key: string
}

export interface ManualHumanWorkActionPreview {
  preview_digest: string
  command: Record<string, unknown>
  destination: {
    lab: ResearchScope
    project: ResearchScope
    task: Pick<ResearchTaskSummary, "id" | "title">
    run: { id: string, number: number }
  }
  assignee: ResearchUser
  effects: string[]
}

export interface HumanWorkSubmissionDraft {
  expected_revision: number
  values: Record<string, unknown>
  data_asset_version_ids: string[]
  note: string
}

export interface HumanWorkReviewDraft {
  expected_revision: number
  expected_action_revision: number
  decision: "accept" | "changes_requested"
  reason: string
}

export interface HumanWorkCommandPreview {
  preview_digest: string
  command: Record<string, unknown>
  effects: string[]
  completion_criteria?: string
  evidence_kind?: HumanWorkRequest["evidence_kind"]
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

export function draftResearchTaskWithAira(payload: AiraResearchTaskDraftRequest) {
  return getData<AiraResearchTaskDraftResponse>({
    url: "/research-tasks/draft-with-aira",
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

export function fetchResearchResultPackage(taskId: string, runId?: string) {
  return getData<ResearchResultPackageEnvelope>({
    url: `/research-tasks/${taskId}/result-package`,
    params: { run_id: runId },
    metadata: { showError: false },
  })
}

export async function downloadResearchResultPackage(
  taskId: string,
  format: "json" | "markdown",
  language: "en" | "zh",
  runId?: string,
) {
  const { data, error } = await request<Blob, "blob">({
    url: `/research-tasks/${taskId}/result-package/export`,
    params: { run_id: runId, format, language },
    responseType: "blob",
    metadata: { showError: false },
  })
  if (error)
    throw error
  if (!data)
    throw new Error("Research Result Package export returned no data")
  return data
}

export function previewResearchRun(taskId: string, payload: ResearchRunDraft) {
  return getData<ResearchRunPreview>({
    url: `/research-tasks/${taskId}/runs/preview`,
    method: "POST",
    data: payload,
  })
}

export function createResearchRun(
  taskId: string,
  payload: ResearchRunDraft & { preview_digest: string },
) {
  return getData<ResearchTaskDetail>({
    url: `/research-tasks/${taskId}/runs`,
    method: "POST",
    data: payload,
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
  review_recommendation_id?: string
  reproduction_assessment?: ResearchReproductionAssessment
  reason?: string
}) {
  return getData<ResearchTaskDetail>({
    url: `/research-tasks/${taskId}/complete`,
    method: "POST",
    data: payload,
  })
}

export function generateResearchReviewRecommendation(
  taskId: string,
  expectedTaskRevision: number,
) {
  return getData<ResearchReviewRecommendation>({
    url: `/research-tasks/${taskId}/review-recommendations`,
    method: "POST",
    data: { expected_task_revision: expectedTaskRevision },
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

export function previewManualHumanWorkAction(
  taskId: string,
  payload: ManualHumanWorkActionDraft,
) {
  return getData<ManualHumanWorkActionPreview>({
    url: `/research-tasks/${taskId}/human-actions/preview`,
    method: "POST",
    data: payload,
  })
}

export function createManualHumanWorkAction(
  taskId: string,
  payload: ManualHumanWorkActionDraft & { preview_digest: string },
) {
  return getData<ResearchAction>({
    url: `/research-tasks/${taskId}/human-actions`,
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

export function previewHumanWorkSubmission(
  workItemId: string,
  payload: HumanWorkSubmissionDraft,
) {
  return getData<HumanWorkCommandPreview>({
    url: `/research-work-items/${workItemId}/submission/preview`,
    method: "POST",
    data: payload,
  })
}

export function submitHumanWork(
  workItemId: string,
  payload: HumanWorkSubmissionDraft & { preview_digest: string },
) {
  return getData<ResearchWorkItemDetail>({
    url: `/research-work-items/${workItemId}/submission`,
    method: "POST",
    data: payload,
  })
}

export function previewHumanWorkReview(
  workItemId: string,
  payload: HumanWorkReviewDraft,
) {
  return getData<HumanWorkCommandPreview>({
    url: `/research-work-items/${workItemId}/review/preview`,
    method: "POST",
    data: payload,
  })
}

export function reviewHumanWork(
  workItemId: string,
  payload: HumanWorkReviewDraft & { preview_digest: string },
) {
  return getData<ResearchWorkItemDetail>({
    url: `/research-work-items/${workItemId}/review`,
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

export function fetchResearchNotifications(params: {
  unreadOnly?: boolean
  page?: number
  pageSize?: number
} = {}) {
  return getData<{
    notifications: ResearchNotification[]
    total_count: number
    unread_count: number
  }>({
    url: "/research-notifications",
    params: {
      unread_only: params.unreadOnly || undefined,
      page: params.page || 1,
      page_size: params.pageSize || 20,
    },
    metadata: { showError: false },
  })
}

export function readResearchNotification(notificationId: string) {
  return getData<ResearchNotification>({
    url: `/research-notifications/${notificationId}/read`,
    method: "POST",
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
