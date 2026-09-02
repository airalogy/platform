import { request } from "../request"

export interface ResearchHumanExecutorUser {
  id: string
  username: string
  name: string
}

export interface ResearchHumanExecutorSkill {
  key: string
  name: string
  level: number
  verified: boolean
  expires_at: string | null
}

export interface ResearchHumanExecutorProfile {
  id: string
  lab_id: string
  user_id: string
  revision: number
  availability: "available" | "unavailable"
  available_from: string | null
  available_until: string | null
  max_concurrent_items: number
  active_workload: number
  currently_available: boolean
  skills: ResearchHumanExecutorSkill[]
  notes: string
  user: ResearchHumanExecutorUser
  created_by_user_id: string
  updated_by_user_id: string
  created_at: string
  updated_at: string
}

export interface ResearchHumanExecutorProfileDraft {
  lab_id: string
  user_id: string
  expected_revision: number
  availability: ResearchHumanExecutorProfile["availability"]
  available_from: string | null
  available_until: string | null
  max_concurrent_items: number
  skills: ResearchHumanExecutorSkill[]
  notes: string
  reason: string
}

export interface ResearchHumanExecutorProfilePreview {
  preview_digest: string
  command: Record<string, unknown>
  destination: { lab_id: string, lab_uid: string, lab_name: string }
  executor: ResearchHumanExecutorUser
  effects: string[]
}

async function getData<T>(options: Parameters<typeof request<T>>[0]): Promise<T> {
  const { data, error } = await request<T>(options)
  if (error)
    throw error
  if (!data)
    throw new Error("Research Human Executor service returned no data")
  return data
}

export function fetchResearchHumanExecutorProfiles(labId: string) {
  return getData<{
    items: ResearchHumanExecutorProfile[]
    members: ResearchHumanExecutorUser[]
  }>({
    url: "/research-human-executors",
    params: { lab_id: labId },
    metadata: { showError: false },
  })
}

export function previewResearchHumanExecutorProfile(
  payload: ResearchHumanExecutorProfileDraft,
) {
  return getData<ResearchHumanExecutorProfilePreview>({
    url: "/research-human-executors/preview",
    method: "POST",
    data: payload,
  })
}

export function updateResearchHumanExecutorProfile(
  userId: string,
  payload: ResearchHumanExecutorProfileDraft & { preview_digest: string },
) {
  return getData<ResearchHumanExecutorProfile>({
    url: `/research-human-executors/${userId}`,
    method: "PUT",
    data: payload,
  })
}
