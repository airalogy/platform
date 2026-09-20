import type { WorkflowAnalysisPublication } from "./workflow-analysis-methods"
import { request } from "../request"

export interface AnalysisProtocolDestination {
  project_id: string
  name: string
  visibility: "public" | "private"
  lab_uid: string
  project_uid: string
}
export interface AnalysisProtocolTemplate {
  method_id: string
  project_id: string
  target_protocol_id: string | null
  base_protocol_version_id: string | null
  files: Record<string, string>
  destination: AnalysisProtocolDestination
  permissions: { can_create: boolean }
}
export interface AnalysisProtocolDraftRequest {
  method_id: string
  target_protocol_id?: string | null
  base_protocol_version_id?: string | null
  files: Record<string, string>
  reason: string
}
export interface AnalysisProtocolRevisionRequest {
  expected_revision: number
  files: Record<string, string>
  reason: string
}
export interface AnalysisProtocolRevision {
  draft_id: string
  revision: number
  files: Record<string, string>
  package_digest: string
  manifest_digest: string
  method_digest: string
  reason: string
  created_by_user_id: string
  created_at: string
}
export interface AnalysisProtocolDraftSummary {
  id: string
  project_id: string
  method_id: string
  target_protocol_id: string | null
  base_protocol_version_id: string | null
  created_by_user_id: string
  revision: number
  state: "draft" | "reviewed" | "rejected" | "applied"
  name?: string
  package_digest: string
}
export interface AnalysisProtocolDraft extends AnalysisProtocolDraftSummary {
  destination?: AnalysisProtocolDestination
  current_revision: AnalysisProtocolRevision
  revisions: Array<Omit<AnalysisProtocolRevision, "files">>
  reviews: Array<{ id: string, revision: number, decision: "reviewed" | "rejected", package_digest: string, note: string, reviewed_by_user_id: string, created_at: string }>
  applied: null | { protocol_id: string, protocol_version_id: string, version: string, lab_uid: string, project_uid: string, protocol_uid: string }
  permissions: { can_edit: boolean, can_review: boolean, can_publish: boolean }
}
export interface AnalysisProtocolPreview {
  preview_digest: string
  preview_token: string
  expires_at: string
  content: AnalysisProtocolDraftRequest & { project_id: string }
  package_digest: string
  manifest_digest: string
  files_manifest: Array<{ path: string, size_bytes: number, sha256: string }>
  destination: AnalysisProtocolDestination
}
export interface AnalysisProtocolPreviewConfirmation {
  preview_digest: string
  preview_token: string
  idempotency_key: string
}

export function supportsAnalysisProtocolDraft(method: Pick<WorkflowAnalysisPublication, "engine_version"> | null | undefined) {
  return method?.engine_version === "airalogy.analysis.v1" || method?.engine_version === "airalogy.project-analysis.v1"
}

/** Preserve the server's entire exact file set; only these two text files are editable. */
export function editAnalysisProtocolFile(files: Record<string, string>, path: string, value: string) {
  if ((path !== "protocol.toml" && path !== "protocol.aimd") || !Object.hasOwn(files, path))
    return files
  return { ...files, [path]: value }
}

export function analysisProtocolDraftFingerprint(files: Record<string, string>, reason: string) {
  return JSON.stringify({ files: Object.fromEntries(Object.entries(files).sort(([a], [b]) => a.localeCompare(b))), reason })
}

export function analysisProtocolReviewRequest(draft: AnalysisProtocolDraft, decision: "reviewed" | "rejected", note: string) {
  return { expected_revision: draft.revision, package_digest: draft.current_revision.package_digest, decision, note }
}

export function analysisProtocolPublishRequest(draft: AnalysisProtocolDraft) {
  return { expected_revision: draft.revision, package_digest: draft.current_revision.package_digest }
}

async function getData<T>(config: Parameters<typeof request<T>>[0]): Promise<T> {
  const { data, error } = await request<T>({ ...config, metadata: { showError: false } })
  if (error)
    throw error
  if (data === null)
    throw new Error("Analysis Protocol draft service returned no data")
  return data
}
const base = "/analysis-protocol-drafts"
export function fetchAnalysisProtocolTemplate(methodId: string, targetProtocolId?: string) {
  return getData<AnalysisProtocolTemplate>({ url: `${base}/template`, method: "POST", data: { method_id: methodId, ...(targetProtocolId ? { target_protocol_id: targetProtocolId } : {}) } })
}
export function fetchAnalysisProtocolDrafts(methodId: string) {
  return getData<{ items: AnalysisProtocolDraftSummary[] }>({ url: base, params: { method_id: methodId } })
}
export function fetchAnalysisProtocolDraft(id: string) {
  return getData<AnalysisProtocolDraft>({ url: `${base}/${id}` })
}
export function fetchAnalysisProtocolRevision(id: string, revision: number) {
  return getData<AnalysisProtocolRevision>({ url: `${base}/${id}/revisions/${revision}` })
}
export function previewAnalysisProtocolDraft(payload: AnalysisProtocolDraftRequest) {
  return getData<AnalysisProtocolPreview>({ url: `${base}/preview`, method: "POST", data: payload })
}
export function confirmAnalysisProtocolDraft(payload: AnalysisProtocolDraftRequest & AnalysisProtocolPreviewConfirmation) {
  return getData<AnalysisProtocolDraft>({ url: `${base}/confirm`, method: "POST", data: payload })
}
export function previewAnalysisProtocolRevision(id: string, payload: AnalysisProtocolRevisionRequest) {
  return getData<AnalysisProtocolPreview>({ url: `${base}/${id}/revisions/preview`, method: "POST", data: payload })
}
export function confirmAnalysisProtocolRevision(id: string, payload: AnalysisProtocolRevisionRequest & AnalysisProtocolPreviewConfirmation) {
  return getData<AnalysisProtocolDraft>({ url: `${base}/${id}/revisions/confirm`, method: "POST", data: payload })
}
export function reviewAnalysisProtocolDraft(id: string, payload: ReturnType<typeof analysisProtocolReviewRequest>) {
  return getData<AnalysisProtocolDraft>({ url: `${base}/${id}/review`, method: "POST", data: payload })
}
export function previewAnalysisProtocolPublish(id: string, payload: ReturnType<typeof analysisProtocolPublishRequest>) {
  return getData<AnalysisProtocolPreview>({ url: `${base}/${id}/publish/preview`, method: "POST", data: payload })
}
export function publishAnalysisProtocolDraft(id: string, payload: ReturnType<typeof analysisProtocolPublishRequest> & Omit<AnalysisProtocolPreviewConfirmation, "idempotency_key">) {
  return getData<AnalysisProtocolDraft>({ url: `${base}/${id}/publish`, method: "POST", data: payload })
}
