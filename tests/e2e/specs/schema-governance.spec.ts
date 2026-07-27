import { expect, test } from "@playwright/test"
import { loadFixtures, selectVisibleOption } from "./fixtures"

test("an old Record stays on its Schema until explicit projection and migration", async ({ page }) => {
  const fixtures = await loadFixtures()
  const governance = fixtures.schema_governance
  await page.goto(
    `/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}/protocols/${governance.protocol_uid}`
    + `/v${governance.source_version}/record/${governance.record_id}/v${governance.record_version}`,
  )

  await expect(page.getByTestId("record-schema-governance")).toBeVisible()
  await expect(page.getByTestId("record-source-version")).toContainText(governance.source_version)
  await page.getByTestId("record-target-version").click()
  await selectVisibleOption(page, `v${governance.target_version}`)
  await expect(page.getByTestId("record-project-version")).toBeEnabled()
  await expect(page.getByTestId("record-migrate-version")).toBeEnabled()

  const projected = page.waitForResponse(response =>
    response.url().endsWith("/projections")
    && response.ok(),
  )
  await page.getByTestId("record-project-version").click()
  await projected
  await expect(page.getByTestId("record-projection-data")).toContainText("Legacy E2E sample")
  await expect(page.getByTestId("record-projection-data")).toContainText("\"name\"")
  await page.getByTestId("record-governance-close").click()

  const previewed = page.waitForResponse(response =>
    response.url().endsWith("/migration-preview")
    && response.ok(),
  )
  await page.getByTestId("record-migrate-version").click()
  await previewed
  await page.getByTestId("record-migration-data-toggle").click()
  await expect(page.getByTestId("record-migration-data")).toContainText("\"name\"")
  await page.getByTestId("record-migration-reason").locator("textarea").fill("E2E confirmed migration")

  const migrated = page.waitForResponse(response =>
    response.url().endsWith("/migrations")
    && response.ok(),
  )
  await page.getByTestId("record-migration-confirm").click()
  await migrated
  await expect(page).toHaveURL(
    new RegExp(`/v${governance.target_version}/record/${governance.record_id}/v2`),
  )
  await expect(
    page.getByTestId("record-source-version").filter({ hasText: governance.target_version }),
  ).toBeVisible()
})
