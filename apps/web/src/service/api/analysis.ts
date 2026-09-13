import type { AnalysisSelection } from "@/utils/analysis-selection"
import type { AnalysisComputeRecipe, AnalysisComputeResult } from "./analysis-compute"
import { createAnalysisContextRequest } from "@/utils/analysis-context"
import { request } from "../request"

export type { AnalysisRecordFilters, AnalysisRecordReference, AnalysisSelection, AnalysisSelectionTransfer } from "@/utils/analysis-selection"
export { consumeAnalysisSelectionTransfer, createAnalysisSelectionTransfer, discardAnalysisSelectionTransfer } from "@/utils/analysis-selection"

export interface AnalysisField {
  key: string
  title: string
  type: string | string[]
  unit?: string | null
  protocol_version?: string
  unsupported_reason?: string
}

export interface AnalysisContext {
  protocol_id: string
  project_id: string
  protocol_name: string
  project_name: string
  fields: AnalysisField[]
  protocol_versions: string[]
  ai_available: boolean
  own_records_only: boolean
  limits: { max_records: number }
}

export interface AnalysisRecipe {
  schema_version: 1
  numeric_fields: string[]
  group_by: string[]
  filters: AnalysisFilter[]
  missing_policy: "exclude" | "error"
  chart: "bar" | "line" | "none"
}

export type AnalysisScalar = string | number | boolean
export interface AnalysisFilter {
  field: string
  op: "eq" | "ne" | "gt" | "gte" | "lt" | "lte" | "in" | "missing" | "present"
  value: AnalysisScalar | AnalysisScalar[] | null
}

export interface AnalysisSource {
  record_id: string
  record_version: number
  protocol_version: string
  user_id: string
  number: number
  created_at: string
  record_hash: string
}

export interface AnalysisCounts {
  total: number
  included: number
  filtered_out: number
}

export interface AnalysisWarning {
  code: string
  field?: string
  count: number
}

export interface AnalysisStatistics {
  count: number
  missing: number
  invalid: number
  mean: number | null
  median: number | null
  min: number | null
  max: number | null
  sum: number | null
  sample_stddev: number | null
}

export interface AnalysisGroup {
  key: Array<{ field: string, type: string, value: AnalysisScalar | null }>
  row_count: number
  fields: Record<string, AnalysisStatistics>
}

export interface AnalysisResult {
  engine_version: string
  counts: AnalysisCounts
  fields: AnalysisField[]
  group_by: AnalysisField[]
  groups: AnalysisGroup[]
  table: AnalysisGroup[]
  chart: {
    type: AnalysisRecipe["chart"]
    statistic: "mean"
    series: Array<{
      field: string
      title: string
      unit: string
      points: Array<{ group_index: number, value: number | null, count: number }>
    }>
  }
  warnings: AnalysisWarning[]
}

export interface AnalysisPreviewRequest {
  protocol_id: string
  selection: AnalysisSelection
  recipe: AnalysisRecipe
  question?: string
  pipeline_revision_id?: string
  rerun_of_id?: string
  ai_draft_id?: string
}

export interface AnalysisPreview {
  ai_provenance?: AnalysisAIProvenance | Record<string, never>
  id: string
  protocol_id: string
  project_id: string
  question: string
  recipe: AnalysisRecipe
  source_selection: AnalysisSelection
  source_digest: string
  recipe_digest: string
  preview_digest: string
  summary: {
    counts: AnalysisCounts
    fields: AnalysisField[]
    field_stats: Record<string, Pick<AnalysisStatistics, "count" | "missing" | "invalid">>
    group_count: number
    warnings: AnalysisWarning[]
    engine_version: string
    protocol_name: string
    project_name: string
    visibility: "private"
    sources: AnalysisSource[]
  }
  expires_at: string
}

export interface BuiltinAnalysisRun {
  ai_provenance?: AnalysisAIProvenance | Record<string, never>
  id: string
  status: "pending" | "running" | "succeeded" | "failed" | "cancelled"
  protocol_id: string
  project_id: string
  created_by_user_id: string
  question: string
  recipe: AnalysisRecipe
  source_selection: AnalysisSelection
  source_snapshot?: {
    schema_version: 1
    protocol_id: string
    records: Array<AnalysisSource & { data: Record<string, unknown> }>
    schemas: Array<{ id: string, version: string, json_schema: Record<string, unknown>, fields: Record<string, unknown> }>
    fields: AnalysisField[]
  }
  source_digest: string
  recipe_digest: string
  preview_digest: string
  result_digest: string | null
  result?: AnalysisResult | null
  pipeline_revision_id: string | null
  rerun_of_id: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  engine_version: string
  error: string | null
}

