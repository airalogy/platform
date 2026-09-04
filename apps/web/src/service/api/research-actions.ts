import type { ResearchAction, ResearchInstrumentControlSession } from "./research-tasks"
import type { EquipmentBooking } from "./resources"
import { request } from "../request"

export interface ResearchToolDefinition {
  key: string
  version: string
  name: string
  description: string
  input_schema: Record<string, any>
  output_schema: Record<string, any>
  risk: string
  executor_type: string
  available: boolean
  unavailable_reason: string
}

export interface ResearchActionDestination {
  lab: { id: string, uid: string, name: string }
  project: { id: string, uid: string, name: string }
  task: { id: string, title: string }
  run: { id: string, number: number }
}

export interface ToolActionDraft {
  tool_key: string
  arguments: Record<string, unknown>
  title: string
  description: string
  idempotency_key: string
}

export interface WaitActionDraft {
  title: string
  description: string
  event_key: string
  expected_event_type: string
  payload_schema: Record<string, unknown>
  due_at?: string | null
  idempotency_key: string
}

export interface WaitEventSignalDraft {
  expected_revision: number
  event_type: string
  payload: Record<string, unknown>
}

export interface ResearchInstrumentCommandOption {
  id: string
  gateway_id: string
  resource_id: string
  resource_revision_id: string
  resource_revision: number
  command_key: string
  command_version: string
  name: string
  description: string
  input_schema: Record<string, any>
  output_schema: Record<string, any>
  risk: "read_only" | "low" | "medium" | "high"
  device_confirmation_required: boolean
  safety_contract: {
    required_interlocks: string[]
    operator_presence_required: boolean
    emergency_stop_required: boolean
  }
  timeout_seconds: number
  revision: number
  gateway: { id: string, name: string }
  resource: { id: string, name: string, code: string }
  bookings: EquipmentBooking[]
}

export interface InstrumentActionDraft {
  command_id: string
  equipment_booking_id: string
  arguments: Record<string, unknown>
  title: string
  description: string
  idempotency_key: string
}

export interface InstrumentStopDraft {
  expected_revision: number
  reason: string
}

export interface InstrumentControlCondition {
  path: string
  operator: "eq" | "ne" | "lt" | "lte" | "gt" | "gte" | "in" | "exists"
  value: unknown
}

export interface InstrumentControlStepDraft {
  key: string
  command_id: string
  arguments: Record<string, unknown>
  transition: {
    condition: InstrumentControlCondition | null
    on_true: string
    on_false?: string | null
  }
}

export interface InstrumentControlDraft {
  mode: "bounded_sequence" | "feedback_loop"
  title: string
  description: string
  equipment_booking_id: string
  entry_step_key: string
  steps: InstrumentControlStepDraft[]
  max_steps: number
  max_duration_seconds: number
  idempotency_key: string
}

export interface AiraInstrumentControlDraftRequest {
  instruction: string
  mode: InstrumentControlDraft["mode"]
  equipment_booking_id: string
  max_step_templates: number
  max_steps: number
  max_duration_seconds: number
}

export interface AiraInstrumentControlDraftResponse {
  draft: InstrumentControlDraft
  rationale: string
  assumptions: string[]
  warnings: string[]
  model: string
  source_digest: string
  boundary: string
}

export interface InstrumentControlDecisionDraft {
  expected_revision: number
  reason: string
}

export interface DigitalActionPreview<T> {
  preview_digest: string
  command: T
  destination: ResearchActionDestination
  effects?: string[]
  effect?: string
  tool?: ResearchToolDefinition
  instrument?: ResearchInstrumentCommandOption & { booking: EquipmentBooking }
  instrument_control?: ResearchInstrumentControlSession & {
    gateway?: { id: string, name: string }
    resource?: { id: string, name: string, code: string }
    booking?: EquipmentBooking
    step_count?: number
    highest_risk?: ResearchInstrumentCommandOption["risk"]
  }
  pending_step?: Record<string, any>
  action?: { id: string, title: string }
}

async function getData<T>(options: Parameters<typeof request<T>>[0]): Promise<T> {
  const { data, error } = await request<T>(options)
  if (error)
    throw error
  if (data === null)
    throw new Error("Research Action service returned no data")
  return data
}

export function fetchResearchTools(taskId?: string) {
  return getData<{ tools: ResearchToolDefinition[] }>({
    url: "/research-tools",
    params: { task_id: taskId },
    metadata: { showError: false },
  })
}

export function previewToolAction(taskId: string, payload: ToolActionDraft) {
  return getData<DigitalActionPreview<ToolActionDraft>>({
    url: `/research-tasks/${taskId}/tool-actions/preview`,
    method: "POST",
    data: payload,
  })
}

export function createToolAction(
  taskId: string,
  payload: ToolActionDraft & { preview_digest: string },
) {
  return getData<ResearchAction>({
    url: `/research-tasks/${taskId}/tool-actions`,
    method: "POST",
    data: payload,
  })
}

