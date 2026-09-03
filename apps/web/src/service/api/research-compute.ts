import { request } from "../request"

export interface ComputeResourceLimits {
  cpu_millis: number
  memory_mb: number
  gpu_count: number
  timeout_seconds: number
  max_output_bytes: number
}

export interface ResearchComputeEnvironment {
  key: string
  version: string
  kind: "compute"
  name: string
  description: string
  source_type: "research_compute_environment_revision"
  source_id: string
  source_revision_id: string
  executor_types: ["compute_runner"]
  risk: "low" | "medium" | "high"
  input_schema: Record<string, unknown>
  output_schema: Record<string, unknown>
  available: boolean
  unavailable_reason: string
  metadata: {
    lab_id: string
    environment_key: string
    environment_revision: number
    runner_protocol_version: "airalogy.compute-runner.v1"
    image_ref: string
    runtime_version: string
    allowed_languages: Array<"python" | "r">
    resource_limits: ComputeResourceLimits
    network_policy: "none" | "egress_allowlist"
    allowed_egress_hosts: string[]
    software_manifest: Record<string, unknown>
    estimated_cost_per_hour?: string | null
    currency?: string | null
    change_reason: string
  }
  position?: number
}

export interface ComputeEnvironmentDraft {
  lab_id: string
  environment_key: string
  name: string
  description: string
  runner_protocol_version: "airalogy.compute-runner.v1"
  image_ref: string
  runtime_version: string
  allowed_languages: Array<"python" | "r">
  resource_limits: ComputeResourceLimits
  network_policy: "none" | "egress_allowlist"
  allowed_egress_hosts: string[]
  input_schema: Record<string, unknown>
  result_schema: Record<string, unknown>
  software_manifest: Record<string, unknown>
  estimated_cost_per_hour?: string | null
  currency?: string | null
  risk: "low" | "medium" | "high"
  enabled: boolean
  reason: string
}

export interface ComputeEnvironmentRevisionDraft extends ComputeEnvironmentDraft {
  expected_revision: number
}

export interface ResearchComputePreview {
  preview_digest: string
  command: Record<string, unknown>
  effects: string[]
}

async function requiredData<T>(config: Parameters<typeof request<T>>[0], message: string) {
  const { data, error } = await request<T>(config)
  if (error)
    throw error
  if (!data)
    throw new Error(message)
  return data
}

export function fetchResearchComputeEnvironments(labId: string) {
  return requiredData<{ items: ResearchComputeEnvironment[] }>({
    url: "/research-compute-environments",
    params: { lab_id: labId },
  }, "Research Compute Environment catalog returned no data")
}

export function previewResearchComputeEnvironment(payload: ComputeEnvironmentDraft) {
  return requiredData<ResearchComputePreview>({
    url: "/research-compute-environments/preview",
    method: "post",
    data: payload,
  }, "Research Compute Environment preview returned no data")
}

export function createResearchComputeEnvironment(
  payload: ComputeEnvironmentDraft & { preview_digest: string },
) {
  return requiredData<ResearchComputeEnvironment>({
    url: "/research-compute-environments",
    method: "post",
    data: payload,
  }, "Research Compute Environment creation returned no data")
}

export function previewResearchComputeEnvironmentRevision(
  environmentId: string,
  payload: ComputeEnvironmentRevisionDraft,
) {
  return requiredData<ResearchComputePreview>({
    url: `/research-compute-environments/${environmentId}/revisions/preview`,
    method: "post",
    data: payload,
  }, "Research Compute Environment revision preview returned no data")
}

export function createResearchComputeEnvironmentRevision(
  environmentId: string,
  payload: ComputeEnvironmentRevisionDraft & { preview_digest: string },
) {
  return requiredData<ResearchComputeEnvironment>({
    url: `/research-compute-environments/${environmentId}/revisions`,
    method: "post",
    data: payload,
  }, "Research Compute Environment revision returned no data")
}
