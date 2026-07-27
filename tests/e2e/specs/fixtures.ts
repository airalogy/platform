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
