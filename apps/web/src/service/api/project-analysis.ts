import type { AnalysisField, AnalysisRecipe, AnalysisResult, AnalysisSelection, AnalysisSource, BuiltinAnalysisRun } from "./analysis"
import { request } from "../request"

export interface ProjectAnalysisSlot {
  slot_id: string
  label: string
  recipe: AnalysisRecipe
}
export interface ProjectAnalysisOutput {
  output_id: string
  slot_id: string
  field: string
  semantic_label: string
  unit: string | null
}
export interface ProjectAnalysisJoin {
  left_slot_id: string
  right_slot_id: string
  kind: "inner" | "left"
  cardinality: "one_to_one"
  keys: Array<{ left_field: string, right_field: string }>
  missing_key_policy: "error" | "exclude"
  duplicate_key_policy: "error"
  semantic_alignment_confirmed: boolean
  outputs: ProjectAnalysisOutput[]
  recipe: AnalysisRecipe
}
export interface ProjectAnalysisRecipe {
  kind: "project"
  schema_version: 1
  mode: "evidence_synthesis" | "relational"
  slots: ProjectAnalysisSlot[]
  join: ProjectAnalysisJoin | null
}
export interface ProjectAnalysisSelection {
  schema: "airalogy.project-selection.v1"
  inputs: Array<{ slot_id: string, protocol_id: string, selection: AnalysisSelection }>
}
export interface ProjectAnalysisProtocol {
  protocol_id: string
  protocol_name: string
  fields: AnalysisField[]
  protocol_versions: string[]
  own_records_only: boolean
}
export interface ProjectAnalysisContext {
  project_id: string
  project_name: string
  protocols: ProjectAnalysisProtocol[]
  next_offset: number | null
  limits: { max_inputs: number, max_records: number }
  ai_available: false
}
export interface ProjectAnalysisJoinAuditSide {
  slot_id: string
  total: number
  filtered_out: number
  key_missing: number
  invalid_keys: number
  excluded: number
  duplicate_keys: number
  duplicate_rows: number
  matched: number
  unmatched: number
}
export interface ProjectAnalysisJoinAudit {
  left: ProjectAnalysisJoinAuditSide
  right: ProjectAnalysisJoinAuditSide
  output_rows: number
}
export interface ProjectAnalysisResult {
  schema: "airalogy.project-result.v1"
  engine_version: "airalogy.project-analysis.v1"
  mode: ProjectAnalysisRecipe["mode"]
  source_digest: string
  recipe_digest: string
  counts: { protocols: number, records: number }
  local_results: Array<{ slot_id: string, label: string, source_digest: string, recipe_digest: string, report: AnalysisResult }>
  join: null | {
    audit: ProjectAnalysisJoinAudit
    fields: Array<ProjectAnalysisOutput & { type: string | string[] }>
    rows: Array<{
      row_id: string
      values: Record<string, string | number | boolean | null>
      sources: Record<string, ProjectAnalysisRecordRef | null>
      field_lineage: Record<string, (ProjectAnalysisRecordRef & { field_path: ["var", string] }) | null>
    }>
    report: AnalysisResult
  }
  warnings: Array<{ code: string, slot_id?: string, count?: number }>
}
export interface ProjectAnalysisRecordRef {
  protocol_id: string
  record_id: string
  record_version: number
  record_hash: string
  protocol_version: string
  protocol_version_id: string
}
export interface ProjectAnalysisRun extends Omit<BuiltinAnalysisRun, "protocol_id" | "recipe" | "source_selection" | "source_snapshot" | "result"> {
  source_scope: "project"
  protocol_id: null
  recipe: ProjectAnalysisRecipe
  source_selection: ProjectAnalysisSelection
  source_snapshot?: { inputs: Array<{ slot_id: string, label: string, snapshot: NonNullable<BuiltinAnalysisRun["source_snapshot"]> }> }
  result: ProjectAnalysisResult | null
}
export interface ProjectAnalysisPipelineRevision {
  id: string
  pipeline_id: string
  revision: number
  recipe: ProjectAnalysisRecipe
  source_selection: ProjectAnalysisSelection
  recipe_digest: string
  created_at: string
}
export interface ProjectAnalysisPipeline {
  id: string
  project_id: string
  protocol_id: null
  source_scope: "project"
  title: string
  current_revision: number
  current_recipe: ProjectAnalysisRecipe
  revisions?: ProjectAnalysisPipelineRevision[]
  created_at: string
  updated_at: string
}
export interface ProjectAnalysisPreviewRequest {
  project_id: string
  question: string
  selection: ProjectAnalysisSelection
  recipe: ProjectAnalysisRecipe
  pipeline_revision_id?: string
  rerun_of_id?: string
}
export interface ProjectAnalysisPreview {
  id: string
  project_id: string
  protocol_id: null
  source_scope: "project"
  question: string
  recipe: ProjectAnalysisRecipe
  source_selection: ProjectAnalysisSelection
  source_digest: string
  recipe_digest: string
  preview_digest: string
  expires_at: string
  summary: ProjectAnalysisResult & {
    visibility: "private"
    project_name: string
    source_inputs: Array<{ slot_id: string, protocol_id: string, record_count: number, sources: AnalysisSource[], schemas: Array<{ id: string, version: string }> }>
  }
}
export type ProjectEvidenceRelation = "supports" | "contradicts" | "inconclusive"
export interface ProjectInterpretationContent {
  judgement: ProjectEvidenceRelation
  summary: string
  findings: Array<{ slot_id: string, field: string, relation: ProjectEvidenceRelation, note: string }>
  limitations: string[]
  unanswered_questions: string[]
}
export interface ProjectInterpretationRevision {
  id: string
  analysis_run_id: string
  revision: number
  result_digest: string
  content: ProjectInterpretationContent
  resolved_evidence: unknown[] | Record<string, unknown>
  content_digest: string
  created_by_user_id: string
  created_at: string
}
export interface ProjectAnalysisComparison {
  analysis_id: string
  baseline_id: string
  current_result_digest: string
  baseline_result_digest: string
  recipe_changed: boolean
  inputs: Array<{ slot_id: string, protocol_id: string, added: ProjectAnalysisRecordRef[], removed: ProjectAnalysisRecordRef[], changed: Array<{ before: ProjectAnalysisRecordRef, after: ProjectAnalysisRecordRef }> }>
  local_results: Array<{ slot_id: string, changed: boolean, before: AnalysisResult, after: AnalysisResult }>
  join: { changed: boolean, before: ProjectAnalysisResult["join"], after: ProjectAnalysisResult["join"] }
  warnings: Array<{ code: string } | string>
}

