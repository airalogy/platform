import type { AnalysisPublication, AnalysisPublicationPreview } from "../../../apps/web/src/service/api/analysis-publications"
import type { ProjectAnalysisRun } from "../../../apps/web/src/service/api/project-analysis"
import { randomUUID } from "node:crypto"
import { readFile } from "node:fs/promises"
import { expect, test } from "@playwright/test"
import { loadFixtures, selectVisibleOption } from "./fixtures"

// Setup creates real analysis jobs over submitted synthetic Records. Every
// publication, Evidence review and Knowledge write below uses ordinary UI/API.
for (const locale of ["en-US", "zh-CN"] as const) {
  test(`selected computed results become reviewed evidence and Knowledge (${locale}, AI off, phone)`, async ({ page, request }, testInfo) => {
    test.setTimeout(180_000)
    page.setDefaultTimeout(15_000)
    const messages = JSON.parse(await readFile(new URL(`../../../packages/shared/src/locales/langs/${locale === "en-US" ? "en-us" : "zh-cn"}.json`, import.meta.url), "utf8"))
    const text = messages.page
    const fixtures = await loadFixtures()
    const sources = fixtures.project_analysis.inputs
    const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
    const signedIn = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
    expect(signedIn.ok()).toBe(true)
    const headers = { "Auth-Token": (await signedIn.json()).token }
    async function call(path: string, data?: unknown) {
      const response = await request.fetch(`${api}${path}`, { method: data === undefined ? "GET" : "POST", headers, data })
      expect(response.ok(), `${path}: ${await response.text()}`).toBe(true)
      return response.json()
    }
    expect((await call("/instance")).ai_enabled).toBe(false)
    const unique = randomUUID().slice(0, 8)
    const title = `Synthetic evidence ${locale} ${unique}`
    const summary = `Synthetic computed comparison ${unique}; no causal conclusion.`
    const taskDraft = { project_id: fixtures.project.id, title: `${title} Task`, goal: "Review known synthetic observations without pooling unlike measurements.", success_criteria: ["Evidence and Knowledge retain both source versions."] }
    const taskPreview = await call("/research-tasks/preview", taskDraft)
    const task = await call("/research-tasks", { ...taskDraft, preview_digest: taskPreview.preview_digest })
    const analysisPreview = await call("/analyses/project/preview", {
      project_id: fixtures.project.id,
      question: `Private analysis purpose not shared ${unique}`,
      selection: { inputs: sources.map((source, index) => ({ slot_id: `source_${index}`, protocol_id: source.protocol_id, selection: { mode: "latest" } })) },
      recipe: {
        mode: "evidence_synthesis",
        slots: sources.map((source, index) => ({ slot_id: `source_${index}`, label: `Synthetic ${source.value_field}`, recipe: { numeric_fields: [source.value_field], group_by: [], chart: "none" } })),
      },
    })
    const queued = await call("/analyses/project", { preview_id: analysisPreview.id, preview_digest: analysisPreview.preview_digest, client_idempotency_key: `publication-e2e-${unique}` })
    let run: ProjectAnalysisRun
    await expect.poll(async () => {
      run = await call(`/analyses/${queued.id}`)
      return run.status
    }, { timeout: 40_000 }).toBe("succeeded")
    expect(run!.result!.local_results[0].report.groups[0].fields[sources[0].value_field].mean).toBe(4)
    await page.addInitScript(language => localStorage.setItem("lang", JSON.stringify({ data: language, expire: null })), locale)
    await page.setViewportSize({ width: 390, height: 844 })
    const errors: string[] = []
    page.on("pageerror", error => errors.push(error.message))
    await page.goto(`/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}/analysis?scope=project&runId=${queued.id}`)
    await page.getByTestId("analysis-publication-open").click()
    const modal = page.getByTestId("analysis-publication-dialog")
    await expect(modal).toBeVisible()
    await page.getByTestId("analysis-publication-task").click()
    await selectVisibleOption(page, taskDraft.title)
    await page.getByTestId("analysis-publication-name").locator("input").fill(title)
    await page.getByTestId("analysis-publication-summary").locator("textarea").fill(summary)
    const previewResponse = page.waitForResponse(response => response.url().endsWith(`/analyses/${queued.id}/evidence-publications/preview`) && response.request().method() === "POST")
    await page.getByTestId("analysis-publication-preview").click()
    const previewHttp = await previewResponse
    expect(previewHttp.ok(), await previewHttp.text()).toBe(true)
    const preview: AnalysisPublicationPreview = await previewHttp.json()
    expect(preview.effect).toMatchObject({ quality_state: "pending", raw_records_shared: false, original_report_remains_private: true })
    expect(JSON.stringify(preview.publication)).not.toContain(`Private analysis purpose not shared ${unique}`)
    expect(preview.publication.sections).toHaveLength(2)
    await expect(modal.getByTestId("analysis-result-table")).toHaveCount(2)
    await expect(page.getByTestId("analysis-publication-destination")).toContainText(taskDraft.title)
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
    await page.screenshot({ path: testInfo.outputPath(`analysis-publication-${locale}-preview.png`) })
    let lostPublicationId: string | undefined
    let lostConfirmationKey: string | undefined
    if (locale === "en-US") {
      const publicationUrl = `**/api/analyses/${queued.id}/evidence-publications`
      // Lose delivery only after the real server commits. Recovery must reuse
      // the request identity, not create a duplicate Evidence asset.
      await page.route(publicationUrl, async (route) => {
        if (!lostPublicationId) {
          const response = await route.fetch()
          expect(response.ok(), await response.text()).toBe(true)
          lostPublicationId = (await response.json()).publication.id
          lostConfirmationKey = route.request().postDataJSON().client_idempotency_key
        }
        await route.abort("failed")
      })
      await page.getByTestId("analysis-publication-confirm").click()
      await expect(modal).toContainText(text.analysisPublication.confirmError)
      await page.unroute(publicationUrl)
    }
    const savedResponse = page.waitForResponse(response => response.url().endsWith(`/analyses/${queued.id}/evidence-publications`) && response.request().method() === "POST")
    await page.getByTestId("analysis-publication-confirm").click()
    const savedHttp = await savedResponse
    expect(savedHttp.ok(), await savedHttp.text()).toBe(true)
    const saved: { publication: AnalysisPublication, evidence: { id: string, quality_state: string } } = await savedHttp.json()
    if (lostPublicationId) {
      expect(saved.publication.id).toBe(lostPublicationId)
      expect(savedHttp.request().postDataJSON().client_idempotency_key).toBe(lostConfirmationKey)
      const bundle = await call(`/research-assets/tasks/${task.id}`)
      expect(bundle.evidence.filter((item: { artifact_id: string }) => item.artifact_id === lostPublicationId)).toHaveLength(1)
    }
    expect(saved.evidence.quality_state).toBe("pending")
    await expect(page.getByTestId("analysis-publication-saved")).toContainText(title)
    await page.getByRole("button", { name: text.analysisPublication.openTask, exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`/research/tasks/${task.id}$`))
    await page.reload()
    const assets = page.locator(".research-assets-panel")
    await assets.locator(".n-tabs-tab").filter({ hasText: text.research.evidence }).click()
    const evidence = assets.locator("article").filter({ hasText: summary })
    await expect(evidence).toContainText(text.research.evidenceQuality.pending)
    await evidence.locator(".n-collapse-item__header").click()
    await expect(evidence.getByTestId("analysis-result-table")).toHaveCount(2)
    const acceptedResponse = page.waitForResponse(response => response.url().endsWith(`/research-assets/evidence/${saved.evidence.id}/review`) && response.request().method() === "POST")
    await evidence.getByRole("button", { name: text.research.validateEvidence, exact: true }).click()
    await page.getByRole("dialog").getByRole("button", { name: messages.common.confirm, exact: true }).click()
    expect((await acceptedResponse).ok()).toBe(true)
    await expect(evidence).toContainText(text.research.evidenceQuality.validated)
    await assets.getByRole("button", { name: text.research.suggestKnowledge, exact: true }).click()
    const knowledgeDialog = page.getByRole("dialog")
    await knowledgeDialog.locator(".n-form-item").filter({ hasText: text.knowledge.knowledgeTitle }).locator("input").fill(`${title} Knowledge`)
    await knowledgeDialog.locator("textarea").fill(`Synthetic knowledge ${unique}. The computed observations are not a causal finding.`)
    await knowledgeDialog.locator(".n-form-item").filter({ hasText: text.research.validatedEvidence }).locator(".n-select").click()
    await selectVisibleOption(page, summary)
    await page.keyboard.press("Escape")
    await knowledgeDialog.getByRole("button", { name: text.research.previewAssetWrite, exact: true }).click()
    const knowledgeResponse = page.waitForResponse(response => response.url().endsWith("/research-assets/knowledge-suggestions") && response.request().method() === "POST")
    await knowledgeDialog.getByRole("button", { name: text.research.confirmAssetWrite, exact: true }).click()
    const knowledgeHttp = await knowledgeResponse
    expect(knowledgeHttp.ok(), await knowledgeHttp.text()).toBe(true)
    const note = await knowledgeHttp.json()
    expect(note.state).toBe("suggested")
    expect(note.evidence.map((link: { evidence_id: string }) => link.evidence_id)).toEqual([saved.evidence.id])
    // Complete the separate organizational review through the normal UI, not
    // just a direct API call. Database tests also cover a distinct reviewer.
    await assets.locator(".n-tabs-tab").filter({ hasText: text.research.knowledgeCandidates }).click()
    const candidate = assets.locator("article").filter({ hasText: `${title} Knowledge` })
    await candidate.getByRole("button", { name: text.research.openProjectKnowledge, exact: true }).click()
    await expect(page).toHaveURL(/\/knowledge\?view=items$/)
    const libraryItem = page.locator(".knowledge-page article").filter({ hasText: `${title} Knowledge` })
    await expect(libraryItem).toBeVisible()
    await libraryItem.locator(".n-collapse-item__header").click()
    const provenance = libraryItem.locator(".knowledge-evidence-source")
    await expect(provenance).toContainText(text.research.artifactType.analysis_publication)
    await expect(provenance).toContainText("SHA-256")
    await expect(provenance).not.toContainText(text.research.artifactType.data_asset)
    const reviewedResponse = page.waitForResponse(response => response.url().endsWith(`/knowledge/items/${note.id}/review`) && response.request().method() === "POST")
    await libraryItem.getByRole("button", { name: text.knowledge.review, exact: true }).click()
    await page.getByRole("dialog").getByRole("button", { name: text.knowledge.review, exact: true }).click()
    const reviewedHttp = await reviewedResponse
    expect(reviewedHttp.ok(), await reviewedHttp.text()).toBe(true)
    const reviewed = await reviewedHttp.json()
    expect(reviewed.state).toBe("reviewed")
    await expect(libraryItem).toContainText(text.knowledge.stateReviewed)
    await expect(page.getByRole("dialog")).toBeHidden()
    await libraryItem.scrollIntoViewIfNeeded()
    await page.screenshot({ path: testInfo.outputPath(`analysis-publication-${locale}-knowledge-review.png`) })
    await page.goto(`/research/tasks/${task.id}`)
    const reloadedTask = page.waitForResponse(response => response.url().endsWith(`/research-tasks/${task.id}`) && response.request().method() === "GET")
    await page.reload()
    const taskHttp = await reloadedTask
    expect(taskHttp.ok(), await taskHttp.text()).toBe(true)
    await assets.locator(".n-tabs-tab").filter({ hasText: text.research.knowledgeCandidates }).click()
    const knowledgeCard = assets.locator("article").filter({ hasText: `${title} Knowledge` })
    await expect(knowledgeCard.getByRole("heading", { name: `${title} Knowledge`, exact: true })).toBeVisible()
    await expect(knowledgeCard).toContainText(`Synthetic knowledge ${unique}`)
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
    await knowledgeCard.scrollIntoViewIfNeeded()
    await page.screenshot({ path: testInfo.outputPath(`analysis-publication-${locale}-knowledge.png`) })
    expect((await call(`/research-assets/analysis-publications/${saved.publication.id}`)).snapshot).toEqual(preview.publication)
    expect((await call(`/analyses/${queued.id}`)).result_digest).toBe(run!.result_digest)
    expect(errors).toEqual([])
  })
}
