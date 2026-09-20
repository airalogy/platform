import type { AnalysisRecipe, AnalysisScalar, AnalysisStatistics } from "./analysis"
import type { AnalysisComputeRecipe } from "./analysis-compute"
import type { ProjectAnalysisRecipe } from "./project-analysis"
import type { ResearchComputeEnvironment } from "./research-compute"
import type { WorkflowField, WorkflowScalarField } from "./workflow-definitions"
import { request } from "../request"

export interface WorkflowAnalysisOutput {
  output_id: string
  field: string
  statistic: keyof AnalysisStatistics
  group: Record<string, AnalysisScalar | null>
}

export interface WorkflowProjectOutput extends WorkflowAnalysisOutput {
  source: { kind: "local", slot_id: string } | { kind: "join" }
}

export interface WorkflowProjectContract {
  schema_version: 1
  slots: Array<{
    slot_id: string
    label: string
    protocol_id: string
    versions: Array<{ id: string, version: string, schema_digest: string, json_schema: Record<string, unknown>, fields: Record<string, unknown> }>
  }>
}

export interface WorkflowComputeOutput extends Omit<WorkflowScalarField, "title" | "bindable_target"> {
  output_id: string
}
export interface WorkflowComputeFileOutput {
  output_id: string
  mount_name: string
}
export interface WorkflowComputeFileField {
  mount_name: string
  title: string
  media_type: string
  max_bytes: number
  required: boolean
  value_type: "file"
  nullable: boolean
  unit: null
  file_extensions: string[] | null
}

export interface WorkflowPublishedComputeContract {
  environment: ResearchComputeEnvironment
  input_schema_contract: { json_schema: Record<string, unknown>, fields: WorkflowAnalysisPublication["input_fields"] }
  input_schema_digest: string
  result_schema: Record<string, unknown>
}

export interface WorkflowAnalysisPublication {
  id: string
  project_id: string
  protocol_id: string | null
  protocol_version_id: string | null
  title: string
  engine_version: "airalogy.analysis.v1" | "airalogy.compute.analysis.v1" | "airalogy.project-analysis.v1"
  recipe: AnalysisRecipe | AnalysisComputeRecipe | ProjectAnalysisRecipe
  project_contract?: WorkflowProjectContract
  /** Server-derived field catalogs; not part of the immutable publication contract or digest. */
  project_input_fields?: Record<string, WorkflowAnalysisPublication["input_fields"]>
  compute_contract?: WorkflowPublishedComputeContract
  input_fields: Array<{ key: string, title: string, type: string | string[], unit: string | null, enum?: Array<AnalysisScalar | null> }>
  source_schema_digest: string
  digest: string
  created_by_user_id: string
  created_at: string
}

export interface WorkflowAnalysisPublicationRequest {
  project_id: string
  pipeline_revision_id: string
  protocol_version_id: string | null
  project_inputs?: Array<{ slot_id: string, protocol_id: string, protocol_version_ids: string[] }>
  title: string
  compute_result_schema?: Record<string, unknown>
}

export interface WorkflowAnalysisPublicationPreview {
  publication: Omit<WorkflowAnalysisPublication, "id" | "created_at" | "created_by_user_id">
  source: { pipeline_id: string, pipeline_revision_id: string, revision: number, method_digest: string }
  audience: "project_research_members_with_protocol_access" | "project_research_members_with_all_source_protocol_access"
  destination?: { project_id: string, project_name: string }
  expires_at?: string
  excluded_fields: string[]
  preview_digest: string
  preview_token?: string
}

async function getData<T>(config: Parameters<typeof request<T>>[0]): Promise<T> {
  const { data, error } = await request<T>({ ...config, metadata: { showError: false } })
  if (error)
    throw error
  if (data === null)
    throw new Error("Workflow analysis service returned no data")
  return data
}

export function fetchWorkflowAnalysisMethods(projectId: string) {
  return getData<{ items: WorkflowAnalysisPublication[], unavailable?: Array<{ id: string, code: "method_unavailable" }> }>({ url: "/workflow-analysis-methods", params: { project_id: projectId } })
}

export function previewWorkflowAnalysisPublication(payload: WorkflowAnalysisPublicationRequest) {
  return getData<WorkflowAnalysisPublicationPreview>({ url: "/workflow-analysis-methods/preview", method: "POST", data: payload })
}

export function confirmWorkflowAnalysisPublication(payload: WorkflowAnalysisPublicationRequest & { preview_digest: string, preview_token?: string, idempotency_key: string }) {
  return getData<WorkflowAnalysisPublication>({ url: "/workflow-analysis-methods/confirm", method: "POST", data: payload })
}

export function previewWorkflowAnalysisOutputs(publicationId: string, outputs: WorkflowAnalysisOutput[] | WorkflowComputeOutput[] | WorkflowProjectOutput[], fileOutputs?: WorkflowComputeFileOutput[]) {
  return getData<{ fields: WorkflowField[] }>({ url: `/workflow-analysis-methods/${publicationId}/outputs/preview`, method: "POST", data: { outputs, ...(fileOutputs?.length ? { file_outputs: fileOutputs } : {}) } })
}

export function fetchWorkflowComputeOutputCatalog(publicationId: string) {
  return getData<{ kind: "compute", fields: WorkflowScalarField[], file_fields?: WorkflowComputeFileField[] }>({ url: `/workflow-analysis-methods/${publicationId}/outputs/catalog` })
}
