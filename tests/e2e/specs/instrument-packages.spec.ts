import { execFileSync } from "node:child_process"
import { createHash } from "node:crypto"
import { mkdtemp, readFile, rm } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import { expect, test } from "@playwright/test"
import { loadFixtures } from "./fixtures"

test("private adapter import, protected download and source review do not qualify equipment", async ({ page }) => {
  const fixture = await loadFixtures()
  const directory = await mkdtemp(path.join(os.tmpdir(), "airalogy-adapter-e2e-"))
  try {
    const archive = path.join(directory, "synthetic.zip")
    const source = "apps/instrument-gateway/examples/adapter-package"
    execFileSync("python3", ["-m", "airalogy_instrument_gateway.package_cli", "build", "--manifest", `${source}/manifest.json`, "--factory", "synthetic_reader:create_adapter", "--file", `source/synthetic_reader.py=${source}/source/synthetic_reader.py`, "--file", `tests/test_reader.py=${source}/tests/test_reader.py`, "--file", `licenses/LICENSE.txt=${source}/licenses/LICENSE.txt`, "--output", archive], {
      env: { ...process.env, PYTHONPATH: "apps/instrument-gateway/src" },
    })
    const original = await readFile(archive)
    const digest = createHash("sha256").update(original).digest("hex")
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto(`/labs/${fixture.lab.uid}/resources/gateways`)
    const panel = page.getByTestId("instrument-packages-panel")
    await expect(panel).toBeVisible()
    expect((await panel.boundingBox())!.width).toBeLessThanOrEqual(390)
    await panel.getByRole("button", { name: "Import adapter package" }).click()
    await page.getByTestId("adapter-upload").setInputFiles(archive)
    let modal = page.getByRole("dialog").last()
    await modal.getByRole("button", { name: "Preview", exact: true }).click()
    await expect(page.getByTestId("adapter-import-preview")).toContainText("synthetic.reader")
    await expect(modal).toContainText(digest)
    await modal.getByRole("button", { name: "Confirm", exact: true }).click()
    await expect(panel).toContainText("Awaiting source review")
    modal = page.getByRole("dialog").last()
    await expect(modal.getByRole("button", { name: "Download exact archive" })).toBeEnabled()
    const downloaded = page.waitForEvent("download")
    await modal.getByRole("button", { name: "Download exact archive" }).click()
    const download = await downloaded
    expect(await readFile((await download.path())!)).toEqual(original)
    await page.getByTestId("adapter-review-reason").locator("textarea").fill("Synthetic source inspected; no physical qualification")
    await expect(modal.getByRole("button", { name: "Preview", exact: true })).toBeDisabled()
    await modal.getByRole("checkbox").check()
    await modal.getByRole("button", { name: "Preview", exact: true }).click()
    await expect(modal).toContainText("Installation and equipment qualification still require separate approval")
    await modal.getByRole("button", { name: "Confirm", exact: true }).click()
    await expect(panel).toContainText("Source approved, not qualified")
    await page.getByTestId("adapter-review-reason").locator("textarea").fill("Synthetic version retired")
    await modal.getByRole("button", { name: "Preview", exact: true }).click()
    await expect(modal).toContainText("This does not uninstall software or stop physical equipment")
    await modal.getByRole("button", { name: "Confirm", exact: true }).click()
    await expect(panel).toContainText("Revoked")
    await modal.getByRole("button", { name: "Close", exact: true }).click()
    await page.reload()
    await expect(panel).toContainText(digest)
    await expect(panel).toContainText("Revoked")
    await panel.getByRole("button", { name: "Inspect and review" }).click()
    modal = page.getByRole("dialog").last()
    await modal.getByText("Review history", { exact: true }).click()
    await expect(modal).toContainText("Synthetic version retired")
    await expect(modal.getByRole("button", { name: "Preview", exact: true })).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  }
  finally {
    await rm(directory, { recursive: true, force: true })
  }
})
