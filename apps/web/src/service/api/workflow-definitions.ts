import type { ResearchComputeRequirement } from "./research-tasks"
import type { WorkflowAnalysisOutput, WorkflowAnalysisPublication, WorkflowComputeFileOutput, WorkflowComputeOutput } from "./workflow-analysis-methods"
import { request } from "../request"

export interface WorkflowProtocolNode {
  node_id: string
  kind: "protocol"
  protocol_id: string
  protocol_version_id: string
  title: string
  position: { x: number, y: number }
  initial_values: Record<string, unknown>
}

interface WorkflowAnalysisNodeBase {
  node_id: string
  kind: "analysis"
  method_publication_id: string
  record_sources: Array<{ source_node_id: string, cardinality: "one" }>
  input_policy: "all_declared"
  title: string
  position: { x: number, y: number }
}

export interface WorkflowBuiltinAnalysisNode extends WorkflowAnalysisNodeBase {
  analysis_kind?: "builtin"
  analysis_outputs: WorkflowAnalysisOutput[]
  compute_outputs?: never
  compute_file_outputs?: never
}
export interface WorkflowComputeAnalysisNode extends WorkflowAnalysisNodeBase {
  analysis_kind: "compute"
  compute_outputs: WorkflowComputeOutput[]
  compute_file_outputs?: WorkflowComputeFileOutput[]
  analysis_outputs?: never
}
export type WorkflowAnalysisNode = WorkflowBuiltinAnalysisNode | WorkflowComputeAnalysisNode

export type WorkflowNode = WorkflowProtocolNode | WorkflowAnalysisNode

export type WorkflowScalarType = "string" | "number" | "integer" | "boolean"
export interface WorkflowScalarField {
  path: string[]
  title: string
  value_type: WorkflowScalarType
  unit: string | null
  nullable: boolean
  bindable_target?: boolean
}
export interface WorkflowFileField {
  path: string[]
  title: string
  value_type: "file"
  unit: null
  nullable: boolean
  bindable_target?: boolean
  file_extensions: string[] | null
}
export type WorkflowField = WorkflowScalarField | WorkflowFileField

export interface WorkflowCondition {
  path: string[]
  value_type: WorkflowScalarType
  operator: "eq" | "ne" | "gt" | "gte" | "lt" | "lte"
  value: string | number | boolean
  unit: string | null
}

export interface WorkflowScalarBinding {
  binding_id: string
  source_node_id: string
  source_path: string[]
  target_node_id: string
  target_path: string[]
  value_type: WorkflowScalarType | "file"
  unit: string | null
  cardinality: "one"
}

export interface WorkflowControlEdge {
  edge_id: string
  source_node_id: string
  target_node_id: string
  condition: WorkflowCondition | null
}

export interface WorkflowGraph {
  schema_version: 1 | 2 | 3 | 4
  nodes: WorkflowNode[]
  edges: WorkflowControlEdge[]
  bindings: WorkflowScalarBinding[]
}

export interface WorkflowCapabilities {
  read: boolean
  write: boolean
  run: boolean
}

export interface WorkflowProtocolPin {
  node_id: string
  kind?: "protocol"
  protocol_id: string
  protocol_version_id: string
  version: string
  name: string
}

export interface WorkflowAnalysisPin {
  node_id: string
  kind: "analysis"
  method_publication_id: string
  protocol_id: string
  protocol_version_id: string
  engine_version: string
  name: string
  content_digest: string
}
export type WorkflowPin = WorkflowProtocolPin | WorkflowAnalysisPin

export interface WorkflowRevision {
  id: string
  revision: number
  title: string
  description: string
  graph: WorkflowGraph
  pins?: WorkflowPin[]
  created_at?: string
}

export interface WorkflowDefinition {
  id: string
  project_id: string
  title: string
  description: string
  revision: number
  current_revision: WorkflowRevision | null
}

