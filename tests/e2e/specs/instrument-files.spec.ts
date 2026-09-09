import { randomUUID } from "node:crypto"
import { mkdtemp, readFile, realpath, rm } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import { expect, test } from "@playwright/test"
import { selectVisibleOption } from "./fixtures"
import { deliverSyntheticFile } from "./instrument-file-fixture"

test("instrument originals: mobile review, exact Record, receipt loss, stale preview and read-only access", async ({ page, request, browser }, testInfo) => {
  test.setTimeout(150000)
  page.setDefaultTimeout(15000)
  const directory = await realpath(await mkdtemp(path.join(os.tmpdir(), "airalogy-file-e2e-")))
  try {
    const setup = await deliverSyntheticFile(request, directory)
    const { fixtures, api, headers, call, confirm, task, outputsUrl, output } = setup
    const file = output.items[0]
    const record = fixtures.schema_governance
    const recordUrl = `/protocols/${record.protocol_id}/records/${record.record_id}?version=${record.record_version}`
    const original = await call(recordUrl, undefined, "GET")
    const associationUrl = `${outputsUrl}/${file.id}/associations`
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto(`/research/tasks/${task.id}`)
    await page.getByTestId("instrument-files-open").click()
    const panel = page.getByTestId("instrument-files")
    await expect(panel).toContainText("synthetic.csv")
    await expect(panel).toContainText("File delivery complete")
    await expect(panel).toContainText("Not associated with a Record")
    await panel.getByText("Original file and provenance", { exact: true }).click()
    await expect(panel).toContainText(file.sha256)
    await expect(panel).toContainText("signal: synthetic_unit")
    const downloadEvent = page.waitForEvent("download")
    await panel.getByRole("button", { name: "Download original", exact: true }).click()
    const downloaded = await downloadEvent
    expect(downloaded.suggestedFilename()).toBe("synthetic.csv")
    expect(await readFile((await downloaded.path())!, "utf8")).toBe("sample,signal\nsynthetic,0.84\n")
    expect((await page.locator(".instrument-files-dialog").boundingBox())!.width).toBeLessThanOrEqual(358)
    expect((await panel.getByRole("heading", { name: "synthetic.csv", exact: true }).boundingBox())!.height).toBeLessThan(40)
    await page.screenshot({ path: testInfo.outputPath("instrument-files-mobile.png"), animations: "disabled" })

    async function chooseRecord(button: string) {
      await panel.getByRole("button", { name: button, exact: true }).click()
      await page.getByTestId("instrument-record-protocol").click()
      await selectVisibleOption(page, record.protocol_uid)
      const editor = page.getByTestId("instrument-association")
      await editor.locator(".n-input-group input").fill(record.record_id)
      const options = page.waitForResponse(response => response.url().includes("/record-options?") && response.url().includes(record.record_id))
      await editor.getByRole("button", { name: "Search", exact: true }).click()
      expect((await options).ok()).toBe(true)
      await expect(page.locator(".instrument-association-dialog").getByRole("button", { name: "Preview", exact: true })).toBeEnabled()
      await page.getByTestId("instrument-record-version").click()
      await selectVisibleOption(page, new RegExp(` · v${record.record_version} · `))
      return page.locator(".instrument-association-dialog")
    }
    const editor = await chooseRecord("Associate Record")
    await editor.locator("textarea").fill("Synthetic sample A — operator selected")
    await editor.getByRole("button", { name: "Preview", exact: true }).click()
    await expect(editor).toContainText(record.record_id)
    await expect(editor).toContainText(file.sha256)
    await expect(editor).toContainText("Existing Record data and previous associations will be preserved")
    expect((await editor.boundingBox())!.width).toBeLessThanOrEqual(358)
    await page.screenshot({ path: testInfo.outputPath("instrument-association-mobile.png"), animations: "disabled" })
    let committedId = ""
    await page.route(`**/api${associationUrl}`, async (route) => {
      const response = await route.fetch()
      expect(response.ok(), await response.text()).toBeTruthy()
      committedId = (await response.json()).id
      await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Synthetic lost response after real commit" }) })
    }, { times: 1 })
    await editor.getByRole("button", { name: "Confirm", exact: true }).click()
    await expect(editor).toContainText("Retry the same confirmation")
    await editor.getByRole("button", { name: "Confirm", exact: true }).click()
    await expect(panel.getByTestId("instrument-association-saved")).toBeVisible()
    let history = await call(associationUrl, undefined, "GET")
    expect(history.items).toHaveLength(1)
    expect(history.items[0].id).toBe(committedId)
    expect(await call(recordUrl, undefined, "GET")).toEqual(original)
    await panel.getByRole("button", { name: "Association history", exact: true }).click()
    await expect(panel.locator(".file-history")).toContainText("Synthetic sample A")
    const recordLink = panel.locator(".file-record-link").first()
    await expect(recordLink).toHaveAttribute("href", new RegExp(`${record.record_id}.*${record.record_version}`))

    // A second user's save invalidates the existing preview, without discarding history.
    await chooseRecord("Change association")
    await editor.locator("textarea").fill("Stale proposal must not be written")
    await editor.getByRole("button", { name: "Preview", exact: true }).click()
    await expect(editor).toContainText("Stale proposal must not be written")
    const replacement = { id: randomUUID(), record_id: record.record_id, record_version: record.record_version, sample_reference: "Newer independently confirmed selection", expected_association_id: committedId }
    await confirm(associationUrl, replacement)
    const conflict = page.waitForResponse(response => response.url().endsWith(associationUrl) && response.request().method() === "POST")
    await editor.getByRole("button", { name: "Confirm", exact: true }).click()
    expect((await conflict).status()).toBe(409)
    await editor.getByRole("button", { name: "Check saved state", exact: true }).click()
    await expect(editor.getByRole("button", { name: "Preview", exact: true })).toBeDisabled()
    await editor.getByRole("button", { name: "Cancel", exact: true }).click()
    await expect(panel).toContainText(replacement.sample_reference)
    history = await call(associationUrl, undefined, "GET")
    expect(history.items.map((item: { id: string }) => item.id)).toEqual([replacement.id, committedId])
    expect(await call(recordUrl, undefined, "GET")).toEqual(original)

    // Existing viewer session: actual server permissions, not hidden UI-only restrictions.
    const viewerContext = await browser.newContext({ baseURL: new URL(page.url()).origin, storageState: "tests/e2e/.auth/viewer.json", viewport: { width: 1440, height: 1000 } })
    try {
      const viewer = await viewerContext.newPage()
      await viewer.goto(`/research/tasks/${task.id}`)
      await viewer.getByTestId("instrument-files-open").click()
      const readOnly = viewer.getByTestId("instrument-files")
      await expect(readOnly).toContainText("Associating a Record requires")
      await expect(readOnly.getByRole("button", { name: "Change association", exact: true })).toHaveCount(0)
      await expect(readOnly.getByRole("button", { name: "Download original", exact: true })).toBeVisible()
      await viewer.locator(".instrument-files-dialog").screenshot({ path: testInfo.outputPath("instrument-files-desktop.png"), animations: "disabled" })
      await viewer.addInitScript(() => {
        localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null }))
      })
      await viewer.reload()
      await viewer.getByTestId("instrument-files-open").click()
      await expect(readOnly).toContainText("原件已接收")
      await expect(readOnly).toContainText("关联 Record 还需要科研执行及知识创建权限")
      await viewer.locator(".instrument-files-dialog").screenshot({ path: testInfo.outputPath("instrument-files-zh.png"), animations: "disabled" })
    }
    finally {
      await viewerContext.close()
    }
    // An unavailable/revoked refresh must clear previously rendered private details.
    await page.route(`**/api${outputsUrl}`, route => route.fulfill({ status: 403, contentType: "application/json", body: JSON.stringify({ detail: "Synthetic access withdrawn" }) }), { times: 1 })
    await panel.getByRole("button", { name: "Refresh", exact: true }).click()
    await expect(panel).not.toContainText("synthetic.csv")
    await expect(panel).not.toContainText(file.sha256)
    await expect(panel).toContainText("Could not load")
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    expect((await request.get(api + outputsUrl, { headers })).ok()).toBe(true)
  }
  finally {
    await rm(directory, { recursive: true, force: true })
  }
})
