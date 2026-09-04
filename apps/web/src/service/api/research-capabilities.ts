import { request } from "../request"

export type ResearchCapabilityKind = "protocol" | "tool" | "human" | "resource" | "instrument" | "service" | "compute"

export interface ResearchCapabilityDescriptor {
  key: string
  version: string
  kind: ResearchCapabilityKind
  name: string
  description: string
  source_type: string
  source_id: string
  source_revision_id: string
  executor_types: string[]
  risk: string
  input_schema: Record<string, any>
  output_schema: Record<string, any>
  available: boolean
  unavailable_reason: string
  metadata: Record<string, any>
}

export interface ResearchCapabilityCatalog {
  project_id: string
  lab_id: string
  protocols: ResearchCapabilityDescriptor[]
  tools: ResearchCapabilityDescriptor[]
  human_work: ResearchCapabilityDescriptor[]
  resources: ResearchCapabilityDescriptor[]
  instruments: ResearchCapabilityDescriptor[]
  services: ResearchCapabilityDescriptor[]
  compute: ResearchCapabilityDescriptor[]
}

export async function fetchResearchCapabilities(projectId: string) {
  const { data, error } = await request<ResearchCapabilityCatalog>({
    url: "/research-capabilities",
    params: { project_id: projectId },
    metadata: { showError: false },
  })
  if (error)
    throw error
  if (!data)
    throw new Error("Research Capability Registry returned no data")
  return data
}
