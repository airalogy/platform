import { request } from "../request"

export interface InstrumentSafetyContract {
  required_interlocks: string[]
  operator_presence_required: boolean
  emergency_stop_required: boolean
}

export interface InstrumentGateway {
  id: string
  lab_id: string
  name: string
  description: string
  token_hint: string
  enabled: boolean
  revision: number
  last_seen_at: string | null
  revoked_at: string | null
}

export interface InstrumentCommand {
  id: string
  gateway_id: string
  lab_id: string
  resource_id: string
  resource_revision_id: string
  resource_revision: number
  command_key: string
  command_version: string
  name: string
  description: string
  input_schema: Record<string, unknown>
  output_schema: Record<string, unknown>
  risk: "read_only" | "low" | "medium" | "high"
  device_confirmation_required: boolean
  safety_contract: InstrumentSafetyContract
  timeout_seconds: number
  enabled: boolean
  revision: number
  archived_at: string | null
}

export interface InstrumentPreview {
  preview_digest: string
  command: Record<string, unknown>
  effects: string[]
}

async function getData<T>(options: Parameters<typeof request<T>>[0]): Promise<T> {
  const { data, error } = await request<T>(options)
  if (error)
    throw error
  if (data === null)
    throw new Error("Instrument Gateway returned no data")
  return data
}

const gatewayUrl = "/research-instrument-gateways"

export function fetchInstrumentGateways(labId: string) {
  return getData<{ items: InstrumentGateway[] }>({
    url: gatewayUrl,
    params: { lab_id: labId },
  })
}

export function previewInstrumentGateway(payload: {
  lab_id: string
  name: string
  description: string
  enabled: boolean
  reason: string
}) {
  return getData<InstrumentPreview>({
    url: `${gatewayUrl}/preview`,
    method: "POST",
    data: payload,
  })
}

export function createInstrumentGateway(
  payload: {
    lab_id: string
    name: string
    description: string
    enabled: boolean
    reason: string
    preview_digest: string
  },
) {
  return getData<{ gateway: InstrumentGateway, credential: string }>({
    url: gatewayUrl,
    method: "POST",
    data: payload,
  })
}

export function previewInstrumentGatewayUpdate(
  gatewayId: string,
  payload: {
    expected_revision: number
    name: string
    description: string
    enabled: boolean
    reason: string
  },
) {
  return getData<InstrumentPreview>({
    url: `${gatewayUrl}/${gatewayId}/preview`,
    method: "POST",
    data: payload,
  })
}

export function updateInstrumentGateway(
  gatewayId: string,
  payload: {
    expected_revision: number
    name: string
    description: string
    enabled: boolean
    reason: string
    preview_digest: string
  },
) {
  return getData<InstrumentGateway>({
    url: `${gatewayUrl}/${gatewayId}`,
    method: "PUT",
    data: payload,
  })
}

export function previewGatewayCredentialRotation(
  gatewayId: string,
  payload: { expected_revision: number, reason: string },
) {
  return getData<InstrumentPreview>({
    url: `${gatewayUrl}/${gatewayId}/rotate/preview`,
    method: "POST",
    data: payload,
  })
}

export function rotateGatewayCredential(
  gatewayId: string,
  payload: {
    expected_revision: number
    reason: string
    preview_digest: string
  },
) {
  return getData<{ gateway: InstrumentGateway, credential: string }>({
    url: `${gatewayUrl}/${gatewayId}/rotate`,
    method: "POST",
    data: payload,
  })
}

export function fetchInstrumentCommands(gatewayId: string) {
  return getData<{ items: InstrumentCommand[] }>({
    url: `${gatewayUrl}/${gatewayId}/commands`,
  })
}

export interface InstrumentCommandPayload {
  gateway_id: string
  resource_id: string
  command_key: string
  command_version: string
  name: string
  description: string
  input_schema: Record<string, unknown>
  output_schema: Record<string, unknown>
  risk: "read_only" | "low" | "medium" | "high"
  device_confirmation_required: boolean
  safety_contract: InstrumentSafetyContract
  timeout_seconds: number
  enabled: boolean
  reason: string
}

export function previewInstrumentCommand(payload: InstrumentCommandPayload) {
  return getData<InstrumentPreview>({
    url: `${gatewayUrl}/commands/preview`,
    method: "POST",
    data: payload,
  })
}

export function createInstrumentCommand(
  payload: InstrumentCommandPayload & { preview_digest: string },
) {
  return getData<InstrumentCommand>({
    url: `${gatewayUrl}/commands`,
    method: "POST",
    data: payload,
  })
}

export interface InstrumentCommandUpdatePayload {
  expected_revision: number
  name: string
  description: string
  input_schema: Record<string, unknown>
  output_schema: Record<string, unknown>
  risk: "read_only" | "low" | "medium" | "high"
  device_confirmation_required: boolean
  safety_contract: InstrumentSafetyContract
  timeout_seconds: number
  enabled: boolean
  reason: string
}

export function previewInstrumentCommandUpdate(
  commandId: string,
  payload: InstrumentCommandUpdatePayload,
) {
  return getData<InstrumentPreview>({
    url: `${gatewayUrl}/commands/${commandId}/preview`,
    method: "POST",
    data: payload,
  })
}

export function updateInstrumentCommand(
  commandId: string,
  payload: InstrumentCommandUpdatePayload & { preview_digest: string },
) {
  return getData<InstrumentCommand>({
    url: `${gatewayUrl}/commands/${commandId}`,
    method: "PUT",
    data: payload,
  })
}