export interface WorkflowDefinitionDetail extends WorkflowDefinition {
  revisions: WorkflowRevision[]
  runs: Array<{
    task_id: string
    run_id: string
    workflow_revision_id: string
    status: string
    actions?: Array<{ id: string, node_id: string, title: string, status: string, skip_reason?: string | null }>
  }>
}

export interface WorkflowTaskContext {
  id: string
  title: string
  revision: number
  run_id: string
  protocols: Array<{ id: string, version_id: string, version: string }>
  compute?: ResearchComputeRequirement[]
  owner_user_id?: string
}

export interface WorkflowContext {
  protocols: Array<{ id: string, name: string, versions: Array<{ id: string, version: string, fields?: WorkflowField[] }> }>
  tasks: WorkflowTaskContext[]
  analysis_methods?: WorkflowAnalysisPublication[]
  analysis_method_warnings?: Array<{ id: string, code: "method_unavailable" }>
  compute_approvers?: Array<{ id: string, name: string, username?: string }>
  capabilities: WorkflowCapabilities
}

export interface WorkflowSaveRequest {
  project_id: string
  definition_id?: string
  expected_revision?: number
  title: string
  description: string
  graph: WorkflowGraph
}

export interface WorkflowSavePreview extends WorkflowSaveRequest {
  preview_digest: string
  pins: WorkflowPin[]
  warnings: string[]
}

export interface WorkflowRunRequest {
  workflow_revision_id: string
  task_id: string
  expected_task_revision: number
  compute_approvers?: Record<string, string>
}

export interface WorkflowRunPreview extends WorkflowRunRequest {
  preview_digest: string
  nodes: WorkflowNode[]
  edges: WorkflowControlEdge[]
  bindings: WorkflowScalarBinding[]
  pins: WorkflowPin[]
  warnings?: string[]
  compute_governance?: Record<string, { approver_user_id: string, max_cost: string | null, budget_currency: string | null, deadline_at: string | null }>
  owner: { id: string, name?: string, username?: string }
  environment: {
    executor_bindings?: Array<{ capability_key: string, executor_type: string, resolved_executor_ref?: { type: string, id: string }, approval_policy?: string }>
    operational_limits?: { budget_limit?: string | null, budget_currency?: string | null, deadline_at?: string | null }
    [key: string]: unknown
  }
}

async function getData<T>(config: Parameters<typeof request<T>>[0]): Promise<T> {
  const { data, error } = await request<T>({ ...config, metadata: { showError: false } })
  if (error)
    throw error
  if (data === null)
    throw new Error("Workflow service returned no data")
  return data
}

export async function fetchWorkflowDefinitions(projectId: string) {
  return getData<{ items: WorkflowDefinition[], capabilities: WorkflowCapabilities }>({ url: "/workflow-definitions", method: "GET", params: { project_id: projectId } })
}

export async function fetchWorkflowContext(projectId: string) {
  return getData<WorkflowContext>({ url: "/workflow-definitions/context", method: "GET", params: { project_id: projectId } })
}

export async function fetchWorkflowDefinition(id: string) {
  return getData<WorkflowDefinitionDetail>({ url: `/workflow-definitions/${id}`, method: "GET" })
}

export async function previewWorkflowDefinition(data: WorkflowSaveRequest) {
  return getData<WorkflowSavePreview>({ url: "/workflow-definitions/preview", method: "POST", data })
}

export async function confirmWorkflowDefinition(data: WorkflowSaveRequest & { preview_digest: string, idempotency_key: string }) {
  return getData<WorkflowDefinition & { confirmed_revision_id: string }>({ url: "/workflow-definitions/confirm", method: "POST", data })
}

export async function previewWorkflowRun(id: string, data: WorkflowRunRequest) {
  return getData<WorkflowRunPreview>({ url: `/workflow-definitions/${id}/runs/preview`, method: "POST", data })
}

export async function confirmWorkflowRun(id: string, data: WorkflowRunRequest & { preview_digest: string, idempotency_key: string }) {
  return getData<{ task_id: string, run_id: string, workflow_revision_id: string, actions: unknown[] }>({ url: `/workflow-definitions/${id}/runs/confirm`, method: "POST", data })
}
