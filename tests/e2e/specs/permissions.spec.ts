import { expect, test } from "@playwright/test"
import { loadFixtures } from "./fixtures"

test("viewer sees Lab resources but no restricted data or mutation controls", async ({ page }) => {
  const fixtures = await loadFixtures()
  await page.goto(`/labs/${fixtures.lab.uid}/resources/resources`)
  await expect(page.getByText("E2E Plasmid pUC19")).toBeVisible()
  await expect(page.getByText("E2E Restricted Plasmid")).toHaveCount(0)
  await expect(page.getByTestId("resource-add-button")).toHaveCount(0)
  await expect(page.getByTestId("resource-import-button")).toHaveCount(0)

  await page.goto(`/labs/${fixtures.lab.uid}/resources/inventory`)
  await expect(page.getByTestId("inventory-record-button")).toHaveCount(0)

  await page.goto(`/labs/${fixtures.lab.uid}/resources/types`)
  await expect(page.getByTestId("resource-register-type-button")).toHaveCount(0)
})
