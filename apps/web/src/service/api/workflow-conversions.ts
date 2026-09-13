import type { WorkflowDefinition, WorkflowGraph, WorkflowPin } from "./workflow-definitions"
import { request } from "../request"

export interface LegacyWorkflowEntry {
  id: string
  title: string
  updated_at: string
  path_status: string
  can_convert: boolean
}
export interface WorkflowConversionEdge {
  source_protocol_index: number
  target_protocol_index: number
}
export interface WorkflowConversionContext {
  source: { id: string, project_id: string, title: string, digest: string, path_status: string }
  nodes: Array<{ protocol_index: number, node_id: string, name: string, protocol_id: string | null, original_reference: string, suggested_version_id: string | null, versions: Array<{ id: string, version: string }> }>
  edges: Array<{ edge_id: string, text: string, source_protocol_index: number | null, target_protocol_index: number | null, supported: boolean }>
  logic_text: string
  warnings: Array<{ code: string, message: string }>
  blockers: Array<{ code: string, protocol_index: number, message: string }>
  omitted_fields: string[]
}
export interface WorkflowConversionRequest {
  project_id: string
  source_digest: string
  title: string
  description: string
  nodes: Array<{ protocol_index: number, protocol_id: string, protocol_version_id: string }>
  edges: WorkflowConversionEdge[]
  acknowledge_versions: boolean
  acknowledge_structure_only: boolean
  acknowledge_logic_omission: boolean
}
export interface WorkflowConversionPreview {
  preview_digest: string
  source: WorkflowConversionContext["source"]
  graph: WorkflowGraph
  pins: WorkflowPin[]
  title: string
  description: string
  warnings: WorkflowConversionContext["warnings"]
  omitted_fields?: string[]
}
export type WorkflowConversionResult = WorkflowDefinition & { confirmed_revision_id: string, conversion_receipt_id: string }

async function getData<T>(config: Parameters<typeof request<T>>[0]): Promise<T> {
  const { data, error } = await request<T>({ ...config, metadata: { showError: false } })
  if (error)
    throw error
  if (!data)
    throw new Error("Workflow conversion returned no data")
  return data
}
export function fetchLegacyWorkflows(projectId: string) {
  return getData<{ items: LegacyWorkflowEntry[], capabilities: { read: boolean, write: boolean } }>({ url: "/workflow-conversions", params: { project_id: projectId } })
}
export function fetchWorkflowConversionContext(id: string) {
  return getData<WorkflowConversionContext>({ url: `/workflow-conversions/${id}/context` })
}
export function previewWorkflowConversion(id: string, data: WorkflowConversionRequest) {
  return getData<WorkflowConversionPreview>({ url: `/workflow-conversions/${id}/preview`, method: "POST", data })
}
export function confirmWorkflowConversion(id: string, data: WorkflowConversionRequest & { preview_digest: string, idempotency_key: string }) {
  return getData<WorkflowConversionResult>({ url: `/workflow-conversions/${id}/confirm`, method: "POST", data })
}
