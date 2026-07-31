import { readFile } from "node:fs/promises"
import { expect, test } from "@playwright/test"
import { loadFixtures } from "./fixtures"

test("Lab Owner can create and download a background Record export", async ({ page }) => {
  const fixtures = await loadFixtures()
  await page.goto(`/labs/${fixtures.lab.uid}/records`)

  await page.getByTestId("record-export-trigger").click()
  await expect(page.getByTestId("record-export-modal")).toBeVisible()
  await expect(page.getByText(/1\s*(条记录|Records?)/i).first()).toBeVisible()
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
