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
