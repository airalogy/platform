import { expect, test } from "@playwright/test"
import { loadFixtures } from "./fixtures"

test("description toggle appears only when the three-line preview overflows", async ({ page }) => {
  const fixtures = await loadFixtures()
  await page.goto(
    `/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}/protocols/drug_response_ic50_en/records`,
  )

  const description = page.getByTestId("global-description-text")
  const toggle = page.getByTestId("global-description-toggle")
  await expect(description).toBeVisible()

  const defaultOverflow = await description.evaluate(
    element => element.scrollHeight - element.clientHeight,
  )
  expect(defaultOverflow).toBeLessThanOrEqual(1)
  await expect(toggle).toHaveCount(0)

  await page.setViewportSize({ width: 600, height: 800 })
  await expect(toggle).toBeVisible()
  const collapsedHeight = await description.evaluate(element => element.clientHeight)

  await toggle.click({ force: true })
  await expect
    .poll(() => description.evaluate(element => element.clientHeight))
    .toBeGreaterThan(collapsedHeight)
})
