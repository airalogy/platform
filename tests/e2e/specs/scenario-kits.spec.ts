import { Buffer } from "node:buffer"
import { expect, test } from "@playwright/test"
import { loadFixtures } from "./fixtures"

test.describe.configure({ mode: "serial" })
let sampleCode = ""

test("bundled kit connects real samples, strict CSV import and grouped analysis without AI", async ({ page }, testInfo) => {
  sampleCode = `KIT-${Date.now()}-${testInfo.retry}`
  test.setTimeout(180000)
  page.setDefaultTimeout(15000)
  const fixtures = await loadFixtures()
  const project = `/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}`
  await page.goto(`/labs/${fixtures.lab.uid}/settings`)
  const catalog = page.getByTestId("kit-catalog")
  await expect(catalog).toBeVisible()
  await catalog.getByRole("button", { name: "Preview enablement or upgrade" }).first().click()
  await page.getByRole("button", { name: "Confirm", exact: true }).last().click()
  await expect(catalog.getByText(/Saved. Receipt:/)).toBeVisible()

  await page.goto(`${project}/scenarios`)
  await page.getByRole("radio", { name: "Create a new template copy", exact: true }).check()
  await page.getByRole("button", { name: "Preview application", exact: true }).first().click()
  await page.getByRole("button", { name: "Confirm", exact: true }).last().click()
  await expect(page.getByTestId("kit-catalog").getByText(/Saved. Receipt:/)).toBeVisible()
  // A retry creates a separate Protocol copy. Reload to select that latest copy
  // instead of retaining the previously selected Protocol and its Records.
  await page.reload()
  await expect(page.getByRole("button", { name: "Register sample", exact: true })).toBeVisible()
  await page.getByRole("button", { name: "Register sample", exact: true }).click()
  await page.getByRole("textbox", { name: "Sample name", exact: true }).fill("Synthetic kit control")
  await page.getByRole("textbox", { name: "Sample code", exact: true }).fill(sampleCode)
  await page.getByRole("textbox", { name: "Category", exact: true }).fill("Synthetic reference")
  const saved = page.waitForResponse(response => response.url().endsWith("/scenario-kits/samples") && response.request().method() === "POST")
  await page.getByRole("button", { name: "Save", exact: true }).last().click()
  const sampleResponse = await saved
  expect(sampleResponse.ok()).toBeTruthy()
  const sample = await sampleResponse.json()
  await page.getByRole("checkbox", { name: sampleCode, exact: true }).check()
  const templated = page.waitForResponse(response => response.url().endsWith("/scenario-kits/sample-template"))
  const download = page.waitForEvent("download")
  await page.getByRole("button", { name: /Download results template for selected samples/ }).click()
  const template = await (await templated).json()
  expect((await download).suggestedFilename()).toBe("sample-results-v1.1.0.csv")
  expect(template.csv).toContain(sample.id)

  await page.getByRole("button", { name: "Bulk upload", exact: true }).click()
  const modal = page.locator(".n-modal:visible").last()
  await modal.locator("input[type=\"file\"]").setInputFiles({ name: "unfilled.csv", mimeType: "text/csv", buffer: Buffer.from(template.csv) })
  await modal.getByRole("button", { name: "Validate file", exact: true }).click()
  await expect(modal.getByText("Correct the file and validate again (not imported)", { exact: true })).toBeVisible()
  await expect(modal.getByRole("button", { name: "Confirm import", exact: true })).toBeDisabled()
  await modal.getByRole("button", { name: "Cancel", exact: true }).click()

  await page.getByRole("button", { name: "Bulk upload", exact: true }).click()
  const quote = (value: unknown) => `"${String(value).replaceAll("\"", "\"\"")}"`
  const rows = [[2, "mg/L"], [4, "mg/L"], [100, "g/L"]].map(([value, unit]) => [JSON.stringify({ id: sample.id, entity: "sample" }), "synthetic-method", "concentration", value, unit, "2026-01-01T12:00:00Z", "synthetic acceptance"].map(quote).join(","))
  const content = `${template.csv.split(/\r?\n/)[0]}\n${rows.join("\n")}\n`
  await modal.locator("input[type=\"file\"]").setInputFiles({ name: "synthetic-results.csv", mimeType: "text/csv", buffer: Buffer.from(content) })
  await modal.getByRole("button", { name: "Validate file", exact: true }).click()
  await expect(modal.getByText("Validation passed (not imported)", { exact: true })).toBeVisible()
  await modal.getByRole("checkbox").check()
  await modal.getByRole("button", { name: "Confirm import", exact: true }).click()
  await expect(modal).toBeHidden()
  await page.getByRole("link", { name: "4. Analyze and report", exact: true }).click()
  await expect(page.getByTestId("analysis-preview")).toBeEnabled()
  await page.getByTestId("analysis-preview").click()
  const analysisPreview = page.getByTestId("analysis-preview-dialog")
  await expect(analysisPreview).toContainText("method · metric · unit")
  await page.getByTestId("analysis-confirm").click()
  const table = page.getByTestId("analysis-result-table")
  await expect(table.locator("tbody tr")).toHaveCount(2, { timeout: 30000 })
  await expect(table).toContainText("mg/L")
  await expect(table).toContainText("g/L")
  await page.goto(`${project}/scenarios`)
  await page.getByRole("link", { name: "2. Record an experiment", exact: true }).click()
  const sampleInput = page.locator(".aimd-rec-entity-ref__input").first()
  await expect(sampleInput).toBeVisible()
  await sampleInput.fill(sampleCode)
  const sampleOption = page.locator(".aimd-rec-entity-ref__option").filter({ hasText: "Synthetic kit control" })
  await expect(sampleOption).toBeVisible()
  await sampleOption.click()
  for (const [field, value] of Object.entries({ method: "manual-method", metric: "concentration", value: "8", unit: "mg/L", measured_at: "2026-01-02 12:00:00" })) {
    const input = page.locator(`#form-research_variable-${field} input, #form-research_variable-${field} textarea`).first()
    await input.fill(value)
    await input.press("Tab")
  }
  await page.getByRole("button", { name: "Submit", exact: true }).click()
  await page.getByRole("dialog").getByRole("button", { name: "Submit Record", exact: true }).click()
  await page.getByRole("dialog").getByRole("button", { name: "View saved Record", exact: true }).click()
  await expect(page).toHaveURL(/\/record\/[^/]+\/v1$/)
  await page.goto(`${project}/scenarios`)
  await expect(page.getByRole("checkbox", { name: sampleCode, exact: true })).toBeVisible()
  await expect(page.getByRole("link", { name: "4. Analyze and report", exact: true })).toBeVisible()
  const workbench = page.getByTestId("scenario-workbench")
  const templateButton = page.getByRole("button", { name: /Download results template for selected samples/ })
  for (const width of [320, 390, 768, 1280]) {
    await page.setViewportSize({ width, height: 844 })
    await expect.poll(() => workbench.evaluate(element => element.scrollWidth - element.clientWidth)).toBeLessThanOrEqual(1)
    await expect.poll(() => templateButton.evaluate((element) => {
      const content = element.querySelector(".n-button__content")!
      return content.scrollWidth <= content.clientWidth + 1 && element.getBoundingClientRect().right <= window.innerWidth
    })).toBe(true)
  }
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ animations: "disabled", path: testInfo.outputPath("scenario-workbench-mobile.png"), fullPage: true })
  await page.evaluate(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
  await page.reload()
  await expect(page.getByRole("heading", { name: "场景工作台", exact: true })).toBeVisible()
  await expect(page.getByRole("button", { name: "登记样品", exact: true })).toBeVisible()
})

test.describe("viewer scenario permissions", () => {
  test.use({ storageState: "tests/e2e/.auth/viewer.json" })
  test("existing kit assets are readable without management actions", async ({ page }) => {
    const fixtures = await loadFixtures()
    await page.goto(`/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}/scenarios`)
    await expect(page.getByTestId("kit-catalog")).toBeVisible()
    await expect(page.getByRole("checkbox", { name: sampleCode, exact: true })).toBeVisible()
    await expect(page.getByRole("button", { name: "Register sample", exact: true })).toHaveCount(0)
    await expect(page.getByRole("button", { name: "Preview application", exact: true })).toHaveCount(0)
    await expect(page.getByRole("button", { name: "Bulk upload", exact: true })).toHaveCount(0)
  })
})
