import type { Locator, Page } from "@playwright/test"
import type { AnalysisPipeline, AnalysisSelection } from "../../../apps/web/src/service/api/analysis"
import type { AnalysisComputeContext, AnalysisComputeDetail, AnalysisComputeInputFile, AnalysisComputeInputFilesEnvelope, AnalysisComputePreview } from "../../../apps/web/src/service/api/analysis-compute"
import type { ResearchAction, ResearchTaskDetail } from "../../../apps/web/src/service/api/research-tasks"
import type { WorkflowAnalysisPublication, WorkflowAnalysisPublicationPreview } from "../../../apps/web/src/service/api/workflow-analysis-methods"
import type { WorkflowContext, WorkflowDefinitionDetail } from "../../../apps/web/src/service/api/workflow-definitions"
import { randomUUID } from "node:crypto"
import { expect, test } from "@playwright/test"
import { loadFixtures, selectVisibleOption } from "./fixtures"

// Real fixture API, stored CSVs/Records, immutable method publication and actual
// approvals. The authorized synthetic Runner stays offline: this verifies input
// preparation and queueing, not code execution or a scientific result.
for (const locale of ["en-US", "zh-CN"] as const) {
  test(`Explicit Record attachment inputs survive method publication and require exact downstream approval (${locale})`, async ({ page, request }, testInfo) => {
    test.setTimeout(240_000)
    const fixtures = await loadFixtures()
    const seed = fixtures.workflow_compute_attachments
    const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
    const signedIn = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
    expect(signedIn.ok()).toBe(true)
    const headers = { "Auth-Token": (await signedIn.json()).token }
    async function call(path: string, data?: unknown) {
      const response = await request.fetch(`${api}${path}`, { method: data === undefined ? "GET" : "POST", headers, data })
      expect(response.ok(), `${path}: ${await response.text()}`).toBe(true)
      return response.json()
    }
    let method: AnalysisPipeline = await call(`/analysis-pipelines/${seed.pipeline_id}`)
    const original = method.revisions!.find(revision => revision.revision === 1)!
    expect(original.recipe).not.toHaveProperty("input_files")
    expect(original.source_selection.records).toHaveLength(2)
    const sources = original.source_selection.records!
    // The language cases share one synthetic fixture. Restore through a new
    // ordinary revision, never mutate its sealed original or invent a Run.
    if ("input_files" in method.current_recipe) {
      await call(`/analysis-pipelines/${seed.pipeline_id}/revisions`, { recipe: original.recipe, expected_revision: method.current_revision, source_selection: original.source_selection })
      method = await call(`/analysis-pipelines/${seed.pipeline_id}`)
    }
    const originalRevision = method.current_revision
    const declarations: AnalysisComputeInputFile[] = [{ input_id: "measurements", field_path: ["var", fixtures.workflow_files.field] }]
    const title = `Synthetic explicit attachment method ${locale} ${randomUUID().slice(0, 8)}`
    const projectPath = `/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}`
    await page.addInitScript(language => localStorage.setItem("lang", JSON.stringify({ data: language, expire: null })), locale)
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto(`${projectPath}/analysis?protocolId=${seed.protocol_id}`)
    const contextResponse = page.waitForResponse(response => response.url().endsWith(`/protocols/${seed.protocol_id}/analysis-compute-context`) && (response.request().postDataJSON() as AnalysisSelection)?.records?.length === 2)
    await page.getByTestId("analysis-pipeline-item").filter({ hasText: seed.pipeline_title }).click()
    const contextHttp = await contextResponse
    expect(contextHttp.ok(), await contextHttp.text()).toBe(true)
    const context: AnalysisComputeContext = await contextHttp.json()
    const field = context.input_file_fields!.find(field => field.field_path[1] === fixtures.workflow_files.field)!
    expect(context.input_file_limits).toMatchObject({ max_files: 30, manifest_filename: "attachments.json" })
    expect(context.source.record_count).toBe(2)
    const approver = context.approvers.find(person => person.id === method.created_by_user_id)!
    expect(approver).toBeTruthy()
    await page.getByTestId("analysis-compute-approver").click()
    await selectVisibleOption(page, approver.name)
    await expect(page.getByTestId("analysis-compute-no-inputs")).toBeVisible()
    await expect(page.getByTestId("analysis-compute-input-declaration")).toHaveCount(0)
    await page.getByTestId("analysis-compute-add-input").click()
    await page.getByTestId("analysis-compute-input-id").locator("input").fill("measurements")
    await page.getByTestId("analysis-compute-input-field").click()
    await selectVisibleOption(page, `${field.title} [${field.field_path[1]}] (${field.file_extensions?.join(", ") || "*"})`)
    await expect(page.getByTestId("analysis-compute-input-count")).toContainText("2")
    await expect(page.getByTestId("analysis-compute-preview")).toBeDisabled()
    const revisionResponse = page.waitForResponse(response => response.url().endsWith(`/analysis-pipelines/${seed.pipeline_id}/revisions`) && response.request().method() === "POST")
    await page.getByTestId("analysis-compute-save-revision").click()
    await page.getByRole("button", { name: locale === "en-US" ? "Confirm" : "确认", exact: true }).click()
    const revisionHttp = await revisionResponse
    expect(revisionHttp.ok(), await revisionHttp.text()).toBe(true)
    expect(revisionHttp.request().postDataJSON().recipe.input_files).toEqual(declarations)
    await expect(page.getByTestId("analysis-compute-input-id").locator("input")).toHaveValue("measurements")
    await expect(page.getByTestId("analysis-compute-preview")).toBeEnabled()
    const savedMethod: AnalysisPipeline = await call(`/analysis-pipelines/${seed.pipeline_id}`)
    expect(savedMethod.current_revision).toBe(originalRevision + 1)
    expect(savedMethod.revisions!.find(revision => revision.revision === 1)!.recipe).toEqual(original.recipe)
    expect(savedMethod.current_recipe).toHaveProperty("input_files", declarations)

    const previewResponse = page.waitForResponse(response => response.url().endsWith("/analyses/compute/preview") && response.request().method() === "POST")
    await page.getByTestId("analysis-compute-preview").click()
    const previewHttp = await previewResponse
    expect(previewHttp.ok(), await previewHttp.text()).toBe(true)
    const preview: AnalysisComputePreview = await previewHttp.json()
    const receipt: AnalysisComputeInputFilesEnvelope = preview.summary.compute.input_files!
    expect(receipt).toMatchObject({ count: 2, manifest: { filename: "attachments.json" } })
    expect(receipt.files.map(file => `${file.record_id}:${file.record_version}`).sort()).toEqual(sources.map(record => `${record.id}:${record.version}`).sort())
    expect(new Set(receipt.files.map(file => file.mount_name)).size).toBe(2)
    expect(receipt.total_bytes).toBe(receipt.files.reduce((total, file) => total + file.byte_size, 0))
    for (const file of receipt.files) {
      expect(file).toMatchObject({ input_id: "measurements", field_path: declarations[0].field_path, media_type: "text/csv" })
      expect(file.checksum_sha256).toMatch(/^[a-f0-9]{64}$/)
      expect(file).not.toHaveProperty("storage_key")
      expect(file).not.toHaveProperty("url")
    }
    const previewDialog = page.getByTestId("analysis-compute-preview-dialog")
    await expect(previewDialog.getByTestId("analysis-compute-input-file")).toHaveCount(2)
    for (const file of receipt.files) {
      const card = previewDialog.getByTestId("analysis-compute-input-file").filter({ hasText: file.record_id })
      await expect(card).toContainText(file.filename)
      await expect(card).toContainText(file.checksum_sha256)
      await expect(card).toContainText(`AIRALOGY_INPUT_DIR/${file.mount_name}`)
    }
    await previewDialog.getByTestId("analysis-compute-input-receipt").scrollIntoViewIfNeeded()
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
    await waitForUnobstructedCapture(page, previewDialog)
    await page.screenshot({ path: testInfo.outputPath(`compute-attachment-preview-${locale}-phone.png`) })
    const confirmResponse = page.waitForResponse(response => response.url().endsWith("/analyses/compute") && response.request().method() === "POST")
    await page.getByTestId("analysis-compute-confirm").click()
    const confirmHttp = await confirmResponse
    expect(confirmHttp.ok(), await confirmHttp.text()).toBe(true)
    const run = await confirmHttp.json()
    const report = page.getByTestId("analysis-compute-report")
    await expect(report.getByTestId("analysis-compute-input-file")).toHaveCount(2)
    await expect(page.getByTestId("analysis-compute-approve")).toBeDisabled()
    await page.getByTestId("analysis-compute-reviewed").click()
    await page.getByTestId("analysis-compute-approve").click()
    await page.getByTestId("analysis-compute-reason").locator("textarea").fill("Reviewed two explicit synthetic CSV inputs; queue only, no running fixture Runner.")
    const decisionResponse = page.waitForResponse(response => response.url().endsWith(`/analyses/${run.id}/compute-approval`) && response.request().method() === "POST")
    await page.getByTestId("analysis-compute-confirm-decision").click()
    expect((await decisionResponse).ok()).toBe(true)
    const queued: AnalysisComputeDetail = await call(`/analyses/${run.id}/compute`)
    expect(queued.job.status).toBe("queued")
    expect(queued.contract.input_files).toEqual(receipt)
    // Close the real queued request; this test has no executable Runner.
    await call(`/analyses/${run.id}/compute-cancel`, { expected_revision: queued.job.revision, contract_digest: queued.approval.contract_digest, reason: "End synthetic browser acceptance without executing code." })

    await page.goto(`${projectPath}/analysis?protocolId=${seed.protocol_id}`)
    const savedRow = page.locator("article").filter({ has: page.getByTestId("analysis-pipeline-item").filter({ hasText: seed.pipeline_title }) })
    await savedRow.getByTestId("analysis-publish-method").click()
    await page.getByTestId("analysis-method-publish-title").locator("input").fill(title)
    const publicationPreviewResponse = page.waitForResponse(response => response.url().endsWith("/workflow-analysis-methods/preview") && response.request().method() === "POST")
    await page.getByTestId("analysis-method-preview-publication").click()
    const publicationPreviewHttp = await publicationPreviewResponse
    expect(publicationPreviewHttp.ok(), await publicationPreviewHttp.text()).toBe(true)
    const publicationPreview: WorkflowAnalysisPublicationPreview = await publicationPreviewHttp.json()
    expect(publicationPreview.publication.recipe).toHaveProperty("input_files", declarations)
    for (const file of receipt.files) {
      expect(JSON.stringify(publicationPreview.publication)).not.toContain(file.file_id)
      expect(JSON.stringify(publicationPreview.publication)).not.toContain(file.record_id)
    }
    const publicationDialog = page.getByTestId("analysis-method-publish-dialog")
    await expect(publicationDialog.getByTestId("analysis-compute-input-declarations")).toContainText("measurements")
    await expect(publicationDialog.getByTestId("analysis-compute-input-receipt")).toHaveCount(0)
    await expect(page.getByTestId("analysis-method-confirm-publication")).toBeDisabled()
    await publicationDialog.getByTestId("analysis-compute-input-declarations").scrollIntoViewIfNeeded()
    await waitForUnobstructedCapture(page, publicationDialog)
    await page.screenshot({ path: testInfo.outputPath(`compute-attachment-publication-${locale}-phone.png`) })
    await page.getByTestId("analysis-method-publish-reviewed").click()
    const publicationResponse = page.waitForResponse(response => response.url().endsWith("/workflow-analysis-methods/confirm") && response.request().method() === "POST")
    await page.getByTestId("analysis-method-confirm-publication").click()
    const publicationHttp = await publicationResponse
    expect(publicationHttp.ok(), await publicationHttp.text()).toBe(true)
    const publication: WorkflowAnalysisPublication = await publicationHttp.json()
    await publicationDialog.getByRole("button", { name: locale === "en-US" ? "Close" : "关闭", exact: true }).click()

    const workflowContextResponse = page.waitForResponse(response => response.url().includes("/workflow-definitions/context?") && response.ok())
    await page.goto(`${projectPath}/workflows`)
    const workflowContext: WorkflowContext = await (await workflowContextResponse).json()
    const protocol = workflowContext.protocols.find(protocol => protocol.id === seed.protocol_id)!
    await page.getByTestId("workflow-title").locator("input").fill(title)
    await page.getByTestId("workflow-add-protocol").click()
    await selectVisibleOption(page, protocol.name)
    const cards = page.getByTestId("workflow-card-list").locator("article")
    const sourceNodeIds: string[] = []
    for (const [index] of sources.entries()) {
      await page.getByTestId("workflow-add-card").click()
      await page.getByTestId("workflow-card-title").locator("input").fill(`Submit CSV ${index + 1}`)
      sourceNodeIds.push((await cards.last().getAttribute("data-node-id"))!)
    }
    await page.getByTestId("workflow-card-kind").locator("input[value=\"analysis\"]").check()
    await page.getByTestId("workflow-add-analysis-method").click()
    await selectVisibleOption(page, title)
    await page.getByTestId("workflow-add-analysis-card").click()
    await page.getByTestId("workflow-card-title").locator("input").fill("Review exact submitted CSV inputs")
    const analysisNodeId = (await cards.last().getAttribute("data-node-id"))!
    await page.getByTestId("workflow-card-dependencies").click()
    for (const [index] of sources.entries())
      await selectVisibleOption(page, `${index + 1}. Submit CSV ${index + 1}`)
    await page.keyboard.press("Escape")
    await page.getByTestId("workflow-analysis-sources").click()
    for (const [index] of sources.entries())
      await selectVisibleOption(page, `Submit CSV ${index + 1}`)
    await page.keyboard.press("Escape")
    await expect(page.getByTestId("workflow-analysis-settings").getByTestId("analysis-compute-input-declarations")).toContainText("measurements")
    await expect(page.getByTestId("workflow-analysis-settings").getByTestId("analysis-compute-input-field")).toHaveCount(0)
    await page.getByTestId("workflow-preview-save").click()
    const savedResponse = page.waitForResponse(response => response.url().endsWith("/workflow-definitions/confirm") && response.request().method() === "POST")
    await page.getByTestId("workflow-confirm-save").click()
    const savedHttp = await savedResponse
    expect(savedHttp.ok(), await savedHttp.text()).toBe(true)
    const saved: WorkflowDefinitionDetail = await savedHttp.json()
    expect(saved.current_revision!.graph.nodes.find(node => node.node_id === analysisNodeId)).toMatchObject({ method_publication_id: publication.id })
    expect(JSON.stringify(saved.current_revision!.graph)).not.toContain(receipt.files[0].file_id)
    const taskDraft = { project_id: fixtures.project.id, title: `${title} Task`, goal: "Review two explicitly supplied synthetic attachments", success_criteria: ["Exact input receipt is approved before dispatch"], protocol_ids: [protocol.id], compute_environment_revision_ids: [seed.environment_revision_id], budget_limit: "2", budget_currency: "USD" }
    const taskPreview = await call("/research-tasks/preview", taskDraft)
    const task: ResearchTaskDetail = await call("/research-tasks", { ...taskDraft, preview_digest: taskPreview.preview_digest })
    await page.getByTestId("workflow-open-run").click()
    await page.getByTestId("workflow-task").click()
    await selectVisibleOption(page, taskDraft.title)
    await page.getByTestId("workflow-preview-run").click()
    await page.getByTestId("workflow-confirm-run").click()
    await expect(page).toHaveURL(new RegExp(`/research/tasks/${task.id}$`))
    async function actionFor(nodeId: string): Promise<ResearchAction> {
      return (await call(`/research-tasks/${task.id}`)).actions.find((action: ResearchAction) => action.input_data.action_graph?.node_id === nodeId)
    }
    for (const [index, nodeId] of sourceNodeIds.entries()) {
      const action = await actionFor(nodeId)
      await call(`/research-approvals/${action.approval!.id}/approve`, { expected_revision: action.approval!.revision, expected_action_revision: action.revision, preview_digest: action.approval!.preview_digest })
      const work = (await actionFor(nodeId)).work_item!
      await call(`/research-work-items/${work.id}/submit`, { expected_revision: work.revision, record_id: sources[index].id, record_version: sources[index].version, note: "Synthetic stored CSV for browser input preparation; no physical experiment performed." })
    }
    const actualAnalysis = await actionFor(analysisNodeId)
    expect(actualAnalysis.approval?.status).toBe("pending")
    expect(actualAnalysis.analysis_run?.compute?.input_files?.files.map(file => file.record_id).sort()).toEqual(sources.map(source => source.id).sort())
    await page.reload()
    const approvalCard = page.locator("#research-approvals article").filter({ has: page.getByRole("heading", { name: actualAnalysis.title, exact: true }) })
    await expect(approvalCard.getByTestId("analysis-compute-input-file")).toHaveCount(2)
    await approvalCard.getByTestId("analysis-compute-input-receipt").scrollIntoViewIfNeeded()
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
    await waitForUnobstructedCapture(page, approvalCard)
    await page.screenshot({ path: testInfo.outputPath(`workflow-attachment-approval-${locale}-phone.png`) })
    await approvalCard.getByRole("button", { name: locale === "en-US" ? "Approve Action" : "批准 Action", exact: true }).click()
    const approvalResponse = page.waitForResponse(response => response.url().endsWith(`/research-approvals/${actualAnalysis.approval!.id}/approve`) && response.request().method() === "POST")
    await page.getByRole("button", { name: locale === "en-US" ? "Confirm approval" : "确认批准", exact: true }).click()
    const approvalHttp = await approvalResponse
    expect(approvalHttp.ok(), await approvalHttp.text()).toBe(true)
    const approved = await actionFor(analysisNodeId)
    expect(approved.analysis_run?.compute_job?.status).toBe("queued")
    expect(approved.analysis_run?.compute?.input_files).toEqual(actualAnalysis.analysis_run!.compute!.input_files)
  })
}

async function waitForUnobstructedCapture(page: Page, surface: Locator) {
  // Loading the method and saving a revision each show a real scope notice.
  // Let those notices expire naturally; do not hide them or disable transitions.
  await expect(page.locator(".n-message")).toHaveCount(0, { timeout: 10_000 })
  await expect(surface).toBeVisible()
  await expect.poll(() => surface.evaluate((element) => {
    for (let node: Element | null = element; node; node = node.parentElement) {
      if (getComputedStyle(node).opacity !== "1" || node.getAnimations().some(animation => animation.playState === "running" || animation.pending))
        return false
    }
    return true
  })).toBe(true)
}
