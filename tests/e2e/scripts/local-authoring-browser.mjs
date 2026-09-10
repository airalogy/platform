// Called only by disposable API acceptance. The model/test outcome is injected
// there; this exercises the actual local UI, HTTP, files, API grants and database.
import assert from "node:assert/strict"
import { createHash } from "node:crypto"
import { readFile } from "node:fs/promises"
import { chromium, expect } from "@playwright/test"

const input = JSON.parse(process.env.AIRALOGY_SYNTHETIC_BROWSER_INPUT)
const browser = await chromium.launch({ headless: true })
try {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } })
  await page.goto(input.url)
  await expect(page.locator("#root")).toHaveText(input.root)
  await page.locator("#language").selectOption("en")
  if (input.stage === "prepare") {
    for (const [key, value] of Object.entries(input.fields))
      await page.locator(`[name="${key}"]`).fill(String(value))
    for (const [kind, file] of Object.entries(input.files)) {
      await page.locator(`[data-kind="${kind}"]`).setInputFiles(file)
      await expect(page.locator(`#${kind}-info`)).toContainText("Private local copy saved")
    }
    await page.getByRole("button", { name: "Preview", exact: true }).click()
    await expect(page.locator("#impact")).toContainText("\"hardware_authorized\": false")
    await expect(page.locator("#confirm")).toBeDisabled()
    await page.locator("#cancel").click()
    await expect(page.locator("#sessions option")).toHaveCount(1)
    await page.getByRole("button", { name: "Preview", exact: true }).click()
    await page.locator("#reviewed").check()
    await page.locator("#confirm").click()
    await expect(page.locator("#sessions option")).toHaveCount(2)
    const downloading = page.waitForEvent("download")
    await page.locator("#authorization").click()
    const file = await downloading
    const raw = await readFile(await file.path(), "utf8")
    assert.doesNotMatch(raw, /authoring_token|aiauthor_[\w-]{43}|gateway_token|sdk_wheel/)
    const authorization = JSON.parse(raw)
    assert.equal(authorization.schema, "airalogy.authoring-request.v1")
    process.stdout.write(JSON.stringify(authorization))
  }
  else {
    await page.locator("#run").click()
    await expect(page.locator("#impact")).toContainText("\"model_calls_permitted\": true")
    await expect(page.locator("#confirm")).toBeDisabled()
    await page.locator("#reviewed").check()
    await page.locator("#confirm").click()
    await expect(page.locator("#job")).toContainText("draft_tested", { timeout: 30000 })
    await page.reload()
    await page.locator("#inspect").click()
    await expect(page.locator("#artifacts")).toContainText("Locally tested draft")
    const downloading = page.waitForEvent("download")
    await page.getByRole("button", { name: "Download PRIVATE draft package", exact: true }).click()
    const raw = await readFile(await (await downloading).path())
    await page.locator("#language").selectOption("zh")
    await expect(page.getByRole("heading", { name: "本地适配开发向导" })).toBeVisible()
    await expect(page.getByRole("button", { name: "下载私有适配草稿包", exact: true })).toBeVisible()
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    await page.screenshot({ path: input.screenshot, fullPage: true })
    process.stdout.write(JSON.stringify({ sha256: createHash("sha256").update(raw).digest("hex") }))
  }
}
finally {
  await browser.close()
}
