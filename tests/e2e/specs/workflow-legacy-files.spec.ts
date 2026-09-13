import type { ResearchAction } from "../../../apps/web/src/service/api/research-tasks"
import type { WorkflowConversionContext, WorkflowConversionPreview, WorkflowConversionResult } from "../../../apps/web/src/service/api/workflow-conversions"
import type { WorkflowContext, WorkflowDefinitionDetail, WorkflowFileField, WorkflowSavePreview } from "../../../apps/web/src/service/api/workflow-definitions"
import { randomUUID } from "node:crypto"
import { expect, test } from "@playwright/test"
import { loadFixtures, selectVisibleOption } from "./fixtures"

// All sources, previews, confirmations and file references use the real disposable
// API. Synthetic files are labelled fixture data; no instrument or model is used.
for (const locale of ["en-US", "zh-CN"] as const) {
  test(`Legacy conversion explicitly excludes prose and preserves the old Workflow (${locale})`, async ({ page, request }, testInfo) => {
    const fixtures = await loadFixtures()
    const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
    const signIn = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
    expect(signIn.ok()).toBe(true)
    const headers = { "Auth-Token": (await signIn.json()).token }
    async function call(path: string, data?: unknown) {
      const response = await request.fetch(`${api}${path}`, { method: data === undefined ? "GET" : "POST", headers, data })
      expect(response.ok(), `${path}: ${await response.text()}`).toBe(true)
      return response.json()
    }
    const context: WorkflowContext = await call(`/workflow-definitions/context?project_id=${fixtures.project.id}`)
    const oldTitle = `Synthetic private legacy ${locale} ${randomUUID().slice(0, 8)}`
    const title = `${oldTitle} structure copy`
    const logic = "Synthetic private prose: a scientist decides whether to repeat. Not an executable condition."
    const base = `airalogy.id.lab.${fixtures.lab.uid}.project.${fixtures.project.uid}.protocol.`
    const protocols = [
      { protocol_index: 1, protocol_name: "Synthetic measurement", airalogy_protocol_id: `${base}${fixtures.analysis.protocol_uid}.v.${context.protocols.find(protocol => protocol.id === fixtures.analysis.protocol_id)!.versions[0].version}` },
      { protocol_index: 2, protocol_name: "Synthetic attachment", airalogy_protocol_id: `${base}${fixtures.workflow_files.protocol_uid}.v.1.0.0` },
    ]
    const legacy = await call("/workflow", { workflow_info: { title: oldTitle, protocols, edges: ["1 -> 2"], logic, default_initial_protocol_index: 1 }, airalogy_protocol_id: protocols[0].airalogy_protocol_id, research_goal: "" })
    expect(legacy.path_data.path_status).toBe("waiting_for_research_goal")
    const before = await call(`/workflow/${legacy.id}`)
    await page.addInitScript(language => localStorage.setItem("lang", JSON.stringify({ data: language, expire: null })), locale)
    const projectPath = `/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}`
    await page.goto(`${projectPath}/workflows`)
    await page.getByTestId("workflow-convert-legacy").click()
    await page.getByTestId("workflow-conversion-source").click()
    const conversionContextResponse = page.waitForResponse(response => response.url().endsWith(`/workflow-conversions/${legacy.id}/context`))
    await selectVisibleOption(page, oldTitle)
    const conversionContext: WorkflowConversionContext = await (await conversionContextResponse).json()
    expect(conversionContext.blockers).toEqual([])
    await page.getByTestId("workflow-conversion-title").locator("input").fill(title)
    await expect(page.getByTestId("workflow-conversion-preview")).toBeDisabled()
    await page.setViewportSize({ width: 390, height: 844 })
    await page.getByTestId("workflow-conversion-dialog").locator("details summary").click()
    await expect(page.getByTestId("workflow-conversion-original-logic")).toHaveText(logic)
    for (const key of ["versions", "structure", "logic"])
      await page.getByTestId(`workflow-conversion-ack-${key}`).click()
    const previewResponse = page.waitForResponse(response => response.url().endsWith(`/workflow-conversions/${legacy.id}/preview`) && response.request().method() === "POST")
    await page.getByTestId("workflow-conversion-preview").click()
    const previewHttp = await previewResponse
    expect(previewHttp.ok(), await previewHttp.text()).toBe(true)
    const preview: WorkflowConversionPreview = await previewHttp.json()
    expect(preview.graph.nodes).toHaveLength(2)
    expect(preview.graph.edges).toHaveLength(1)
    expect(preview.graph.edges[0].condition).toBeNull()
    expect(preview.graph.bindings).toEqual([])
    expect(JSON.stringify(preview.graph)).not.toContain(logic)
    expect(preview.omitted_fields).toEqual(expect.arrayContaining(["logic", "path_data", "records", "initial_values"]))
    await expect(page.getByTestId("workflow-conversion-dialog")).toContainText(locale === "en-US" ? "not executable conditions" : "不是可执行条件")
    await expect.poll(async () => (await page.getByTestId("workflow-conversion-dialog").boundingBox())?.width).toBeLessThanOrEqual(358)
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
    await page.screenshot({ path: testInfo.outputPath(`workflow-legacy-preview-${locale}-phone.png`) })
    const confirmResponse = page.waitForResponse(response => response.url().endsWith(`/workflow-conversions/${legacy.id}/confirm`) && response.request().method() === "POST")
    await page.getByTestId("workflow-conversion-confirm").click()
    const confirmHttp = await confirmResponse
    expect(confirmHttp.ok(), await confirmHttp.text()).toBe(true)
    const converted: WorkflowConversionResult = await confirmHttp.json()
    expect(converted.conversion_receipt_id).toBeTruthy()
    expect(converted.id).not.toBe(legacy.id)
    expect((await call(`/workflow/${legacy.id}`)).path_data).toEqual(before.path_data)
    expect((await call(`/workflow/${legacy.id}`)).workflow_info).toEqual(before.workflow_info)
    const replay = await call(`/workflow-conversions/${legacy.id}/confirm`, confirmHttp.request().postDataJSON())
    expect(replay.id).toBe(converted.id)
    expect(replay.confirmed_revision_id).toBe(converted.confirmed_revision_id)
    await page.getByTestId("workflow-conversion-open").click()
    await expect(page.getByTestId("workflow-card-list").locator("article")).toHaveCount(2)
    await expect(page.getByTestId("workflow-title").locator("input")).toHaveValue(title)
    const saved: WorkflowDefinitionDetail = await call(`/workflow-definitions/${converted.id}`)
    expect(saved.runs).toEqual([])
    expect(JSON.stringify(saved)).not.toContain(logic)
    expect(JSON.stringify(saved)).not.toContain(legacy.id)
    expect(saved.current_revision?.graph).toEqual(preview.graph)
  })

  test(`Protocol file transfer resolves an audited controlled reference before downstream approval (${locale})`, async ({ page, request }, testInfo) => {
    test.setTimeout(180_000)
    const fixtures = await loadFixtures()
    const seed = fixtures.workflow_files
    const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
    const signIn = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
    expect(signIn.ok()).toBe(true)
    const headers = { "Auth-Token": (await signIn.json()).token }
    async function call(path: string, data?: unknown) {
      const response = await request.fetch(`${api}${path}`, { method: data === undefined ? "GET" : "POST", headers, data })
      expect(response.ok(), `${path}: ${await response.text()}`).toBe(true)
      return response.json()
    }
    const title = `Synthetic safe file workflow ${locale} ${randomUUID().slice(0, 8)}`
    const projectPath = `/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}`
    await page.addInitScript(language => localStorage.setItem("lang", JSON.stringify({ data: language, expire: null })), locale)
    const contextResponse = page.waitForResponse(response => response.url().includes("/workflow-definitions/context?") && response.ok())
    await page.goto(`${projectPath}/workflows`)
    const context: WorkflowContext = await (await contextResponse).json()
    const protocol = context.protocols.find(protocol => protocol.id === seed.protocol_id)!
    const fileField = protocol.versions.find(version => version.id === seed.protocol_version_id)!.fields!.find(field => field.value_type === "file" && field.path[1] === seed.field) as WorkflowFileField
    expect(fileField).toBeTruthy()
    const fileFieldLabel = `${fileField.title} (${fileField.file_extensions?.join(", ") || "*"})`
    expect(protocol.versions[0].fields).toEqual(expect.arrayContaining([expect.objectContaining({ path: ["var", seed.field], value_type: "file", file_extensions: ["csv"] })]))
    await page.getByTestId("workflow-title").locator("input").fill(title)
    await page.getByTestId("workflow-add-protocol").click()
    await selectVisibleOption(page, protocol.name)
    await page.getByTestId("workflow-add-card").click()
    await page.getByTestId("workflow-card-title").locator("input").fill("Submit source CSV")
    await page.getByTestId("workflow-view-list").click()
    const cards = page.getByTestId("workflow-card-list").locator("article")
    const sourceId = (await cards.first().getAttribute("data-node-id"))!
    await page.getByTestId("workflow-duplicate-card").click()
    await page.getByTestId("workflow-card-title").locator("input").fill("Review controlled CSV")
    const targetId = (await cards.last().getAttribute("data-node-id"))!
    await page.getByTestId("workflow-card-dependencies").click()
    await selectVisibleOption(page, "1. Submit source CSV")
    await page.keyboard.press("Escape")
    await page.getByTestId("workflow-binding-source-card").click()
    await selectVisibleOption(page, "Submit source CSV")
    await page.getByTestId("workflow-binding-source-field").click()
    await selectVisibleOption(page, fileFieldLabel)
    await page.getByTestId("workflow-binding-target-field").click()
    await selectVisibleOption(page, fileFieldLabel)
    await page.getByTestId("workflow-binding-add").click()
    await page.setViewportSize({ width: 390, height: 844 })
    const savePreviewResponse = page.waitForResponse(response => response.url().endsWith("/workflow-definitions/preview") && response.request().method() === "POST")
    await page.getByTestId("workflow-preview-save").click()
    const preview: WorkflowSavePreview = await (await savePreviewResponse).json()
    expect(preview.graph.schema_version).toBe(4)
    expect(preview.graph.bindings[0]).toMatchObject({ value_type: "file", source_path: ["var", seed.field], target_path: ["var", seed.field], unit: null })
    await expect(page.getByTestId("workflow-file-binding-preview")).toBeVisible()
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
    await page.screenshot({ path: testInfo.outputPath(`workflow-file-preview-${locale}-phone.png`) })
    const saveResponse = page.waitForResponse(response => response.url().endsWith("/workflow-definitions/confirm") && response.request().method() === "POST")
    await page.getByTestId("workflow-confirm-save").click()
    const saved: WorkflowDefinitionDetail = await (await saveResponse).json()
    await expect(page.getByTestId("workflow-result")).toContainText(title)
    const taskDraft = { project_id: fixtures.project.id, title: `${title} Task`, goal: "Review one explicit synthetic CSV reference", success_criteria: ["The actual file receipt is visible before downstream approval"], protocol_ids: [protocol.id] }
    const taskPreview = await call("/research-tasks/preview", taskDraft)
    const task = await call("/research-tasks", { ...taskDraft, preview_digest: taskPreview.preview_digest })
    await page.getByTestId("workflow-open-run").click()
    await page.getByTestId("workflow-task").click()
    await selectVisibleOption(page, taskDraft.title)
    await page.getByTestId("workflow-preview-run").click()
    await page.getByTestId("workflow-confirm-run").click()
    await expect(page).toHaveURL(new RegExp(`/research/tasks/${task.id}$`))
    async function readAction(id: string): Promise<ResearchAction> {
      return (await call(`/research-tasks/${task.id}`)).actions.find((action: ResearchAction) => action.input_data.action_graph?.node_id === id)
    }
    const source = await readAction(sourceId)
    await call(`/research-approvals/${source.approval!.id}/approve`, { expected_revision: source.approval!.revision, expected_action_revision: source.revision, preview_digest: source.approval!.preview_digest })
    const work = (await readAction(sourceId)).work_item!
    await call(`/research-work-items/${work.id}/submit`, { expected_revision: work.revision, record_id: seed.record_id, record_version: seed.record_version, note: "Synthetic CSV fixture; no physical experiment performed." })
    const target = await readAction(targetId)
    expect(target.approval?.status).toBe("pending")
    const alias = (target.input_data.initial_values as Record<string, unknown>)[seed.field]
    expect(alias).toBeTruthy()
    expect(alias).not.toBe(seed.file_ref)
    await page.reload()
    const approval = page.locator("#research-approvals article").filter({ has: page.getByRole("heading", { name: target.title, exact: true }) })
    await expect(approval.getByTestId("workflow-resolved-file")).toContainText("synthetic-measurements.csv")
    await expect(approval.getByTestId("workflow-resolved-file")).toContainText("text/csv")
    await expect(approval.getByTestId("workflow-resolved-file")).toContainText("SHA-256")
    await expect(approval.getByTestId("workflow-resolution-summary")).toContainText(seed.record_id)
    await approval.getByTestId("workflow-resolved-file").scrollIntoViewIfNeeded()
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
    await page.screenshot({ path: testInfo.outputPath(`workflow-file-approval-${locale}-phone.png`) })
    await approval.getByRole("button", { name: locale === "en-US" ? "Approve Action" : "批准 Action", exact: true }).click()
    const approvalResponse = page.waitForResponse(response => response.url().endsWith(`/research-approvals/${target.approval!.id}/approve`) && response.request().method() === "POST")
    await page.getByRole("button", { name: locale === "en-US" ? "Confirm approval" : "确认批准", exact: true }).click()
    expect((await approvalResponse).ok()).toBe(true)
    const approved = await readAction(targetId)
    expect(approved.work_item?.status).toBe("open")
    expect(approved.protocol_run?.initial_values?.[seed.field]).toBe(alias)
    expect((await call(`/workflow-definitions/${saved.id}`)).current_revision.graph).toEqual(preview.graph)
  })
}
