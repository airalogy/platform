import type { AnalysisCounts, AnalysisPipeline, AnalysisPreview, AnalysisRun, AnalysisSelection, AnalysisSource } from "./analysis"
import type { ComputeResourceLimits, ResearchComputeEnvironment } from "./research-compute"
import type { ComputeOutputDraft, ResearchComputeJob } from "./research-compute-jobs"
import { request } from "../request"

export interface AnalysisComputeRecipe {
  kind: "compute"
  environment_revision_id: string
  language: "python" | "r"
  source_code: string
  parameters: Record<string, unknown>
  output_files: ComputeOutputDraft[]
}

export interface AnalysisComputeEnvironment {
  id: string
  revision_id: string
  revision: number
  name: string
  image_ref: string
  allowed_languages: Array<"python" | "r">
  resource_limits: ComputeResourceLimits
  network_policy: "none" | "egress_allowlist"
  allowed_egress_hosts: string[]
  input_schema: Record<string, unknown>
  result_schema: Record<string, unknown>
  estimated_cost: string | null
  currency: string | null
  authorized_runner_count: number
  ready_runner_count: number
}

export interface AnalysisComputeContext {
  environments: AnalysisComputeEnvironment[]
  approvers: Array<{ id: string, name: string }>
  source: { record_count: number, source_digest: string, filename: "records.json" }
  max_source_bytes: number
}

export interface AnalysisComputePreviewRequest {
  protocol_id: string
  selection: AnalysisSelection
  question: string
  recipe: AnalysisComputeRecipe
  approver_user_id: string
  max_cost?: string
  budget_currency?: string
  deadline_at?: string
  pipeline_revision_id?: string
  rerun_of_id?: string
  ai_draft_id?: string
}

export interface AnalysisComputeContract {
  environment: ResearchComputeEnvironment
  source: { language: "python" | "r", code: string, sha256: string, bytes: number }
  input: { record_count: number, bytes: number, sha256: string, filename: string }
  parameters: Record<string, unknown>
  output_files: ComputeOutputDraft[]
  approver: { id: string, name: string }
  cost: { estimated_cost: string | null, currency: string | null, max_cost: string | null, budget_currency: string | null }
  deadline_at?: string | null
  authorized_runner_count: number
  ready_runner_count: number
  approval_required: true
}

export interface AnalysisComputePreview extends Omit<AnalysisPreview, "recipe" | "summary"> {
  recipe: AnalysisComputeRecipe
  summary: {
    compute: AnalysisComputeContract
    counts: AnalysisCounts
    sources: AnalysisSource[]
    source_digest: string
    protocol_name: string
    project_name: string
    visibility: "private"
  }
}

export interface AnalysisComputeApproval {
  state: "pending" | "approved" | "rejected" | "cancelled"
  revision: number
  approver_user_id: string
  can_approve: boolean
  contract_digest: string
  reason?: string
  decided_at?: string | null
}

export interface AnalysisComputeDetail {
  contract: AnalysisComputeContract
  job: Omit<ResearchComputeJob, "output_manifest"> & { output_manifest: AnalysisComputeOutput[] }
  approval: AnalysisComputeApproval
  events: Array<{ id: string, kind: string, created_at: string, details?: Record<string, unknown> }>
  run: AnalysisRun
}

export interface AnalysisComputeOutput {
  id: string
  mount_name: string
  asset_name: string
  media_type: string
  max_bytes: number
  byte_size: number | null
  checksum_sha256: string | null
  required: boolean
  status: string
}

export interface AnalysisComputeResult {
  computed_result: Record<string, unknown>
  outputs: AnalysisComputeOutput[]
  usage: Record<string, number>
  actual_cost: string | null
  currency: string | null
}

export interface AnalysisComputeSeed {
  recipe: AnalysisComputeRecipe
  pipeline?: AnalysisPipeline
  pipelineRevisionId?: string
  rerunOfId?: string
}

async function requiredData<T>(options: Parameters<typeof request<T>>[0]) {
  const { data, error } = await request<T>({ ...options, metadata: { showError: false } })
  if (error)
    throw error
  if (data === null)
    throw new Error("Analysis Compute service returned no data")
  return data
}

export function fetchAnalysisComputeContext(protocolId: string, selection: AnalysisSelection) {
  return requiredData<AnalysisComputeContext>({ url: `/protocols/${protocolId}/analysis-compute-context`, method: "POST", data: selection })
}

export function previewAnalysisCompute(payload: AnalysisComputePreviewRequest) {
  return requiredData<AnalysisComputePreview>({ url: "/analyses/compute/preview", method: "POST", data: payload })
}

export function confirmAnalysisCompute(payload: { preview_id: string, preview_digest: string, client_idempotency_key: string }) {
  return requiredData<AnalysisRun>({ url: "/analyses/compute", method: "POST", data: payload })
}

export function fetchAnalysisCompute(id: string, approvalOnly = false) {
  return requiredData<AnalysisComputeDetail>({ url: `/analyses/${id}/${approvalOnly ? "compute-approval" : "compute"}` })
}

export function decideAnalysisCompute(id: string, payload: { decision: "approved" | "rejected", expected_revision: number, contract_digest: string, reason: string }) {
  return requiredData<AnalysisComputeDetail>({ url: `/analyses/${id}/compute-approval`, method: "POST", data: payload })
}

export function cancelAnalysisCompute(id: string, payload: { expected_revision: number, reason: string, contract_digest: string }) {
  return requiredData<{ analysis_id: string, job_id: string, status: ResearchComputeJob["status"], revision: number }>({ url: `/analyses/${id}/compute-cancel`, method: "POST", data: payload })
}

export async function downloadAnalysisComputeOutput(id: string, outputId: string) {
  const { data, error } = await request<Blob, "blob">({ url: `/analyses/${id}/compute/outputs/${outputId}`, responseType: "blob", metadata: { showError: false } })
  if (error)
    throw error
  if (data === null)
    throw new Error("Analysis output download returned no data")
  return data
}

export function fetchAnalysisComputeApprovals(projectId: string) {
  return requiredData<{ items: Array<{ analysis_id: string, question: string, requested_at: string, approval_state: string, approver_user_id: string }> }>({ url: "/analysis-compute-approvals", params: { project_id: projectId } })
}