async function getData<T>(options: Parameters<typeof request<T>>[0]): Promise<T> {
  const { data, error } = await request<T>({ ...options, metadata: { showError: false } })
  if (error)
    throw error
  if (data === null)
    throw new Error("Project analysis returned no data")
  return data
}
export function fetchProjectAnalysisContext(projectId: string, offset = 0) {
  return getData<ProjectAnalysisContext>({ url: `/projects/${projectId}/project-analysis-context`, params: { offset, limit: 100 } })
}
export function previewProjectAnalysis(payload: ProjectAnalysisPreviewRequest) {
  return getData<ProjectAnalysisPreview>({ url: "/analyses/project/preview", method: "POST", data: payload })
}
export function fetchProjectAnalysisSourceContext(projectId: string, protocolId: string, selection: AnalysisSelection) {
  return getData<ProjectAnalysisProtocol>({ url: `/projects/${projectId}/project-analysis-context/${protocolId}`, method: "POST", data: selection })
}
export function fetchProjectAnalysisRun(id: string) {
  return getData<ProjectAnalysisRun>({ url: `/analyses/${id}` })
}
export function fetchProjectAnalysisRuns(projectId: string) {
  return getData<{ items: ProjectAnalysisRun[] }>({ url: `/projects/${projectId}/analyses`, params: { source_scope: "project" } })
}
export function fetchProjectAnalysisMethods(projectId: string) {
  return getData<{ items: ProjectAnalysisPipeline[] }>({ url: `/projects/${projectId}/analysis-pipelines`, params: { source_scope: "project" } })
}
export function fetchProjectAnalysisMethod(id: string) {
  return getData<ProjectAnalysisPipeline>({ url: `/analysis-pipelines/${id}` })
}
export function createProjectAnalysis(payload: { preview_id: string, preview_digest: string, client_idempotency_key: string }) {
  return getData<ProjectAnalysisRun>({ url: "/analyses/project", method: "POST", data: payload })
}
export function saveProjectAnalysisMethod(runId: string, title: string) {
  return getData<ProjectAnalysisPipeline>({ url: "/analysis-pipelines", method: "POST", data: { run_id: runId, title } })
}
export function reviseProjectAnalysisMethod(id: string, payload: { recipe: ProjectAnalysisRecipe, source_selection: ProjectAnalysisSelection, expected_revision: number }) {
  return getData<ProjectAnalysisPipelineRevision>({ url: `/analysis-pipelines/${id}/revisions`, method: "POST", data: payload })
}
export function downloadProjectAnalysis(id: string) {
  return getData<ProjectAnalysisRun>({ url: `/analyses/${id}/download` })
}
export function fetchProjectInterpretations(id: string) {
  return getData<{ analysis_id: string, result_digest: string, current_revision: number, items: ProjectInterpretationRevision[] }>({ url: `/analyses/${id}/interpretations` })
}
export function createProjectInterpretation(id: string, payload: { expected_revision: number, result_digest: string, content: ProjectInterpretationContent }) {
  return getData<ProjectInterpretationRevision>({ url: `/analyses/${id}/interpretations`, method: "POST", data: payload })
}
export function compareProjectAnalyses(id: string, baselineId: string) {
  return getData<ProjectAnalysisComparison>({ url: `/analyses/${id}/comparison`, params: { baseline_id: baselineId } })
}
