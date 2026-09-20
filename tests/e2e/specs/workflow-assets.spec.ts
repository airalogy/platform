import type { Locator, Page } from "@playwright/test"
import type { ResearchAction } from "../../../apps/web/src/service/api/research-tasks"
import type { WorkflowAssetVersion, WorkflowContext, WorkflowDefinitionDetail, WorkflowRunPreview, WorkflowSavePreview } from "../../../apps/web/src/service/api/workflow-definitions"
import { Buffer } from "node:buffer"
import { randomUUID } from "node:crypto"
import { expect, test } from "@playwright/test"
import { loadFixtures, selectVisibleOption } from "./fixtures"

// Real stored JSON, ordinary Workflow/Task APIs and actual approvals. Synthetic
// input data is not experimental evidence; no Action, result or response is mocked.
for (const locale of ["en-US", "zh-CN"] as const) {
  test(`Workflow DataAsset inputs keep exact versions, literal keys and controlled files (${locale})`, async ({ page, request }, testInfo) => {
    test.setTimeout(180_000)
    page.setDefaultTimeout(15_000)
    const browserErrors: string[] = []
    page.on("pageerror", error => browserErrors.push(error.message))
    const fixtures = await loadFixtures()
    const seed = fixtures.workflow_assets
    const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
    const signin = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
    expect(signin.ok()).toBe(true)
    const headers = { "Auth-Token": (await signin.json()).token }
    async function call(path: string, data?: unknown) {
      const response = await request.fetch(`${api}${path}`, { method: data === undefined ? "GET" : "POST", headers, data })
      expect(response.ok(), `${path}: ${await response.text()}`).toBe(true)
      return response.json()
    }
    if (process.env.AI_ENABLED === "false")
      expect((await call("/instance")).ai_enabled).toBe(false)
    const title = `Synthetic fixed asset workflow ${locale} ${randomUUID().slice(0, 8)}`
    const projectPath = `/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}`
    await page.addInitScript(language => localStorage.setItem("lang", JSON.stringify({ data: language, expire: null })), locale)
    await page.setViewportSize({ width: 390, height: 844 })
    const contextResponse = page.waitForResponse(response => response.url().includes("/workflow-definitions/context?") && response.ok())
    await page.goto(`${projectPath}/workflows`)
    const context: WorkflowContext = await (await contextResponse).json()
    const protocol = context.protocols.find(item => item.id === seed.protocol_id)!
    const fields = protocol.versions.find(version => version.id === seed.protocol_version_id)!.fields!
    const scalar = fields.find(field => field.path[1] === seed.scalar_field)!
    const file = fields.find(field => field.path[1] === seed.file_field)!
    expect(file.value_type).toBe("file")
    expect(scalar).toMatchObject({ value_type: "number", unit: seed.unit })
    await page.getByTestId("workflow-title").locator("input").fill(title)
    await page.getByTestId("workflow-add-protocol").click()
    await selectVisibleOption(page, protocol.name)
    await page.getByTestId("workflow-add-card").click()
    await page.getByTestId("workflow-card-title").locator("input").fill("Review exact synthetic asset")
    const nodeId = (await page.getByTestId("workflow-card-list").locator("article").getAttribute("data-node-id"))!
    await page.getByTestId("workflow-add-asset-input").click()
    await page.getByTestId("workflow-asset-label").locator("input").fill("Synthetic calibrated input")
    await expect(page.getByTestId("workflow-preview-save")).toBeDisabled()
    const bindings = page.getByTestId("workflow-asset-bindings")
    await bindings.getByTestId("workflow-asset-binding-input").click()
    await selectVisibleOption(page, "Synthetic calibrated input")
    await bindings.getByTestId("workflow-asset-binding-target").click()
    await selectVisibleOption(page, `${file.title} (json)`)
    await bindings.getByTestId("workflow-asset-binding-add").click()
    await bindings.getByTestId("workflow-asset-binding-type").click()
    await selectVisibleOption(page, locale === "en-US" ? /^Number$/ : /^数值$/)
    await bindings.getByTestId("workflow-asset-json-key").locator("input").fill(seed.source_path[1])
    await bindings.getByTestId("workflow-asset-add-key").click()
    await bindings.getByTestId("workflow-asset-json-key").last().locator("input").fill(seed.source_path[2])
    await bindings.getByTestId("workflow-asset-binding-unit").locator("input").fill(seed.unit)
    await bindings.getByTestId("workflow-asset-binding-target").click()
    await selectVisibleOption(page, `${scalar.title} (${seed.unit})`)
    await bindings.getByTestId("workflow-asset-binding-add").click()
    await expect(bindings.getByTestId("workflow-asset-binding-item")).toHaveCount(2)
    const savePreviewResponse = page.waitForResponse(response => response.url().endsWith("/workflow-definitions/preview") && response.request().method() === "POST")
    await page.getByTestId("workflow-preview-save").click()
    const savePreviewHttp = await savePreviewResponse
    expect(savePreviewHttp.ok(), await savePreviewHttp.text()).toBe(true)
    const preview: WorkflowSavePreview = await savePreviewHttp.json()
    expect(preview.graph.schema_version).toBe(5)
    expect(preview.graph.nodes).toHaveLength(1)
    expect(preview.graph.edges).toEqual([])
    expect(preview.graph.bindings).toEqual([])
    expect(preview.graph.asset_inputs).toEqual([{ input_id: "asset_1", label: "Synthetic calibrated input" }])
    expect(preview.graph.asset_bindings).toEqual(expect.arrayContaining([
      expect.objectContaining({ source_path: ["file"], value_type: "file", target_node_id: nodeId, target_path: ["var", seed.file_field] }),
      expect.objectContaining({ source_path: seed.source_path, value_type: "number", unit: seed.unit, target_node_id: nodeId, target_path: ["var", seed.scalar_field] }),
    ]))
    expect(JSON.stringify(preview.graph)).not.toContain(seed.data_asset_version_id)
    const saveResponse = page.waitForResponse(response => response.url().endsWith("/workflow-definitions/confirm") && response.request().method() === "POST")
    await page.getByTestId("workflow-confirm-save").click()
    const saveHttp = await saveResponse
    expect(saveHttp.ok(), await saveHttp.text()).toBe(true)
    const saved: WorkflowDefinitionDetail = await saveHttp.json()
    await expect(page.getByTestId("workflow-result")).toContainText(title)
    await expect(page.locator(".n-modal-mask")).toHaveCount(0)
    await page.reload()
    await page.getByTestId("workflow-saved-item").filter({ hasText: title }).click()
    await expect(page.getByTestId("workflow-asset-label").locator("input")).toHaveValue("Synthetic calibrated input")
    const reloaded: WorkflowDefinitionDetail = await call(`/workflow-definitions/${saved.id}`)
    expect(reloaded.current_revision?.graph).toEqual(preview.graph)

    const taskDraft = { project_id: fixtures.project.id, title: `${title} Task`, goal: "Review exact synthetic asset version 1; no physical experiment performed.", success_criteria: ["Literal JSON scalar and controlled whole file match the selected immutable version."], protocol_ids: [seed.protocol_id] }
    const taskPreview = await call("/research-tasks/preview", taskDraft)
    const task = await call("/research-tasks", { ...taskDraft, preview_digest: taskPreview.preview_digest })
    if (process.env.AI_ENABLED === "false")
      expect(task.ai_available).toBe(false)
    const versionsResponse = page.waitForResponse(response => response.url().includes("/workflow-definitions/asset-versions?") && response.ok())
    await page.getByTestId("workflow-open-run").click()
    const catalog: { items: WorkflowAssetVersion[] } = await (await versionsResponse).json()
    expect(catalog.items).toEqual(expect.arrayContaining([
      expect.objectContaining({ version_id: seed.data_asset_version_id, version: 1 }),
      expect.objectContaining({ data_asset_id: seed.data_asset_id, version: seed.latest_version }),
    ]))
    expect(catalog.items.find(version => version.version_id === seed.data_asset_version_id)!.fields).toEqual(expect.arrayContaining([expect.objectContaining({ path: seed.source_path, value_type: "number", unit: seed.unit })]))
    await page.getByTestId("workflow-task").click()
    await selectVisibleOption(page, taskDraft.title)
    await expect(page.getByTestId("workflow-preview-run")).toBeDisabled()
    await page.getByTestId("workflow-asset-version").click()
    await selectVisibleOption(page, `${seed.name} · v${seed.version}`)
    await expect(page.getByTestId("workflow-asset-run-slot")).toContainText(seed.data_asset_version_id)
    const runPreviewResponse = page.waitForResponse(response => response.url().endsWith(`/workflow-definitions/${saved.id}/runs/preview`) && response.request().method() === "POST")
    await page.getByTestId("workflow-preview-run").click()
    const runPreviewHttp = await runPreviewResponse
    expect(runPreviewHttp.ok(), await runPreviewHttp.text()).toBe(true)
    expect(runPreviewHttp.request().postDataJSON().asset_versions).toEqual({ asset_1: seed.data_asset_version_id })
    const runPreview: WorkflowRunPreview = await runPreviewHttp.json()
    expect(runPreview.asset_inputs).toHaveLength(1)
    expect(runPreview.asset_inputs![0]).toMatchObject({ input_id: "asset_1", version: 1, data_asset_version_id: seed.data_asset_version_id, sha256: seed.sha256 })
    expect(runPreview.asset_inputs![0].bindings.find(binding => binding.value_type === "number")!.value).toBe(seed.value)
    const assetPreview = page.getByTestId("workflow-asset-preview")
    await expect(assetPreview).toContainText(seed.filename)
    await expect(assetPreview).toContainText(seed.sha256)
    await expect(assetPreview).toContainText(String(seed.value))
    await assetPreview.scrollIntoViewIfNeeded()
    await stableCapture(page, assetPreview)
    await page.screenshot({ path: testInfo.outputPath(`workflow-asset-preview-${locale}-phone.png`) })
    const confirmedResponse = page.waitForResponse(response => response.url().endsWith(`/workflow-definitions/${saved.id}/runs/confirm`) && response.request().method() === "POST")
    await page.getByTestId("workflow-confirm-run").click()
    const confirmed = await confirmedResponse
    expect(confirmed.ok(), await confirmed.text()).toBe(true)
    await expect(page).toHaveURL(new RegExp(`/research/tasks/${task.id}$`))
    async function readAction(): Promise<ResearchAction> {
      return (await call(`/research-tasks/${task.id}`)).actions.find((action: ResearchAction) => action.input_data.action_graph?.node_id === nodeId)
    }
    const action = await readAction()
    expect(action.approval?.status).toBe("pending")
    expect(action.input_data.initial_values?.[seed.scalar_field]).toBe(seed.value)
    const alias = action.input_data.initial_values?.[seed.file_field]
    expect(alias).toMatch(/^airalogy\.id\.file\..+\.json$/)
    expect(action.input_data.workflow_resolution.receipt.asset_sources.asset_1).toMatchObject({ kind: "data_asset", data_asset_version_id: seed.data_asset_version_id, version: 1 })
    const approval = page.locator("#research-approvals article").filter({ has: page.getByRole("heading", { name: action.title, exact: true }) })
    const receipt = approval.getByTestId("workflow-resolved-asset")
    await expect(receipt).toContainText(seed.data_asset_version_id)
    await expect(receipt.getByTestId("workflow-resolved-file")).toContainText(seed.filename)
    await expect(receipt).toContainText(seed.sha256)
    await receipt.scrollIntoViewIfNeeded()
    await stableCapture(page, receipt)
    await page.screenshot({ path: testInfo.outputPath(`workflow-asset-approval-${locale}-phone.png`) })
    await approval.getByRole("button", { name: locale === "en-US" ? "Approve Action" : "批准 Action", exact: true }).click()
    const approvedResponse = page.waitForResponse(response => response.url().endsWith(`/research-approvals/${action.approval!.id}/approve`) && response.request().method() === "POST")
    await page.getByRole("button", { name: locale === "en-US" ? "Confirm approval" : "确认批准", exact: true }).click()
    const approvedHttp = await approvedResponse
    expect(approvedHttp.ok(), await approvedHttp.text()).toBe(true)
    const approved = await readAction()
    expect(approved.protocol_run?.initial_values).toMatchObject({ [seed.scalar_field]: seed.value, [seed.file_field]: alias })
    expect(approved.work_item?.status).toBe("open")
    const metadata = await call(`/airalogy_files/${alias}`)
    expect(metadata.workflow_managed).toBe(true)
    expect(metadata.filename).toBe(seed.filename)
    // The controlled reference serves the selected bytes, not the newer v2 file.
    const download = await request.get(`${api}/airalogy_files/${alias}/download`, { headers })
    expect(download.ok(), await download.text()).toBe(true)
    expect((await download.json()).metrics["calibration.mean"]).toBe(seed.value)
    await page.goto(`/research/work-items/${approved.work_item!.id}`)
    await page.getByRole("button", { name: locale === "en-US" ? "Execute Protocol" : "执行 Protocol", exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`researchWorkItem=${approved.work_item!.id}`))
    const main = page.getByTestId("record-main-content")
    const dose = main.locator("input:not([type=\"file\"])").first()
    await expect(dose).toHaveValue(String(seed.value))
    const inlineFile = main.getByTestId("aimd-inline-file-input")
    const attachment = inlineFile.getByText(seed.filename, { exact: true })
    await expect(attachment).toBeVisible()
    await expect(inlineFile).not.toContainText("file.file")
    await attachment.scrollIntoViewIfNeeded()
    await stableCapture(page, attachment)
    await expect(attachment).toBeInViewport({ ratio: 1 })
    await expect.poll(() => inlineFile.evaluate((element) => {
      const bounds = element.getBoundingClientRect()
      return bounds.width >= 260 && bounds.left >= 0 && bounds.right <= innerWidth
    })).toBe(true)
    await page.screenshot({ path: testInfo.outputPath(`workflow-asset-record-${locale}-phone.png`) })
    // Inline editing must not open the mobile field drawer or steal focus.
    await dose.fill("3.5")
    await dose.press("Tab")
    await expect(page.getByTestId("record-fields-drawer")).toBeHidden()
    await expect(dose).toHaveValue("3.5")
    await page.getByTestId("record-open-fields").click()
    const drawer = page.getByTestId("record-fields-drawer")
    await expect(drawer).toBeVisible()
    const drawerDose = drawer.locator(`#form-research_variable-${seed.scalar_field} input`)
    await expect(drawerDose).toHaveValue("3.5")
    await drawerDose.fill(String(seed.value))
    await drawerDose.press("Tab")
    await expect(drawer.locator(".file-card__name").filter({ hasText: seed.filename })).toBeVisible()
    await stableCapture(page, drawer)
    await page.screenshot({ path: testInfo.outputPath(`workflow-asset-fields-${locale}-phone.png`) })
    await drawer.locator(".n-drawer-header__close").click()
    await expect(drawer).toBeHidden()
    await expect(page.locator(".n-drawer-mask")).toHaveCount(0)
    await expect(dose).toHaveValue(String(seed.value))
    await expect(attachment).toBeVisible()
    await page.getByRole("button", { name: locale === "en-US" ? "Submit" : "提交", exact: true }).click()
    const confirmation = page.getByRole("dialog")
    await expect(confirmation).toContainText("2/2")
    const recordResponse = page.waitForResponse(response => response.url().endsWith(`/protocols/${seed.protocol_id}/records`) && response.request().method() === "POST")
    const workResponse = page.waitForResponse(response => response.url().endsWith(`/research-work-items/${approved.work_item!.id}/submit`) && response.request().method() === "POST")
    await confirmation.getByRole("button", { name: locale === "en-US" ? "Submit Record" : "提交 Record", exact: true }).click()
    const recordHttp = await recordResponse
    expect(recordHttp.ok(), await recordHttp.text()).toBe(true)
    // Display-only metadata must never replace the exact FileId in saved values.
    expect(recordHttp.request().postDataJSON().var).toMatchObject({ [seed.scalar_field]: seed.value, [seed.file_field]: alias })
    const workHttp = await workResponse
    expect(workHttp.ok(), await workHttp.text()).toBe(true)
    await expect(page.getByRole("dialog")).toContainText(locale === "en-US" ? "Evidence accepted" : "证据已验收")
    const completed = await readAction()
    expect(completed.status).toBe("completed")
    expect(completed.work_item?.status).toBe("accepted")
    const submittedRecord = workHttp.request().postDataJSON()
    const persisted = await call(`/protocols/${seed.protocol_id}/records/${submittedRecord.record_id}?version=${submittedRecord.record_version}`)
    expect(persisted.data.var).toMatchObject({ [seed.scalar_field]: seed.value, [seed.file_field]: alias })
    await page.getByRole("dialog").getByRole("button", { name: locale === "en-US" ? "Return to Research Task" : "返回 Research Task", exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`/research/tasks/${task.id}$`))
    expect(browserErrors).toEqual([])
    expect((await call(`/workflow-definitions/${saved.id}`)).current_revision.graph).toEqual(preview.graph)
  })
}

