import { execFileSync } from "node:child_process"
import { createHash } from "node:crypto"
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import { expect, test } from "@playwright/test"
import { instrumentWorkspaceUrl, loadFixtures } from "./fixtures"

test("private adapter import, protected download and source review do not qualify equipment", async ({ page, request }) => {
  const fixture = await loadFixtures()
  const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
  const login = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
  expect(login.ok()).toBeTruthy()
  const headers = { "Auth-Token": (await login.json()).token }
  const draft = { lab_id: fixture.lab.id, name: `Package fixture ${Date.now()}`, enabled: false }
  const preview = await (await request.post(`${api}/research-instrument-gateways/preview`, { headers, data: draft })).json()
  const created = await request.post(`${api}/research-instrument-gateways`, { headers, data: { ...draft, preview_digest: preview.preview_digest } })
  expect(created.ok()).toBeTruthy()
  const gateway = (await created.json()).gateway
  const directory = await mkdtemp(path.join(os.tmpdir(), "airalogy-adapter-e2e-"))
  try {
    const archive = path.join(directory, "synthetic.zip")
    const source = "apps/instrument-gateway/examples/adapter-package"
    // Isolate matching from other tests' packages in this shared synthetic Lab.
    const manifest = JSON.parse(await readFile(`${source}/manifest.json`, "utf8"))
    const model = `Catalogue reader ${Date.now()}`
    manifest.compatibility.declared[0].model = model
    const manifestPath = path.join(directory, "manifest.json")
    await writeFile(manifestPath, JSON.stringify(manifest))
    execFileSync("python3", ["-m", "airalogy_instrument_gateway.package_cli", "build", "--manifest", manifestPath, "--factory", "synthetic_reader:create_adapter", "--file", `source/synthetic_reader.py=${source}/source/synthetic_reader.py`, "--file", `tests/test_reader.py=${source}/tests/test_reader.py`, "--file", `licenses/LICENSE.txt=${source}/licenses/LICENSE.txt`, "--output", archive], {
      env: { ...process.env, PYTHONPATH: "apps/instrument-gateway/src" },
    })
    const original = await readFile(archive)
    const digest = createHash("sha256").update(original).digest("hex")
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto(instrumentWorkspaceUrl(fixture.lab.uid, gateway.id, "", "prepare"))
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
    await modal.getByRole("button", { name: "Close", exact: true }).click()
    await panel.getByRole("button", { name: "Find reusable adapters" }).click()
    modal = page.getByRole("dialog").last()
    await page.getByTestId("adapter-match-manufacturer").locator("input").fill("Synthetic")
    await page.getByTestId("adapter-match-model").locator("input").fill(model)
    await page.getByTestId("adapter-match-search").click()
    const candidate = page.getByTestId("adapter-match-candidate").filter({ hasText: digest })
    await expect(candidate).toContainText("More information or review needed")
    await expect(modal).toContainText("Matching does not check qualification")
    await modal.getByText("Compare software, firmware and runtime versions", { exact: true }).click()
    await page.getByTestId("adapter-match-application_version").locator("input").fill("unreviewed-version")
    await expect(page.getByTestId("adapter-match-results")).toHaveCount(0)
    await page.getByTestId("adapter-match-search").click()
    await expect(candidate).toContainText("Declared compatibility conflicts")
    await candidate.getByText(/Declared combination 1:/).click()
    await expect(candidate).toContainText("unreviewed-version")
    await expect(candidate).toContainText("1.0.0")
    await modal.screenshot({ path: test.info().outputPath("adapter-reuse-mobile.png"), animations: "disabled" })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await candidate.getByRole("button", { name: "Inspect and review" }).click()
    modal = page.getByRole("dialog").last()
    await expect(modal).toContainText(digest)
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
    await panel.getByTestId("adapter-release").filter({ hasText: digest }).getByRole("button", { name: "Inspect and review" }).click()
    modal = page.getByRole("dialog").last()
    await modal.getByText("Review history", { exact: true }).click()
    await expect(modal).toContainText("Synthetic version retired")
    await expect(modal.getByRole("button", { name: "Preview", exact: true })).toHaveCount(0)
    await modal.getByRole("button", { name: "Close", exact: true }).click()
    await panel.getByRole("button", { name: "Find reusable adapters" }).click()
    modal = page.getByRole("dialog").last()
    await page.getByTestId("adapter-match-manufacturer").locator("input").fill("Synthetic")
    await page.getByTestId("adapter-match-model").locator("input").fill(model)
    await page.getByTestId("adapter-match-search").click()
    await expect(page.getByTestId("adapter-match-candidate")).toHaveCount(0)
    await expect(modal).toContainText("No package in this Lab declares this exact manufacturer and model")
    await modal.getByRole("checkbox", { name: "Include revoked versions for inspection" }).check()
    await page.getByTestId("adapter-match-search").click()
    await expect(candidate).toContainText("Revoked")
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  }
  finally {
    await rm(directory, { recursive: true, force: true })
  }
})
