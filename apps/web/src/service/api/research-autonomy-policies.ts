import { request } from "../request"

export interface ResearchAutonomyRule {
  auto_approve_read_only_tools: boolean
  auto_create_wait_events: boolean
  auto_approve_isolated_compute: boolean
}

export interface ResearchAutonomyPolicyConfig {
  schema: "airalogy.research-autonomy-policy.v1"
  bounded_autopilot: ResearchAutonomyRule
  autonomous_within_policy: ResearchAutonomyRule
  automatic_compute_limits: {
    max_estimated_cost?: string
    currency?: string
    max_timeout_seconds: number
  }
}

export interface ResearchAutonomyPolicySnapshot {
  schema: "airalogy.research-autonomy-policy-snapshot.v1"
  id?: string | null
  revision: number
  source: "platform_default" | "lab_policy"
  policy: ResearchAutonomyPolicyConfig
  policy_digest: string
  updated_at?: string | null
  evaluated_grants?: ResearchAutonomyGrant[]
}

export type ResearchAutonomyLevel = "bounded_autopilot" | "autonomous_within_policy"

export interface ResearchAutonomyTarget {
  schema: "airalogy.research-autonomy-target.v1"
  capability_key: string
  capability_version: string
  executor_type: string
  executor_ref: Record<string, unknown>
  executor_digest: string
  target_digest: string
}

export interface ResearchAutonomyEvaluationAction {
  action_id: string
  run_id?: string
  status: "completed" | "failed" | "cancelled"
  preview_digest?: string
  output_digest?: string
  completed_at?: string | null
}

export interface ResearchAutonomyEvaluation {
  schema: "airalogy.research-autonomy-evaluation.v1"
  target: ResearchAutonomyTarget
  evaluated_at?: string | null
  criteria: {
    minimum_supervised_successes: number
    maximum_sample: number
    allowed_failures: number
  }
  sample: ResearchAutonomyEvaluationAction[]
  completed_count: number
  failure_count: number
  passed: boolean
  evaluation_digest: string
}

export interface ResearchAutonomyGrant {
  schema: "airalogy.research-autonomy-grant.v1"
  id: string
  lab_id: string
  target: ResearchAutonomyTarget
  revision: number
  enabled: boolean
  allowed_levels: ResearchAutonomyLevel[]
  evaluation: ResearchAutonomyEvaluation
  valid_until: string
  reason: string
  created_by_user_id: string
  updated_by_user_id: string
  created_at: string
  updated_at: string
}

export interface ResearchAutonomyGrantDraft {
  lab_id: string
  target_digest: string
  expected_revision: number
  allowed_levels: ResearchAutonomyLevel[]
  valid_until: string
  reason: string
}

export interface ResearchAutonomyGrantPreview {
  preview_digest: string
  command: Record<string, unknown>
  destination: { lab_id: string, lab_uid: string, lab_name: string }
  current?: ResearchAutonomyGrant | null
  effects: string[]
}

export interface ResearchAutonomyGrantRevokeDraft {
  lab_id: string
  expected_revision: number
  reason: string
}

export interface ResearchAutonomyGrantRevokePreview {
  preview_digest: string
  command: Record<string, unknown>
  current: ResearchAutonomyGrant
  effects: string[]
}

export interface ResearchAutonomyPolicyDraft {
  lab_id: string
  expected_revision: number
  policy: ResearchAutonomyPolicyConfig
  reason: string
}

export interface ResearchAutonomyPolicyAudit {
  id: string
  revision: number
  snapshot: ResearchAutonomyPolicySnapshot
  reason: string
  actor_user_id: string
  created_at: string
}

export interface ResearchAutonomyPolicyPreview {
  preview_digest: string
  command: Record<string, unknown>
  destination: { lab_id: string, lab_uid: string, lab_name: string }
  current: ResearchAutonomyPolicySnapshot
  effects: string[]
}

async function getData<T>(options: Parameters<typeof request<T>>[0]): Promise<T> {
  const { data, error } = await request<T>(options)
  if (error)
    throw error
  if (!data)
    throw new Error("Research autonomy policy service returned no data")
  return data
}

export function fetchResearchAutonomyPolicy(labId: string) {
  return getData<{ policy: ResearchAutonomyPolicySnapshot, can_manage: boolean }>({
    url: "/research-autonomy-policies",
    params: { lab_id: labId },
    metadata: { showError: false },
  })
}

export function fetchResearchAutonomyPolicyAudits(labId: string) {
  return getData<{ items: ResearchAutonomyPolicyAudit[] }>({
    url: "/research-autonomy-policies/audits",
    params: { lab_id: labId },
    metadata: { showError: false },
  })
}

export function previewResearchAutonomyPolicy(payload: ResearchAutonomyPolicyDraft) {
  return getData<ResearchAutonomyPolicyPreview>({
    url: "/research-autonomy-policies/preview",
    method: "POST",
    data: payload,
  })
}

export function confirmResearchAutonomyPolicy(
  payload: ResearchAutonomyPolicyDraft & { preview_digest: string },
) {
  return getData<{ policy: ResearchAutonomyPolicySnapshot, can_manage: boolean }>({
    url: "/research-autonomy-policies",
    method: "PUT",
    data: payload,
  })
}

export function fetchResearchAutonomyEvaluations(labId: string) {
  return getData<{ items: ResearchAutonomyEvaluation[] }>({
    url: "/research-autonomy-policies/evaluations",
    params: { lab_id: labId },
    metadata: { showError: false },
  })
}

export function fetchResearchAutonomyGrants(labId: string) {
  return getData<{ items: ResearchAutonomyGrant[], can_manage: boolean }>({
    url: "/research-autonomy-policies/grants",
    params: { lab_id: labId },
    metadata: { showError: false },
  })
}

export function previewResearchAutonomyGrant(payload: ResearchAutonomyGrantDraft) {
  return getData<ResearchAutonomyGrantPreview>({
    url: "/research-autonomy-policies/grants/preview",
    method: "POST",
    data: payload,
  })
}

export function confirmResearchAutonomyGrant(
  payload: ResearchAutonomyGrantDraft & { preview_digest: string },
) {
  return getData<ResearchAutonomyGrant>({
    url: "/research-autonomy-policies/grants",
    method: "PUT",
    data: payload,
  })
}

export function previewResearchAutonomyGrantRevocation(
  grantId: string,
  payload: ResearchAutonomyGrantRevokeDraft,
) {
  return getData<ResearchAutonomyGrantRevokePreview>({
    url: `/research-autonomy-policies/grants/${grantId}/revoke/preview`,
    method: "POST",
    data: payload,
  })
}

export function confirmResearchAutonomyGrantRevocation(
  grantId: string,
  payload: ResearchAutonomyGrantRevokeDraft & { preview_digest: string },
) {
  return getData<ResearchAutonomyGrant>({
    url: `/research-autonomy-policies/grants/${grantId}/revoke`,
    method: "POST",
    data: payload,
  })
}
