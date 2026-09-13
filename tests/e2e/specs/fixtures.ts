import type { Page } from "@playwright/test"
import { readFile } from "node:fs/promises"

export interface E2EFixtures {
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
  resourceType: { id: string }
  analysis: { protocol_id: string, protocol_uid: string }
  workflow_compute: { pipeline_id: string, pipeline_title: string, environment_id: string, environment_revision_id: string, environment_name: string, protocol_id: string, protocol_version_id: string }
  workflow_files: { protocol_id: string, protocol_uid: string, protocol_version_id: string, record_id: string, record_version: number, file_ref: string, field: string }
  labResource: { id: string }
  restrictedResource: { id: string }
  container: { id: string }
}

export async function loadFixtures(): Promise<E2EFixtures> {
  return JSON.parse(
    await readFile("tests/e2e/.state/fixtures.json", "utf8"),
  ) as E2EFixtures
}

export async function selectVisibleOption(page: Page, label: string | RegExp) {
  const option = page.locator(".n-base-select-option").filter({ hasText: label })
  await option.last().click()
}

export function instrumentWorkspaceUrl(labUid: string, gatewayId: string, resourceId: string, step: "connect" | "prepare" | "install" | "use", tool = "reuse") {
  const query = new URLSearchParams({ instrument_gateway: gatewayId, instrument_step: step, instrument_tool: tool })
  if (resourceId)
    query.set("instrument_resource", resourceId)
  return `/labs/${labUid}/resources/gateways?${query}`
}