export interface ComputeAnalysisRun extends Omit<BuiltinAnalysisRun, "recipe" | "result"> {
  recipe: AnalysisComputeRecipe
  result?: AnalysisComputeResult | null
}

export type AnalysisRun = BuiltinAnalysisRun | ComputeAnalysisRun

export interface AnalysisPipeline {
  id: string
  title: string
  protocol_id: string
  project_id: string
  created_by_user_id: string
  current_revision: number
  current_recipe: AnalysisRecipe | AnalysisComputeRecipe
  current_revision_id?: string
  source_selection?: AnalysisSelection
  revisions?: AnalysisPipelineRevision[]
  created_at: string
  updated_at: string
}

export interface AnalysisPipelineRevision {
  id: string
  pipeline_id: string
  revision: number
  recipe: AnalysisRecipe | AnalysisComputeRecipe
  recipe_digest: string
  source_selection: AnalysisSelection
  provenance: {
    method_digest: string
    analysis_id?: string
    source_digest?: string
    result_digest?: string
    parent_revision_id?: string
    parent_recipe_digest?: string
  }
  created_by_user_id: string
  created_at: string
}

export interface AnalysisDraftOutput {
  mode: "builtin" | "clarification_required" | "compute_required"
  title: string
  explanation: string
  assumptions: string[]
  recipe: AnalysisRecipe | null
  clarification_questions: string[]
  compute_requirements: string[]
}

export interface AnalysisComputeDraftOutput {
  mode: "compute" | "clarification_required"
  title: string
  explanation: string
  assumptions: string[]
  recipe: AnalysisComputeRecipe | null
  clarification_questions: string[]
}

export interface AnalysisGroundedMetric {
  field: string
  group_index: number
  statistic: keyof AnalysisStatistics
  value: number | null
  unit: string
  n: number
  row_count: number
  group: AnalysisGroup["key"]
}

export interface AnalysisBuiltinInterpretation {
  result_kind?: "builtin"
  summary: string
  observations: Array<{ text: string, metrics: AnalysisGroundedMetric[] }>
  limitations: string[]
  next_steps: string[]
  interpretation_origin?: "ai"
  numeric_values_origin?: "computed_result"
}

export interface AnalysisComputeMetric {
  pointer: string
  value: string | number | boolean | null
}

export interface AnalysisComputeInterpretation extends Omit<AnalysisBuiltinInterpretation, "observations" | "result_kind"> {
  result_kind: "compute"
  observations: Array<{ text: string, metrics: AnalysisComputeMetric[] }>
}

export type AnalysisInterpretation = AnalysisBuiltinInterpretation | AnalysisComputeInterpretation

export interface AnalysisAIRequest {
  id: string
  kind: "draft" | "compute_draft" | "interpretation"
  protocol_id: string
  project_id: string
  analysis_run_id: string | null
  previous_request_id: string | null
  question: string
  locale: "en-US" | "zh-CN"
  model: string
  operation_id: string
  state: "generating" | "generated" | "failed"
  output: AnalysisDraftOutput | AnalysisComputeDraftOutput | AnalysisInterpretation | null
  error: "model_timeout" | "invalid_proposal" | "model_unavailable" | "generation_interrupted" | "ai_disabled" | "context_changed" | "source_access_changed" | null
  source_selection: AnalysisSelection
  source_digest: string
  input_digest: string
  output_digest: string | null
  created_at: string
  finished_at: string | null
  deadline: string
}

export interface AnalysisAIProvenance {
  request_id: string
  model: string
  operation_id: string
  input_digest: string
  output_digest: string
  source_digest: string
  generated_at: string
  generation_question: string
  generation: AnalysisDraftOutput | AnalysisComputeDraftOutput
  user_edited: boolean
  inherited?: boolean
  digest: string
}

export interface AnalysisAIDraftRequest {
  id: string
  protocol_id: string
  selection: AnalysisSelection
  question: string
  locale: "en-US" | "zh-CN"
  previous_request_id?: string
}

