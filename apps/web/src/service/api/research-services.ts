import { request } from "../request"

export interface ResearchServiceProvider {
  id: string
  lab_id: string
  provider_key: string
  name: string
  description: string
  contact_name: string
  contact_email: string
  website_url: string
  enabled: boolean
  revision: number
  archived_at?: string | null
  offerings: ResearchServiceOffering[]
}

export interface ResearchServiceOffering {
  key: string
  version: string
  kind: "service"
  name: string
  description: string
  source_type: "research_service_offering_revision"
  source_id: string
  source_revision_id: string
  executor_types: ["external_service"]
  risk: "low" | "medium" | "high"
  input_schema: Record<string, any>
  output_schema: Record<string, any>
  available: boolean
  unavailable_reason: string
  metadata: {
    lab_id: string
    provider: Omit<ResearchServiceProvider, "offerings">
    offering_id: string
    offering_key: string
    offering_enabled: boolean
    offering_revision: number
    quote_required: boolean
    base_price?: string | null
    currency?: string | null
    sla_hours?: number | null
    sample_requirements: Record<string, any>
    logistics_policy: Record<string, any>
    terms: string
    change_reason: string
  }
}

export interface ServiceProviderDraft {
  lab_id: string
  provider_key: string
  name: string
  description: string
  contact_name: string
  contact_email: string
  website_url: string
  enabled: boolean
  reason: string
}

export interface ServiceProviderUpdateDraft extends Omit<ServiceProviderDraft, "lab_id" | "provider_key"> {
  expected_revision: number
}

export interface ServiceOfferingDraft {
  provider_id: string
  offering_key: string
  name: string
  description: string
  service_version: string
  input_schema: Record<string, any>
  result_schema: Record<string, any>
  quote_required: boolean
  base_price?: string | null
  currency?: string | null
  sla_hours?: number | null
  sample_requirements: Record<string, any>
  logistics_policy: Record<string, any>
  terms: string
  risk: "low" | "medium" | "high"
  enabled: boolean
  reason: string
}

export interface ServiceOfferingRevisionDraft extends ServiceOfferingDraft {
  expected_revision: number
}

export interface ResearchServicePreview {
  preview_digest: string
  command: Record<string, any>
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

export function fetchResearchServices(labId: string) {
  return requiredData<{ providers: ResearchServiceProvider[] }>({
    url: "/research-services",
    params: { lab_id: labId },
  }, "Research service catalog returned no data")
}

export function previewServiceProvider(payload: ServiceProviderDraft) {
  return requiredData<ResearchServicePreview>({
    url: "/research-services/providers/preview",
    method: "post",
    data: payload,
  }, "Service provider preview returned no data")
}

export function createServiceProvider(payload: ServiceProviderDraft & { preview_digest: string }) {
  return requiredData<Omit<ResearchServiceProvider, "offerings">>({
    url: "/research-services/providers",
    method: "post",
    data: payload,
  }, "Service provider creation returned no data")
}

export function previewServiceProviderUpdate(providerId: string, payload: ServiceProviderUpdateDraft) {
  return requiredData<ResearchServicePreview>({
    url: `/research-services/providers/${providerId}/preview`,
    method: "post",
    data: payload,
  }, "Service provider preview returned no data")
}

export function updateServiceProvider(
  providerId: string,
  payload: ServiceProviderUpdateDraft & { preview_digest: string },
) {
  return requiredData<Omit<ResearchServiceProvider, "offerings">>({
    url: `/research-services/providers/${providerId}`,
    method: "put",
    data: payload,
  }, "Service provider update returned no data")
}

export function previewServiceOffering(payload: ServiceOfferingDraft) {
  return requiredData<ResearchServicePreview>({
    url: "/research-services/offerings/preview",
    method: "post",
    data: payload,
  }, "Service offering preview returned no data")
}

export function createServiceOffering(payload: ServiceOfferingDraft & { preview_digest: string }) {
  return requiredData<ResearchServiceOffering>({
    url: "/research-services/offerings",
    method: "post",
    data: payload,
  }, "Service offering creation returned no data")
}

export function previewServiceOfferingRevision(
  offeringId: string,
  payload: ServiceOfferingRevisionDraft,
) {
  return requiredData<ResearchServicePreview>({
    url: `/research-services/offerings/${offeringId}/revisions/preview`,
    method: "post",
    data: payload,
  }, "Service offering preview returned no data")
}

export function createServiceOfferingRevision(
  offeringId: string,
  payload: ServiceOfferingRevisionDraft & { preview_digest: string },
) {
  return requiredData<ResearchServiceOffering>({
    url: `/research-services/offerings/${offeringId}/revisions`,
    method: "post",
    data: payload,
  }, "Service offering revision returned no data")
}
