import type { ResearchComputeEnvironment } from "./research-compute"
import { request } from "../request"

export interface ResearchComputeRunner {
  id: string
  lab_id: string
  name: string
  description: string
  runner_protocol_version: "airalogy.compute-runner.v1"
  max_concurrent_jobs: number
  token_hint: string
  enabled: boolean
  revision: number
  last_report: {
    protocol_version?: string
    runner_version?: string
    executor_backend?: "docker" | "podman" | "kubernetes" | "slurm"
    active_jobs?: number
    available_slots?: number
    security?: {
      non_root?: boolean
      read_only_root_filesystem?: boolean
      network_isolation?: boolean
      no_host_mounts?: boolean
    }
  }
  last_seen_at: string | null
  revoked_at: string | null
}

export interface ResearchComputeRunnerBinding {
  id: string
  runner_id: string
  lab_id: string
  compute_environment_id: string
  compute_environment_revision_id: string
  environment: ResearchComputeEnvironment
  created_at: string | null
  archived_at: string | null
}

export interface ComputeRunnerPreview {
  preview_digest: string
  command: Record<string, unknown>
  effects: string[]
}

export interface ComputeRunnerDraft {
  lab_id: string
  name: string
  description: string
  runner_protocol_version: "airalogy.compute-runner.v1"
  max_concurrent_jobs: number
  enabled: boolean
  reason: string
}

async function requiredData<T>(config: Parameters<typeof request<T>>[0], message: string) {
  const { data, error } = await request<T>(config)
  if (error)
    throw error
  if (!data)
    throw new Error(message)
  return data
}

const runnerUrl = "/research-compute-runners"

export function fetchResearchComputeRunners(labId: string) {
  return requiredData<{ items: ResearchComputeRunner[] }>({
    url: runnerUrl,
    params: { lab_id: labId },
  }, "Research Compute Runner catalog returned no data")
}

export function previewResearchComputeRunner(payload: ComputeRunnerDraft) {
  return requiredData<ComputeRunnerPreview>({
    url: `${runnerUrl}/preview`,
    method: "post",
    data: payload,
  }, "Research Compute Runner preview returned no data")
}

export function createResearchComputeRunner(
  payload: ComputeRunnerDraft & { preview_digest: string },
) {
  return requiredData<{ runner: ResearchComputeRunner, credential: string }>({
    url: runnerUrl,
    method: "post",
    data: payload,
  }, "Research Compute Runner creation returned no data")
}

export function previewResearchComputeRunnerUpdate(
  runnerId: string,
  payload: Omit<ComputeRunnerDraft, "lab_id"> & { expected_revision: number },
) {
  return requiredData<ComputeRunnerPreview>({
    url: `${runnerUrl}/items/${runnerId}/preview`,
    method: "post",
    data: payload,
  }, "Research Compute Runner update preview returned no data")
}

export function updateResearchComputeRunner(
  runnerId: string,
  payload: Omit<ComputeRunnerDraft, "lab_id"> & {
    expected_revision: number
    preview_digest: string
  },
) {
  return requiredData<ResearchComputeRunner>({
    url: `${runnerUrl}/items/${runnerId}`,
    method: "put",
    data: payload,
  }, "Research Compute Runner update returned no data")
}

export function previewResearchComputeRunnerRotation(
  runnerId: string,
  payload: { expected_revision: number, reason: string },
) {
  return requiredData<ComputeRunnerPreview>({
    url: `${runnerUrl}/items/${runnerId}/rotate/preview`,
    method: "post",
    data: payload,
  }, "Research Compute Runner rotation preview returned no data")
}

export function rotateResearchComputeRunnerCredential(
  runnerId: string,
  payload: { expected_revision: number, reason: string, preview_digest: string },
) {
  return requiredData<{ runner: ResearchComputeRunner, credential: string }>({
    url: `${runnerUrl}/items/${runnerId}/rotate`,
    method: "post",
    data: payload,
  }, "Research Compute Runner credential rotation returned no data")
}

export function fetchResearchComputeRunnerBindings(runnerId: string) {
  return requiredData<{ items: ResearchComputeRunnerBinding[] }>({
    url: `${runnerUrl}/items/${runnerId}/bindings`,
  }, "Research Compute Runner bindings returned no data")
}

export function previewResearchComputeRunnerBinding(payload: {
  runner_id: string
  compute_environment_revision_id: string
  expected_runner_revision: number
  reason: string
}) {
  return requiredData<ComputeRunnerPreview>({
    url: `${runnerUrl}/bindings/preview`,
    method: "post",
    data: payload,
  }, "Research Compute Runner binding preview returned no data")
}

export function createResearchComputeRunnerBinding(payload: {
  runner_id: string
  compute_environment_revision_id: string
  expected_runner_revision: number
  reason: string
  preview_digest: string
}) {
  return requiredData<ResearchComputeRunnerBinding>({
    url: `${runnerUrl}/bindings`,
    method: "post",
    data: payload,
  }, "Research Compute Runner binding creation returned no data")
}

export function previewResearchComputeRunnerBindingArchive(
  bindingId: string,
  payload: { expected_runner_revision: number, reason: string },
) {
  return requiredData<ComputeRunnerPreview>({
    url: `${runnerUrl}/bindings/${bindingId}/archive/preview`,
    method: "post",
    data: payload,
  }, "Research Compute Runner binding removal preview returned no data")
}

export function archiveResearchComputeRunnerBinding(
  bindingId: string,
  payload: { expected_runner_revision: number, reason: string, preview_digest: string },
) {
  return requiredData<ResearchComputeRunnerBinding>({
    url: `${runnerUrl}/bindings/${bindingId}/archive`,
    method: "post",
    data: payload,
  }, "Research Compute Runner binding removal returned no data")
}
