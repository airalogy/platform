import type { AnalysisField, AnalysisResult } from "./analysis"
import type { ProjectAnalysisJoinAudit, ProjectInterpretationContent } from "./project-analysis"
import type { ResearchEvidence } from "./research-assets"
import { request } from "../request"

export interface AnalysisPublicationSectionSelection {
  section_id: string
  fields: string[]
}

export interface AnalysisPublicationDraft {
  task_id: string
  title: string
  summary: string
  sections: AnalysisPublicationSectionSelection[]
  interpretation_revision_id: string | null
}

export interface AnalysisPublicationContext {
  analysis_id: string
  project_id: string
  source_scope: "protocol" | "project"
  engine_version: string
  result_digest: string
  sections: Array<{ section_id: string, label: string, fields: AnalysisField[] }>
  interpretations: Array<{ id: string, revision: number, summary: string, result_digest: string }>
  tasks: Array<{ id: string, title: string }>
  next_task_offset: number | null
}

export interface AnalysisPublicationSnapshot {
  schema: "airalogy.analysis-evidence-publication.v1"
  analysis: {
    id: string
    source_scope: "protocol" | "project"
    engine_version: string
    source_digest: string
    recipe_digest: string
    result_digest: string
  }
  title: string
  summary: string
  warnings: Array<{ code: string, slot_id?: string, count?: number }>
  sources: Array<{
    slot_id: string
    protocol_id: string
    source_digest: string
    records: Array<{ record_id: string, record_version: number, protocol_version: string, record_hash: string }>
    schemas: Array<{ id: string, version: string, schema_digest: string }>
  }>
  sections: Array<{
    section_id: string
    label: string
    report: Pick<AnalysisResult, "counts" | "fields" | "group_by" | "groups" | "warnings">
  }>
  join_audit: ProjectAnalysisJoinAudit | null
  interpretation: {
    id: string
    revision: number
    content: ProjectInterpretationContent
    resolved_evidence: unknown[] | Record<string, unknown>
    content_digest: string
  } | null
}

export interface AnalysisPublication {
  id: string
  task_id: string
  project_id: string
  analysis_run_id: string
  title: string
  summary: string
  snapshot: AnalysisPublicationSnapshot
  digest: string
  created_by_user_id: string
  created_at: string
  evidence_id: string
}

export interface AnalysisPublicationPreview {
  preview_digest: string
  preview_token: string
  expires_at: string
  destination: { task_id: string, task_title: string, project_id: string, project_name: string }
  publication: AnalysisPublicationSnapshot
  effect: {
    quality_state: "pending"
    requires_review: true
    audience: "task_members_with_all_source_access"
    original_report_remains_private: true
    raw_records_shared: false
  }
}

export function fetchAnalysisPublicationContext(analysisId: string, offset = 0) {
  return request<AnalysisPublicationContext>({
    url: `/analyses/${analysisId}/evidence-publication-context`,
    params: { task_limit: 50, task_offset: offset },
  })
}

export function previewAnalysisPublication(analysisId: string, data: AnalysisPublicationDraft) {
  return request<AnalysisPublicationPreview>({
    url: `/analyses/${analysisId}/evidence-publications/preview`,
    method: "POST",
    data,
  })
}

export function confirmAnalysisPublication(analysisId: string, data: AnalysisPublicationDraft & {
  preview_digest: string
  preview_token: string
  client_idempotency_key: string
}) {
  return request<{ publication: AnalysisPublication, evidence: ResearchEvidence }>({
    url: `/analyses/${analysisId}/evidence-publications`,
    method: "POST",
    data,
  })
}

export function fetchAnalysisPublication(publicationId: string) {
  return request<AnalysisPublication>({ url: `/research-assets/analysis-publications/${publicationId}` })
}
