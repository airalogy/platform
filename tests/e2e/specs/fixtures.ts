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
  project_analysis: { inputs: Array<{ slot_id: string, protocol_id: string, protocol_uid: string, key_field: string, value_field: string, unit: string }> }
  workflow_compute: { pipeline_id: string, pipeline_title: string, environment_id: string, environment_revision_id: string, environment_name: string, protocol_id: string, protocol_version_id: string }
  workflow_compute_attachments: { pipeline_id: string, pipeline_title: string, environment_id: string, environment_revision_id: string, environment_name: string, protocol_id: string, protocol_version_id: string }
  workflow_files: { protocol_id: string, protocol_uid: string, protocol_version_id: string, record_id: string, record_version: number, file_ref: string, field: string }
  workflow_assets: { protocol_id: string, protocol_uid: string, protocol_version_id: string, data_asset_id: string, data_asset_version_id: string, version: number, latest_version: number, name: string, value: number, sha256: string, byte_size: number, filename: string, source_path: string[], unit: string, scalar_field: string, file_field: string }
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
  // Closed menus remain visible during their leave transition. They can contain
  // the same label as the newly opened menu, but must never receive the click.
  const option = page.locator(".n-base-select-menu:visible:not(.fade-in-scale-up-transition-leave-active) .n-base-select-option:visible").filter({ hasText: label })
  // Long lists are virtualized. Type in the actual focused search field rather
  // than waiting for an offscreen option that has not been rendered at all.
  // Non-filterable menus and regex selections retain their visible-option path.
  if (typeof label === "string" && await option.count() === 0) {
    const search = page.locator("input.n-base-selection-input:focus")
    if (await search.count() === 1 && await search.isVisible() && await search.isEditable())
      await search.fill(label)
  }
  await option.last().click({ timeout: 15_000 })
}

export function instrumentWorkspaceUrl(labUid: string, gatewayId: string, resourceId: string, step: "connect" | "prepare" | "install" | "use", tool = "reuse") {
  const query = new URLSearchParams({ instrument_gateway: gatewayId, instrument_step: step, instrument_tool: tool })
  if (resourceId)
    query.set("instrument_resource", resourceId)
  return `/labs/${labUid}/resources/gateways?${query}`
}
