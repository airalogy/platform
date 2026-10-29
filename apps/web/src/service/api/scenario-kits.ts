import type { AnalysisRecipe } from "./analysis"
import type { ResourceItem } from "./resources"
import { request } from "../request"

export interface KitAsset {
  component_id: string
  protocol_id: string
  protocol_version_id: string
  version: string
  source_kit_version: string
  resource_type_id: string
  available: boolean
  changed: boolean
  name?: string
  uid?: string
  latest_version?: string
  can_record?: boolean
  can_read_records?: boolean
}
export interface ScenarioKit {
  id: string
  version: string
  digest: string
  name: Record<string, string>
  description: Record<string, string>
  modules: Array<{ id: string, version: string }>
  source: string
  license: string
  external_services: string[]
  unavailable_reasons: string[]
  installation: { version: string, enabled: boolean, revision: number } | null
  application: { id: string, version: string, enabled: boolean, revision: number, assets: KitAsset[] } | null
}
export interface KitDirectory {
  kits: ScenarioKit[]
  can_manage: boolean
  can_register_samples: boolean
  lab_name: string
  project_name: string | null
}
export interface KitOperation {
  kit_id: string
  version: string
  action: "enable" | "disable" | "apply" | "deactivate"
  strategy: "keep" | "new_copy"
}
export interface KitPreview {
  preview_token: string
  expires_at: string
  destination: { lab: string, project: string | null }
  create_components: string[]
  assets: KitAsset[]
  blockers: string[]
  manifest: ScenarioKit
}
export function kitUrl(labId: string, projectId?: string) {
  return `/labs/${labId}${projectId ? `/projects/${projectId}` : ""}/scenario-kits`
}
async function data<T>(options: Parameters<typeof request<T>>[0]): Promise<T> {
  const result = await request<T>(options)
  if (result.error)
    throw result.error
  if (!result.data)
    throw new Error("No response returned")
  return result.data
}
export const fetchKitDirectory = (labId: string, projectId?: string) => data<KitDirectory>({ url: kitUrl(labId, projectId) })
export const previewKit = (labId: string, projectId: string | undefined, operation: KitOperation) => data<KitPreview>({ url: `${kitUrl(labId, projectId)}/preview`, method: "POST", data: operation })
export const confirmKit = (labId: string, projectId: string | undefined, operation: KitOperation, token: string, requestId: string) => data<{ event_id: string, replayed: boolean }>({ url: `${kitUrl(labId, projectId)}/confirm`, method: "POST", data: { ...operation, preview_token: token, request_id: requestId }, timeout: 120000 })
export const registerKitSample = (labId: string, projectId: string, values: { kit_id: string, name: string, code: string, category: string, source?: string, storage?: string }) => data<ResourceItem>({ url: `${kitUrl(labId, projectId)}/samples`, method: "POST", data: values })
export const fetchSampleTemplate = (labId: string, projectId: string, values: { kit_id: string, protocol_id: string, sample_ids: string[] }) => data<{ csv: string, protocol_version: string, row_count: number }>({ url: `${kitUrl(labId, projectId)}/sample-template`, method: "POST", data: values })
export const fetchKitRecipe = (labId: string, projectId: string) => data<{ recipe: AnalysisRecipe }>({ url: `${kitUrl(labId, projectId)}/analysis-recipe` })
export const fetchKitHistory = (labId: string, projectId?: string) => data<{ items: Array<{ id: string, operation: string, kit_id: string, version: string, created_at: string }> }>({ url: `${kitUrl(labId, projectId)}/history` })

export function downloadKitFile(contents: string, name: string, type = "text/csv;charset=utf-8") {
  const url = URL.createObjectURL(new Blob([type.startsWith("text/csv") ? "\uFEFF" : "", contents], { type }))
  const link = document.createElement("a")
  link.href = url
  link.download = name
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
