import type { ResearchAction, ResearchScope } from "./research-tasks"
import { request } from "../request"

export type ResearchComputeJobStatus
  = | "awaiting_approval"
  | "queued"
  | "leased"
  | "running"
  | "cancel_requested"
  | "completed"
  | "failed"
  | "cancelled"

export interface ComputeOption {
  compute_environment_revision_id: string
  name: string
  revision: number
  allowed_languages: Array<"python" | "r">
  input_schema: Record<string, unknown>
  result_schema: Record<string, unknown>
  resource_limits: {
    cpu_millis: number
    memory_mb: number
    gpu_count: number
    timeout_seconds: number
    max_output_bytes: number
  }
  network_policy: "none" | "egress_allowlist"
  estimated_cost?: string | null
  currency?: string | null
  authorized_runner_count: number
  ready_runner_count: number
}

export interface ComputeInputDraft {
  data_asset_version_id: string
  mount_name: string
}

export interface ComputeOutputDraft {
  mount_name: string
  asset_name: string
  description: string
  kind: "file" | "table" | "image" | "model" | "archive"
  media_type: string
  max_bytes: number
  required: boolean
  data_schema: Record<string, unknown>
  metadata: Record<string, unknown>
}

export interface ComputeActionDraft {
  compute_environment_revision_id: string
  language: "python" | "r"
  source_code: string
  input_payload: Record<string, unknown>
  input_assets: ComputeInputDraft[]
  output_files: ComputeOutputDraft[]
  title: string
  description: string
  idempotency_key: string
}

export interface ComputeActionPreview {
  preview_digest: string
  command: Record<string, any>
  destination: {
    lab: ResearchScope
    project: ResearchScope
    task: { id: string, title: string }
    run: { id: string, number: number }
  }
  environment: {
    name: string
    revision: number
    image_ref: string
    risk: "low" | "medium" | "high"
  }
  source: { language: string, sha256: string, bytes: number }
  input_asset_count: number
  output_file_count: number
  authorized_runner_count: number
  ready_runner_count: number
  effects: string[]
}

export interface ResearchComputeJob {
  id: string
  action_id: string
  compute_environment_id: string
  compute_environment_revision_id: string
  compute_environment_revision: number
  runner_id?: string | null
  language: "python" | "r"
  source_code?: string
  source_sha256: string
  source_bytes: number
  input_payload: Record<string, unknown>
  environment_snapshot: {
    name?: string
    revision?: number
    image_ref?: string
    [key: string]: unknown
  }
  result_schema: Record<string, unknown>
  resource_limits: Record<string, number>
  timeout_seconds: number
  estimated_cost?: string | null
  actual_cost?: string | null
  currency?: string | null
  status: ResearchComputeJobStatus
  attempt_count: number
  result: Record<string, unknown>
  output_manifest: Array<{
    id: string
    mount_name: string
    asset_name: string
    description: string
    kind: "file" | "table" | "image" | "model" | "archive"
    media_type: string
    max_bytes: number
    required: boolean
    status: "declared" | "uploaded" | "registered"
    checksum_sha256?: string | null
    byte_size?: number | null
    research_file_id?: string | null
    data_asset_id?: string | null
    data_asset_version_id?: string | null
  }>
  usage: Record<string, number>
  error?: string | null
  cancel_reason?: string | null
  revision: number
  created_at: string
  leased_at?: string | null
  started_at?: string | null
  heartbeat_at?: string | null
  completed_at?: string | null
}

async function getData<T>(options: Parameters<typeof request<T>>[0]): Promise<T> {
  const { data, error } = await request<T>(options)
  if (error)
    throw error
  if (data === null)
    throw new Error("Research Compute service returned no data")
  return data
}

export function fetchComputeOptions(taskId: string) {
  return getData<{ items: ComputeOption[] }>({
    url: `/research-tasks/${taskId}/compute-options`,
  })
}

export function previewComputeAction(taskId: string, payload: ComputeActionDraft) {
  return getData<ComputeActionPreview>({
    url: `/research-tasks/${taskId}/compute-actions/preview`,
    method: "POST",
    data: payload,
  })
}

export function createComputeAction(
  taskId: string,
  payload: ComputeActionDraft & { preview_digest: string },
) {
  return getData<ResearchAction>({
    url: `/research-tasks/${taskId}/compute-actions`,
    method: "POST",
    data: payload,
  })
}

export function previewComputeCancellation(
  job: ResearchComputeJob,
  reason: string,
) {
  return getData<{ preview_digest: string, effects: string[] }>({
    url: `/research-compute-jobs/${job.id}/cancel/preview`,
    method: "POST",
    data: { expected_revision: job.revision, reason },
  })
}

export function cancelComputeJob(
  job: ResearchComputeJob,
  reason: string,
  previewDigest: string,
) {
  return getData<ResearchAction>({
    url: `/research-compute-jobs/${job.id}/cancel`,
    method: "POST",
    data: {
      expected_revision: job.revision,
      reason,
      preview_digest: previewDigest,
    },
  })
}
