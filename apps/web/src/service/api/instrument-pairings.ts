import { request } from "../request"

export interface InstrumentPairing {
  id: string
  gateway_id: string
  lab_id: string
  gateway_name: string
  state: "pending" | "claimed" | "confirmed" | "cancelled" | "expired" | "stale" | "superseded"
  client_name: string | null
  fingerprint: string | null
  expires_at: string
}

export interface PairingDraft {
  gateway_id: string
  expected_revision: number
  reason: string
}

async function call<T>(path: string, data?: unknown, params?: Record<string, string>) {
  const result = await request<T>({ url: `/instrument-pairings${path}`, method: data ? "POST" : "GET", data, params })
  if (result.error)
    throw result.error
  if (!result.data)
    throw new Error("No pairing response")
  return result.data
}

export const fetchPairings = (gatewayId: string) => call<{ items: InstrumentPairing[] }>("", undefined, { gateway_id: gatewayId })
export const previewPairing = (data: PairingDraft) => call<{ preview_digest: string }>("/preview", data)
export const createPairing = (data: PairingDraft & { preview_digest: string }) => call<{ pairing: InstrumentPairing, code: string }>("", data)
export const previewPairingConfirmation = (id: string) => call<{ pairing: InstrumentPairing, preview_digest: string }>(`/${id}/preview`, {})
export const confirmPairing = (id: string, previewDigest: string) => call<{ pairing: InstrumentPairing }>(`/${id}/confirm`, { preview_digest: previewDigest })
export const cancelPairing = (id: string) => call<InstrumentPairing>(`/${id}/cancel`, {})