export function previewWaitAction(taskId: string, payload: WaitActionDraft) {
  return getData<DigitalActionPreview<WaitActionDraft>>({
    url: `/research-tasks/${taskId}/wait-actions/preview`,
    method: "POST",
    data: payload,
  })
}

export function createWaitAction(
  taskId: string,
  payload: WaitActionDraft & { preview_digest: string },
) {
  return getData<ResearchAction>({
    url: `/research-tasks/${taskId}/wait-actions`,
    method: "POST",
    data: payload,
  })
}

export function previewWaitEventSignal(waitEventId: string, payload: WaitEventSignalDraft) {
  return getData<DigitalActionPreview<WaitEventSignalDraft>>({
    url: `/research-wait-events/${waitEventId}/signal/preview`,
    method: "POST",
    data: payload,
  })
}

export function signalWaitEvent(
  waitEventId: string,
  payload: WaitEventSignalDraft & { preview_digest: string },
) {
  return getData<ResearchAction>({
    url: `/research-wait-events/${waitEventId}/signal`,
    method: "POST",
    data: payload,
  })
}

export function fetchResearchInstrumentCommands(taskId: string) {
  return getData<{ items: ResearchInstrumentCommandOption[] }>({
    url: "/research-instrument-commands",
    params: { task_id: taskId },
    metadata: { showError: false },
  })
}

export function previewInstrumentAction(taskId: string, payload: InstrumentActionDraft) {
  return getData<DigitalActionPreview<InstrumentActionDraft>>({
    url: `/research-tasks/${taskId}/instrument-actions/preview`,
    method: "POST",
    data: payload,
  })
}

export function createInstrumentAction(
  taskId: string,
  payload: InstrumentActionDraft & { preview_digest: string },
) {
  return getData<ResearchAction>({
    url: `/research-tasks/${taskId}/instrument-actions`,
    method: "POST",
    data: payload,
  })
}

export function previewInstrumentControlSession(
  taskId: string,
  payload: InstrumentControlDraft,
) {
  return getData<DigitalActionPreview<InstrumentControlDraft>>({
    url: `/research-tasks/${taskId}/instrument-control-sessions/preview`,
    method: "POST",
    data: payload,
  })
}

export function draftInstrumentControlWithAira(
  taskId: string,
  payload: AiraInstrumentControlDraftRequest,
) {
  return getData<AiraInstrumentControlDraftResponse>({
    url: `/research-tasks/${taskId}/instrument-control-sessions/draft-with-aira`,
    method: "POST",
    data: payload,
  })
}

export function createInstrumentControlSession(
  taskId: string,
  payload: InstrumentControlDraft & { preview_digest: string },
) {
  return getData<ResearchInstrumentControlSession>({
    url: `/research-tasks/${taskId}/instrument-control-sessions`,
    method: "POST",
    data: payload,
  })
}

export function fetchInstrumentControlSession(sessionId: string) {
  return getData<ResearchInstrumentControlSession>({
    url: `/research-instrument-control-sessions/${sessionId}`,
  })
}

export function previewInstrumentControlResume(
  sessionId: string,
  payload: InstrumentControlDecisionDraft,
) {
  return getData<DigitalActionPreview<InstrumentControlDecisionDraft>>({
    url: `/research-instrument-control-sessions/${sessionId}/resume/preview`,
    method: "POST",
    data: payload,
  })
}

export function resumeInstrumentControlSession(
  sessionId: string,
  payload: InstrumentControlDecisionDraft & { preview_digest: string },
) {
  return getData<ResearchInstrumentControlSession>({
    url: `/research-instrument-control-sessions/${sessionId}/resume`,
    method: "POST",
    data: payload,
  })
}

export function previewInstrumentControlStop(
  sessionId: string,
  payload: InstrumentControlDecisionDraft,
) {
  return getData<DigitalActionPreview<InstrumentControlDecisionDraft>>({
    url: `/research-instrument-control-sessions/${sessionId}/stop/preview`,
    method: "POST",
    data: payload,
  })
}

export function stopInstrumentControlSession(
  sessionId: string,
  payload: InstrumentControlDecisionDraft & { preview_digest: string },
) {
  return getData<ResearchInstrumentControlSession>({
    url: `/research-instrument-control-sessions/${sessionId}/stop`,
    method: "POST",
    data: payload,
  })
}

export function previewInstrumentStop(jobId: string, payload: InstrumentStopDraft) {
  return getData<DigitalActionPreview<InstrumentStopDraft>>({
    url: `/research-instrument-jobs/${jobId}/stop/preview`,
    method: "POST",
    data: payload,
  })
}

export function stopInstrumentJob(
  jobId: string,
  payload: InstrumentStopDraft & { preview_digest: string },
) {
  return getData<ResearchAction>({
    url: `/research-instrument-jobs/${jobId}/stop`,
    method: "POST",
    data: payload,
  })
}
