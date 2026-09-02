import { request } from "../request"

export type ResearchLogScope = "personal" | "lab" | "project"
export type ResearchLogKind = "progress" | "meeting" | "reflection" | "blocker" | "milestone"
export type ResearchLogSource = "all" | "manual" | "record" | "protocol" | "knowledge" | "research"

export interface ResearchLogScopeParams {
  scope_type: ResearchLogScope
  lab_id?: string
  project_id?: string
}

export interface ResearchLogUser {
  id: string
  username: string
  name: string
}

export interface ResearchLogContext {
  id: string
  uid: string
  name: string
}

export interface ResearchLogAssetLink {
  asset_type: "paper" | "protocol" | "record" | "knowledge" | "research_task" | "data_asset" | "external"
  asset_id: string
  version?: string
  label?: string
  url?: string
}

export interface ResearchLogManualEntry {
  id: string
  entry_type: "manual"
  event_type: string
  immutable: false
  can_edit: boolean
  scope_type: ResearchLogScope
  owner_user_id?: string | null
  lab_id?: string | null
  project_id?: string | null
  kind: ResearchLogKind
  title: string
  body: string
  goal: string
  completed_items: string[]
  evidence: string[]
  risks: string[]
  next_steps: string[]
  asset_links: ResearchLogAssetLink[]
  revision: number
  author: ResearchLogUser | null
  created_by_user_id: string
  occurred_at: string
  created_at: string
  updated_at: string
}

export interface ResearchLogSystemEvent {
  id: string
  entry_type: "system"
  event_type: string
  kind: "system"
  title: string
  summary: string
  occurred_at: string
  author: ResearchLogUser | null
  immutable: true
  can_edit: false
  lab: ResearchLogContext | null
  project: ResearchLogContext | null
  payload?: Record<string, unknown>
  asset?: Record<string, string>
}

export type ResearchLogTimelineItem = ResearchLogManualEntry | ResearchLogSystemEvent

export interface ResearchLogDraft extends ResearchLogScopeParams {
  kind: ResearchLogKind
  title: string
  body: string
  goal: string
  completed_items: string[]
  evidence: string[]
  risks: string[]
  next_steps: string[]
  asset_links: ResearchLogAssetLink[]
  occurred_at?: string
}

async function getData<T>(options: Parameters<typeof request<T>>[0]): Promise<T> {
  const { data, error } = await request<T>(options)
  if (error)
    throw error
  if (data === null)
    throw new Error("Research Log service returned no data")
  return data
}

export function fetchResearchLogTimeline(params: ResearchLogScopeParams & {
  source?: ResearchLogSource
  actor_user_id?: string
  date_from?: string
  date_to?: string
  page?: number
  page_size?: number
}) {
  return getData<{
    items: ResearchLogTimelineItem[]
    total_count: number
    can_write: boolean
    page: number
    page_size: number
  }>({
    url: "/research-log/timeline",
    params,
    metadata: { showError: false },
  })
}

export function createResearchLogEntry(payload: ResearchLogDraft) {
  return getData<ResearchLogManualEntry>({
    url: "/research-log/entries",
    method: "POST",
    data: payload,
  })
}

export function updateResearchLogEntry(entryId: string, payload: Partial<ResearchLogDraft> & {
  expected_revision: number
  change_summary: string
}) {
  const { scope_type: _scopeType, lab_id: _labId, project_id: _projectId, ...data } = payload
  return getData<ResearchLogManualEntry>({
    url: `/research-log/entries/${entryId}`,
    method: "PATCH",
    data,
  })
}

export function fetchResearchLogRevisions(entryId: string) {
  return getData<{ revisions: Array<{
    id: string
    revision: number
    snapshot: Record<string, unknown>
    change_summary: string
    created_at: string
  }> }>({
    url: `/research-log/entries/${entryId}/revisions`,
    metadata: { showError: false },
  })
}
