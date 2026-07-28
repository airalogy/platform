import { expect, test } from "@playwright/test"
import { loadFixtures } from "./fixtures"

test("record diary heatmap finishes rendering", async ({ page }) => {
  const fixtures = await loadFixtures()

  await page.goto(`/labs/${fixtures.lab.uid}/records`)

  const chart = page.getByTestId("record-diary-heatmap-chart")
  await expect(chart).toBeVisible()
  await expect(chart.locator("svg.ch-container")).toBeVisible()
  await expect(page.getByTestId("record-diary-heatmap-loading")).toHaveCount(0)
})