export interface AnalysisAIComputeDraftRequest extends AnalysisAIDraftRequest {
  environment_revision_id: string
  language: "python" | "r"
}

export interface AnalysisAIInterpretationRequest {
  id: string
  question?: string
  locale: "en-US" | "zh-CN"
}

async function getData<T>(options: Parameters<typeof request<T>>[0]): Promise<T> {
  const { data, error } = await request<T>(options)
  if (error)
    throw error
  if (data === null)
    throw new Error("Analysis service returned no data")
  return data
}

export function fetchAnalysisContext(protocolId: string, selection?: AnalysisSelection) {
  return getData<AnalysisContext>({
    ...createAnalysisContextRequest(protocolId, selection),
    metadata: { showError: false },
  })
}

export function createAnalysisAIDraft(payload: AnalysisAIDraftRequest) {
  return getData<AnalysisAIRequest>({ url: "/analyses/aira-drafts", method: "POST", data: payload, metadata: { showError: false } })
}

export function createAnalysisAIComputeDraft(payload: AnalysisAIComputeDraftRequest) {
  return getData<AnalysisAIRequest>({ url: "/analyses/aira-compute-drafts", method: "POST", data: payload, metadata: { showError: false } })
}

export function createAnalysisAIInterpretation(runId: string, payload: AnalysisAIInterpretationRequest) {
  return getData<AnalysisAIRequest>({ url: `/analyses/${runId}/aira-interpretations`, method: "POST", data: payload, metadata: { showError: false } })
}

export function fetchAnalysisAIRequest(id: string) {
  return getData<AnalysisAIRequest>({ url: `/analysis-ai-requests/${id}`, metadata: { showError: false } })
}

export function fetchAnalysisAIDrafts(protocolId: string) {
  return getData<{ items: AnalysisAIRequest[] }>({ url: `/protocols/${protocolId}/analysis-ai-drafts`, metadata: { showError: false } })
}

export function fetchAnalysisAIComputeDrafts(protocolId: string) {
  return getData<{ items: AnalysisAIRequest[] }>({ url: `/protocols/${protocolId}/analysis-ai-compute-drafts`, metadata: { showError: false } })
}

export function fetchAnalysisAIInterpretations(runId: string) {
  return getData<{ items: AnalysisAIRequest[] }>({ url: `/analyses/${runId}/aira-interpretations`, metadata: { showError: false } })
}

export function previewAnalysis(payload: AnalysisPreviewRequest) {
  return getData<AnalysisPreview>({ url: "/analyses/preview", method: "POST", data: payload })
}

export function createAnalysis(payload: {
  preview_id: string
  preview_digest: string
  client_idempotency_key: string
}) {
  return getData<AnalysisRun>({ url: "/analyses", method: "POST", data: payload })
}

export function fetchAnalysis(analysisId: string) {
  return getData<AnalysisRun>({ url: `/analyses/${analysisId}` })
}

export function downloadAnalysis(analysisId: string) {
  return getData<AnalysisRun>({ url: `/analyses/${analysisId}/download` })
}

export function fetchProjectAnalyses(projectId: string) {
  return getData<{ items: AnalysisRun[] }>({ url: `/projects/${projectId}/analyses` })
}

export function cancelAnalysis(analysisId: string) {
  return getData<AnalysisRun>({ url: `/analyses/${analysisId}/cancel`, method: "POST" })
}

export function createAnalysisPipeline(payload: { run_id: string, title: string }) {
  return getData<AnalysisPipeline>({ url: "/analysis-pipelines", method: "POST", data: payload })
}

export function fetchProjectAnalysisPipelines(projectId: string) {
  return getData<{ items: AnalysisPipeline[] }>({ url: `/projects/${projectId}/analysis-pipelines` })
}

export function createAnalysisPipelineRevision(
  pipelineId: string,
  payload: { recipe: AnalysisRecipe | AnalysisComputeRecipe, expected_revision: number, source_selection?: AnalysisSelection },
) {
  return getData<AnalysisPipelineRevision>({
    url: `/analysis-pipelines/${pipelineId}/revisions`,
    method: "POST",
    data: payload,
  })
}

export function fetchAnalysisPipeline(pipelineId: string) {
  return getData<AnalysisPipeline>({ url: `/analysis-pipelines/${pipelineId}` })
}