test("mobile inline files persist before first opening and after closing the field drawer", async ({ page }) => {
  test.setTimeout(90_000)
  const fixtures = await loadFixtures()
  const seed = fixtures.workflow_assets
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "en-US", expire: null })))
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(`/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}/protocols/${seed.protocol_uid}/add`)
  const main = page.getByTestId("record-main-content")
  const dose = main.locator("input:not([type=\"file\"])").first()
  await dose.fill("7")
  // The numeric control commits on blur, as when a user clicks the uploader.
  // setInputFiles alone does not move focus and is not that user interaction.
  await dose.press("Tab")
  await expect(page.getByText("1/2", { exact: true })).toBeVisible()
  const inlineFile = main.getByTestId("aimd-inline-file-input")
  const drawer = page.getByTestId("record-fields-drawer")
  async function upload(filename: string, value: number): Promise<string> {
    const uploaded = page.waitForResponse(response => response.url().endsWith("/airalogy_files") && response.request().method() === "POST")
    await inlineFile.locator("input[type=\"file\"]").setInputFiles({ name: filename, mimeType: "application/json", buffer: Buffer.from(JSON.stringify({ synthetic: true, value })) })
    const response = await uploaded
    expect(response.ok(), await response.text()).toBe(true)
    await expect(inlineFile.getByText(filename, { exact: true })).toBeVisible()
    await expect(drawer).toBeHidden()
    return (await response.json()).airalogy_file_id
  }
  const oldReference = await upload("synthetic-before-replacement.json", 1)
  await expect(page.getByText("2/2", { exact: true })).toBeVisible()
  await page.getByTestId("record-open-fields").click()
  await expect(drawer.locator(".file-card__name").filter({ hasText: "synthetic-before-replacement.json" })).toBeVisible()
  await drawer.locator(".n-drawer-header__close").click()
  await expect(drawer).toBeHidden()
  await expect(page.locator(".n-drawer-mask")).toHaveCount(0)
  await inlineFile.getByRole("button", { name: "Delete", exact: true }).click()
  await expect(inlineFile.getByText("synthetic-before-replacement.json", { exact: true })).toHaveCount(0)
  await expect(page.getByText("1/2", { exact: true })).toBeVisible()
  await expect(drawer).toBeHidden()
  const replacement = await upload("synthetic-after-replacement.json", 2)
  expect(replacement).toMatch(/^airalogy\.id\.file\..+\.json$/)
  expect(replacement).not.toBe(oldReference)
  await expect(page.getByText("2/2", { exact: true })).toBeVisible()
  await page.getByRole("button", { name: "Submit", exact: true }).click()
  const submitted = page.waitForResponse(response => response.url().endsWith(`/protocols/${seed.protocol_id}/records`) && response.request().method() === "POST")
  await page.getByRole("dialog").getByRole("button", { name: "Submit Record", exact: true }).click()
  const response = await submitted
  expect(response.ok(), await response.text()).toBe(true)
  expect(response.request().postDataJSON().var).toMatchObject({ [seed.scalar_field]: 7, [seed.file_field]: replacement })
  const persisted = page.waitForResponse(response => new URL(response.url()).pathname.startsWith(`/api/protocols/${seed.protocol_id}/records/`) && response.request().method() === "GET")
  await page.getByRole("dialog").getByRole("button", { name: "View saved Record", exact: true }).click()
  const record = await persisted
  expect(record.ok(), await record.text()).toBe(true)
  expect((await record.json()).data.var).toMatchObject({ [seed.scalar_field]: 7, [seed.file_field]: replacement })
  await expect(page).toHaveURL(/\/record\/[^/]+\/v1$/)
})

async function stableCapture(page: Page, surface: Locator) {
  await expect(page.locator(".n-message")).toHaveCount(0, { timeout: 10_000 })
  await expect(surface).toBeVisible()
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
  await expect.poll(() => surface.evaluate((element) => {
    for (let node: Element | null = element; node; node = node.parentElement) {
      if (getComputedStyle(node).opacity !== "1" || node.getAnimations().some(animation => animation.playState === "running" || animation.pending))
        return false
    }
    return true
  })).toBe(true)
}
