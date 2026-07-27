import type { APIResponse, FullConfig } from "@playwright/test"
import { mkdir, writeFile } from "node:fs/promises"
import { request } from "@playwright/test"

const API_URL = process.env.E2E_API_URL || "http://127.0.0.1:4100"
const DEV_PASSWORD = "AiralogyDev123!"

interface QuickstartFixture {
  accounts: Array<{ key: string, email: string, password: string }>
  lab: { id: string, uid: string }
  project: { id: string, uid: string, lab_uid: string }
  schema_governance: {
    protocol_id: string
    protocol_uid: string
    source_version: string
    target_version: string
    record_id: string
    record_version: number
  }
}

async function requiredJson<T>(response: APIResponse, label: string): Promise<T> {
  if (!response.ok())
    throw new Error(`${label} failed (${response.status()}): ${await response.text()}`)
  return response.json() as Promise<T>
}

export default async function globalSetup(_: FullConfig) {
  const api = await request.newContext({ baseURL: API_URL })
  try {
    const quickstart = await requiredJson<QuickstartFixture>(
      await api.post("/dev/fixtures/quickstart"),
      "quickstart fixture",
    )
    const owner = quickstart.accounts.find(account => account.key === "owner")
    if (!owner)
      throw new Error("Quickstart fixture did not return an owner account")
    const login = await requiredJson<{ token: string }>(
      await api.post("/signin_by_email", {
        data: { email: owner.email, password: DEV_PASSWORD },
      }),
      "owner login",
    )
    const headers = { "Auth-Token": login.token }
    const definitions = await requiredJson<{ items: Array<{ id: string, protocol_uid: string }> }>(
      await api.get(`/labs/${quickstart.lab.id}/resource-library/definition-versions`, { headers }),
      "resource definition lookup",
    )
    const plasmidDefinition = definitions.items.find(
      item => item.protocol_uid === "plasmid_resource_definition_en",
    )
    if (!plasmidDefinition)
      throw new Error("Plasmid resource definition was not loaded by the quickstart fixture")

    const resourceType = await requiredJson<{ id: string }>(
      await api.post(`/labs/${quickstart.lab.id}/resource-library/types`, {
        headers,
        data: {
          protocol_version_id: plasmidDefinition.id,
          code: "e2e_plasmid",
          name: "E2E Plasmid",
          description: "Playwright-managed resource type",
          capabilities: {
            inventory: true,
            lots: true,
            containers: true,
            expiry: true,
          },
          booking_policy: "none",
        },
      }),
      "resource type registration",
    )
    const labResource = await requiredJson<{ id: string }>(
      await api.post(`/labs/${quickstart.lab.id}/resource-library/resources`, {
        headers,
        data: {
          resource_type_id: resourceType.id,
          name: "E2E Plasmid pUC19",
          code: "E2E-PLASMID-001",
          visibility: "lab",
          data: {
            construct_name: "pUC19",
            aliases: null,
            backbone: "pUC",
            sequence: null,
            sequence_file: null,
            resistance_markers: ["Ampicillin"],
            host_species: "Escherichia coli",
            copy_number: "high",
            external_source: null,
            features: [],
          },
        },
      }),
      "visible resource creation",
    )
    const restrictedResource = await requiredJson<{ id: string }>(
      await api.post(`/labs/${quickstart.lab.id}/resource-library/resources`, {
        headers,
        data: {
          resource_type_id: resourceType.id,
          name: "E2E Restricted Plasmid",
          code: "E2E-RESTRICTED-001",
          visibility: "restricted",
          data: {
            construct_name: "Restricted",
            aliases: null,
            backbone: null,
            sequence: null,
            sequence_file: null,
            resistance_markers: null,
            host_species: null,
            copy_number: null,
            external_source: null,
            features: [],
          },
        },
      }),
      "restricted resource creation",
    )
    const container = await requiredJson<{ id: string }>(
      await api.post(`/labs/${quickstart.lab.id}/resource-library/resources/${labResource.id}/containers`, {
        headers,
        data: { code: "E2E-TUBE-001", unit: "mL", data: {} },
      }),
      "container creation",
    )
    await requiredJson(
      await api.post(`/labs/${quickstart.lab.id}/resource-library/inventory/operations/receipt`, {
        headers,
        data: {
          container_id: container.id,
          quantity: "10",
          unit: "mL",
          reason: "E2E opening balance",
          idempotency_key: "e2e-opening-balance",
        },
      }),
      "opening inventory receipt",
    )

    await mkdir("tests/e2e/.state", { recursive: true })
    await writeFile(
      "tests/e2e/.state/fixtures.json",
      JSON.stringify({
        ...quickstart,
        resourceType,
        labResource,
        restrictedResource,
        container,
      }, null, 2),
      "utf8",
    )
  }
  finally {
    await api.dispose()
  }
}
