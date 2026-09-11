import { readFile } from "node:fs/promises"
import { expect, test } from "@playwright/test"
import { loadFixtures } from "./fixtures"

for (const locale of ["en-US", "zh-CN"]) {
  test(`Record export keeps gutters and reachable actions at every scope (${locale})`, async ({ page }, testInfo) => {
    const fixtures = await loadFixtures()
    await page.addInitScript(language => localStorage.setItem("lang", JSON.stringify({ data: language, expire: null })), locale)
    const lab = `/labs/${fixtures.lab.uid}`
    const project = `${lab}/projects/${fixtures.project.uid}`
    const cases = [
      { path: `${lab}/records`, width: 1440, height: 900 },
      { path: `${project}/records`, width: 850, height: 400 },
      { path: `${project}/protocols/${fixtures.schema_governance.protocol_uid}/records`, width: 320, height: 568 },
    ]
    for (const size of cases) {
      await page.setViewportSize({ width: size.width, height: size.height })
      await page.goto(size.path)
      await page.getByTestId("record-export-trigger").click()
      const dialog = page.getByTestId("record-export-modal")
      await expect(dialog).toBeVisible()
      await expect.poll(async () => (await dialog.boundingBox())?.width).toBeCloseTo(Math.min(760, size.width - 32), 0)
      const box = (await dialog.boundingBox())!
      expect(box.x).toBeGreaterThanOrEqual(15)
      expect(box.x + box.width).toBeLessThanOrEqual(size.width - 15)
      expect(box.y).toBeGreaterThanOrEqual(15)
      expect(box.y + box.height).toBeLessThanOrEqual(size.height - 15)
      const footer = dialog.locator(".n-card__footer")
      await expect(footer).toBeInViewport({ ratio: 1 })
      await expect(page.getByTestId("record-export-start")).toBeInViewport({ ratio: 1 })
      expect(await dialog.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true)
      await page.screenshot({ path: testInfo.outputPath(`record-export-${size.width}.png`) })
      await dialog.locator(".n-tabs-tab").filter({ hasText: /Export history|导出历史/ }).click()
      await expect(dialog.locator(".n-card__footer")).toHaveCount(0)
      const historyBox = (await dialog.boundingBox())!
      expect(historyBox.width).toBeLessThanOrEqual(761)
      expect(historyBox.x).toBeGreaterThanOrEqual(15)
      await page.keyboard.press("Escape")
      await expect(dialog).toHaveCount(0)
    }
  })
}

test("Lab Owner can create and download a background Record export", async ({ page }) => {
  const fixtures = await loadFixtures()
  await page.goto(`/labs/${fixtures.lab.uid}/records`)

  await page.getByTestId("record-export-trigger").click()
  await expect(page.getByTestId("record-export-modal")).toBeVisible()
  // Earlier journeys may have added valid Records to the same isolated Lab.
  await expect(page.getByTestId("record-export-modal").getByText(/[1-9]\d*\s*(条记录|Records?)/i).first()).toBeVisible()
  await expect(page.getByTestId("record-export-revisions")).toHaveAttribute("aria-checked", "false")
  await expect(page.getByTestId("record-export-attachments")).toHaveAttribute("aria-checked", "true")

  await page.getByTestId("record-export-format").getByText("JSONL", { exact: true }).click()
  const createResponse = page.waitForResponse(response => (
    response.url().endsWith("/record-exports")
    && response.request().method() === "POST"
    && response.ok()
  ))
  await page.getByTestId("record-export-start").click()
  await createResponse

  const historyItem = page.getByTestId("record-export-history-item").filter({ hasText: "JSONL" }).first()
  await expect(historyItem).toBeVisible()
  await expect(historyItem.getByRole("button", { name: /下载|Download/i })).toBeVisible({ timeout: 30_000 })

  const download = page.waitForEvent("download")
  await historyItem.getByRole("button", { name: /下载|Download/i }).click()
  const downloaded = await download
  expect(downloaded.suggestedFilename()).toMatch(/\.jsonl$/)
  const downloadedPath = await downloaded.path()
  expect(downloadedPath).not.toBeNull()
  const records = (await readFile(downloadedPath!, "utf8"))
    .trim()
    .split("\n")
    .map(line => JSON.parse(line) as Record<string, unknown>)
  expect(records.length).toBeGreaterThan(0)
  expect(records[0]).toMatchObject({
    format: "airalogy.record",
    schema_version: 1,
  })

  await page.goto(`/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}/records`)
  await expect(page.getByTestId("record-export-trigger")).toBeVisible()

  await page.goto(
    `/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}`
    + `/protocols/${fixtures.schema_governance.protocol_uid}/records`,
  )
  await expect(page.getByTestId("record-export-trigger")).toBeVisible()
})
