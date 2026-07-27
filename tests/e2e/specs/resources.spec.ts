import { expect, test } from "@playwright/test"
import { loadFixtures, selectVisibleOption } from "./fixtures"

test("owner can inspect resources and inventory audit", async ({ page }) => {
  const fixtures = await loadFixtures()
  await page.goto(`/labs/${fixtures.lab.uid}/resources/resources`)
  await expect(page.getByTestId("resource-library")).toBeVisible()
  await expect(page.getByText("E2E Plasmid pUC19")).toBeVisible()

  await page.getByText("E2E Plasmid pUC19").click()
  const detail = page.getByTestId("resource-detail")
  await expect(detail).toBeVisible()
  await expect(detail.getByText("E2E-PLASMID-001")).toBeVisible()
  await expect(detail.getByText(/E2E-TUBE-001/)).toBeVisible()
  await expect(detail.getByText(/10 mL/)).toBeVisible()
})

test("resource creation rejects invalid AIMD data and accepts valid data", async ({ page }) => {
  const fixtures = await loadFixtures()
  const code = `E2E-UI-${Date.now()}`
  await page.goto(`/labs/${fixtures.lab.uid}/resources/resources`)
  await page.getByTestId("resource-add-button").last().click()
  await page.getByTestId("resource-type-select").click()
  await selectVisibleOption(page, "E2E Plasmid")
  await page.getByTestId("resource-name-input").locator("input").fill("E2E UI Plasmid")
  await page.getByTestId("resource-code-input").locator("input").fill(code)
  await page.getByTestId("resource-data-input").locator("textarea").fill("{}")
  const rejected = page.waitForResponse(response =>
    response.url().endsWith("/resource-library/resources")
    && response.status() === 422,
  )
  await page.getByTestId("resource-save-button").click()
  await rejected
  await expect(page.getByTestId("resource-save-button")).toBeVisible()

  await page.getByTestId("resource-data-input").locator("textarea").fill(JSON.stringify({
    construct_name: "UI-created",
    aliases: null,
    backbone: null,
    sequence: null,
    sequence_file: null,
    resistance_markers: null,
    host_species: null,
    copy_number: null,
    external_source: null,
    features: [],
  }))
  const created = page.waitForResponse(response =>
    response.url().endsWith("/resource-library/resources")
    && response.ok(),
  )
  await page.getByTestId("resource-save-button").click()
  await created
  await expect(page.getByText("E2E UI Plasmid")).toBeVisible()
  await expect(page.getByText(code)).toBeVisible()
})

test("inventory rejects over-consumption and commits a valid operation", async ({ page }) => {
  const fixtures = await loadFixtures()
  await page.goto(`/labs/${fixtures.lab.uid}/resources/inventory`)
  await page.getByTestId("inventory-record-button").click()
  await page.getByTestId("inventory-operation-select").click()
  await selectVisibleOption(page, /consumption/i)
  await page.getByTestId("inventory-resource-select").click()
  await selectVisibleOption(page, /E2E Plasmid pUC19/)
  await page.getByTestId("inventory-container-select").click()
  await selectVisibleOption(page, /E2E-TUBE-001/)
  await page.getByTestId("inventory-quantity-input").locator("input").fill("100")
  await page.getByTestId("inventory-reason-input").locator("textarea").fill("Over-consumption guard")

  const rejected = page.waitForResponse(response =>
    response.url().includes("/inventory/operations/consumption")
    && response.status() === 409,
  )
  await page.getByTestId("inventory-save-button").click()
  await rejected
  await expect(page.getByTestId("inventory-save-button")).toBeVisible()

  await page.getByTestId("inventory-quantity-input").locator("input").fill("2")
  await page.getByTestId("inventory-reason-input").locator("textarea").fill("E2E valid consumption")
  const committed = page.waitForResponse(response =>
    response.url().includes("/inventory/operations/consumption")
    && response.ok(),
  )
  await page.getByTestId("inventory-save-button").click()
  await committed
  await expect(page.getByText("E2E valid consumption")).toBeVisible()
  await expect(page.getByText(/10 → 8/)).toBeVisible()
})
