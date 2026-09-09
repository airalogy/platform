import { request } from "../request"

export interface InstrumentRecordOption {
  record_id: string
  record_version: number
  record_number: number
  protocol_id: string
  protocol_uid: string
  protocol_name: string
  protocol_version: string
  created_at: string
}
export type InstrumentAssociation = { id: string, state: "restricted" } | (InstrumentRecordOption & {
  id: string
  state: "associated"
  sample_reference: string
})
export interface InstrumentOutput {
  id: string
  name: string
  media_type: string
  max_bytes: number
  required: boolean
  state: "awaiting_capture" | "awaiting_upload" | "registered" | "omitted" | "unavailable"
  research_file_id?: string
  data_asset_id?: string
  data_asset_version_id?: string
  sha256?: string
  byte_size?: number
  captured_at?: string
  received_at?: string
  original_units?: string[]
  conversion_rules?: string[]
  completion_reference?: string
  association: InstrumentAssociation | null
}
export interface InstrumentOutputs {
  job_id: string
  state: "awaiting_execution" | "execution_stopped" | "awaiting_files" | "delivered"
  execution_status: string
  finalized_at: string | null
  destination: { scope_type: "project", project_id: string, lab_id: string, task_id: string, visibility: "project", asset_state: "draft", record_association: "awaiting_review" }
  context: { project_id: string, project_uid: string, project_name: string, lab_id: string, lab_uid: string, lab_name: string, task_id: string }
  permissions: { associate: boolean }
  items: InstrumentOutput[]
}
export interface InstrumentAssociationDraft {
  id: string
  record_id: string
  record_version: number
  sample_reference: string
  expected_association_id: string | null
}
export interface InstrumentAssociationPreview {
  preview_digest: string
  command: InstrumentAssociationDraft & { output_id: string, data_asset_version_id: string, record_hash: string, protocol_id: string, protocol_version: string, association_revision: number }
  record: InstrumentRecordOption
  output: { name: string, research_file_id: string, data_asset_id: string, data_asset_version_id: string, sha256: string, byte_size: number }
}
export interface InstrumentPage<T> { items: T[], has_more: boolean, next_offset: number }
export type InstrumentAssociationHistory = InstrumentAssociation & { revision: number, associated_at: string }

async function call<T>(jobId: string, suffix = "", data?: unknown, params?: Record<string, unknown>) {
  const result = await request<T>({ url: `/research-instrument-jobs/${jobId}/outputs${suffix}`, method: data === undefined ? "GET" : "POST", data, params })
  if (result.error)
    throw result.error
  if (!result.data)
    throw new Error("Instrument output response is unavailable")
  return result.data
}
export const fetchInstrumentOutputs = (id: string) => call<InstrumentOutputs>(id)
export const fetchInstrumentRecordOptions = (id: string, protocolId: string, q = "", offset = 0) => call<InstrumentPage<InstrumentRecordOption>>(id, "/record-options", undefined, { protocol_id: protocolId, q, offset })
export const fetchInstrumentAssociationHistory = (id: string, outputId: string, offset = 0) => call<InstrumentPage<InstrumentAssociationHistory>>(id, `/${outputId}/associations`, undefined, { offset })
export const previewInstrumentAssociation = (id: string, outputId: string, draft: InstrumentAssociationDraft) => call<InstrumentAssociationPreview>(id, `/${outputId}/associations/preview`, draft)
export const confirmInstrumentAssociation = (id: string, outputId: string, draft: InstrumentAssociationDraft, digest: string) => call<{ id: string, state: "associated" }>(id, `/${outputId}/associations`, { ...draft, preview_digest: digest })
