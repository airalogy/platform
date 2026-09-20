import type { Locator, Page } from "@playwright/test"
import type { ProjectAnalysisComparison, ProjectAnalysisContext, ProjectAnalysisPipeline, ProjectAnalysisPreview, ProjectAnalysisRun, ProjectInterpretationRevision } from "../../../apps/web/src/service/api/project-analysis"
import { randomUUID } from "node:crypto"
import { readFile } from "node:fs/promises"
import { expect, test } from "@playwright/test"
import { loadFixtures, selectVisibleOption } from "./fixtures"

// Real submitted Records, deterministic worker, private methods, exact-source
// interpretation revisions and downloads. No model or analysis route mocks.
for (const locale of ["en-US", "zh-CN"] as const) {
  for (const mode of ["evidence_synthesis", "relational"] as const) {
    test(`Project ${mode} preserves exact sources, reviewed methods and independent evidence (${locale})`, async ({ page, request }, testInfo) => {
      test.setTimeout(240_000)
      page.setDefaultTimeout(15_000)
      const pageErrors: string[] = []
      page.on("pageerror", error => pageErrors.push(error.message))
      const fixtures = await loadFixtures()
      const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
      const signedIn = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
      expect(signedIn.ok()).toBe(true)
      const headers = { "Auth-Token": (await signedIn.json()).token }
      async function get(path: string) {
        const response = await request.get(`${api}${path}`, { headers })
        expect(response.ok(), `${path}: ${await response.text()}`).toBe(true)
        return response.json()
      }
      const context: ProjectAnalysisContext = await get(`/projects/${fixtures.project.id}/project-analysis-context`)
      const sources = fixtures.project_analysis.inputs
      expect(sources).toHaveLength(2)
      expect(context.ai_available).toBe(false)
      const title = `Synthetic Project ${mode} ${locale} ${randomUUID().slice(0, 8)}`
      const project = `/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}`
      await page.addInitScript(language => localStorage.setItem("lang", JSON.stringify({ data: language, expire: null })), locale)
      await page.setViewportSize({ width: 390, height: 844 })
      await page.goto(`${project}/analysis`)
      await page.getByTestId("analysis-open-project").click()
      await expect(page).toHaveURL(/scope=project/)
      const workbench = page.getByTestId("project-analysis-workbench")
      await expect(workbench).toBeVisible()
      await expect(page.getByTestId("analysis-ai-draft-generate")).toHaveCount(0)
      const slots = page.getByTestId("project-analysis-slot")
      await expect(slots).toHaveCount(2)
      const slotIds: string[] = []
      for (const [index, source] of sources.entries()) {
        const card = slots.nth(index)
        slotIds.push((await card.getAttribute("data-slot-id"))!)
        const protocol = context.protocols.find(item => item.protocol_id === source.protocol_id)!
        const numeric = protocol.fields.find(field => field.key === source.value_field)!
        const contextResponse = page.waitForResponse(response => response.url().endsWith(`/project-analysis-context/${source.protocol_id}`) && response.request().method() === "POST")
        await card.getByTestId("project-source-protocol").click()
        await selectVisibleOption(page, protocol.protocol_name)
        expect((await contextResponse).ok()).toBe(true)
        await card.getByTestId("project-source-label").locator("input").fill(`Synthetic ${source.value_field}`)
        await card.getByTestId("project-source-select-records").click()
        const picker = page.getByTestId("project-record-picker")
        await expect(picker.getByRole("checkbox")).toHaveCount(3)
        for (const checkbox of await picker.getByRole("checkbox").all())
          await checkbox.check()
        const selectedContext = page.waitForResponse(response => response.url().endsWith(`/project-analysis-context/${source.protocol_id}`) && response.request().postDataJSON()?.mode === "selected", { timeout: 15_000 })
        await page.getByTestId("project-confirm-records").click()
        const selectedHttp = await selectedContext.catch((cause) => {
          throw new Error(`Record selection did not reach the API. Browser errors: ${pageErrors.join(" | ") || "none"}`, { cause })
        })
        expect(pageErrors).toEqual([])
        await expect(picker).toBeHidden()
        expect(selectedHttp.ok()).toBe(true)
        expect(selectedHttp.request().postDataJSON().records).toHaveLength(3)
        await card.getByTestId("project-numeric-fields").click()
        await selectVisibleOption(page, `${numeric.title || numeric.key}${numeric.unit ? ` (${numeric.unit})` : ""}`)
        await page.keyboard.press("Escape")
        await card.getByTestId("project-chart-type").click()
        await selectVisibleOption(page, locale === "en-US" ? "Bar chart" : "柱状图")
      }
      await page.getByTestId("project-analysis-question").locator("textarea").fill(title)
      if (mode === "relational") {
        await page.getByTestId("project-analysis-mode").click()
        await selectVisibleOption(page, locale === "en-US" ? "Join by explicit keys" : "按键关联计算")
        const join = page.getByTestId("project-join-editor")
        for (const [index, source] of sources.entries()) {
          const protocol = context.protocols.find(item => item.protocol_id === source.protocol_id)!
          const key = protocol.fields.find(field => field.key === source.key_field)!
          await join.getByTestId(index === 0 ? "project-join-key-left" : "project-join-key-right").click()
          await selectVisibleOption(page, `${key.title || key.key} · string`)
          await page.getByTestId("project-add-output").click()
          const output = page.getByTestId("project-join-output").nth(index)
          await output.getByTestId("project-output-id").locator("input").fill(source.value_field)
          await output.getByTestId("project-output-source").click()
          await selectVisibleOption(page, `Synthetic ${source.value_field}`)
          const numeric = protocol.fields.find(field => field.key === source.value_field)!
          await output.getByTestId("project-output-field").click()
          await selectVisibleOption(page, `${numeric.title || numeric.key} · number (${source.unit})`)
          await output.getByTestId("project-output-label").locator("input").fill(`Associated ${source.value_field}`)
        }
        await join.getByTestId("project-numeric-fields").click()
        for (const source of sources)
          await selectVisibleOption(page, `Associated ${source.value_field} (${source.unit})`)
        await page.keyboard.press("Escape")
        await expect(page.getByTestId("project-analysis-preview")).toBeDisabled()
        await page.getByTestId("project-confirm-semantics").check()
      }
      async function previewAndRun(expectedTitle: string, expectedRerunId: string | null = null) {
        const response = page.waitForResponse(response => response.url().endsWith("/analyses/project/preview") && response.request().method() === "POST")
        await expect(page.getByTestId("project-analysis-preview")).toBeEnabled()
        await page.getByTestId("project-analysis-preview").click()
        const http = await response
        expect(http.ok(), await http.text()).toBe(true)
        expect(http.request().postDataJSON().question).toBe(expectedTitle)
        expect(http.request().postDataJSON().rerun_of_id ?? null).toBe(expectedRerunId)
        const preview: ProjectAnalysisPreview = await http.json()
        expect(preview.question).toBe(expectedTitle)
        expect(preview.recipe.mode).toBe(mode)
        expect(preview.source_selection.inputs.every(input => input.selection.mode === "selected")).toBe(true)
        const modal = page.getByTestId("project-analysis-preview-dialog")
        await expect(modal).toBeVisible()
        await expect(page.getByTestId("project-analysis-confirm")).toBeDisabled()
        await page.getByTestId("project-preview-reviewed").check()
        const completed = page.waitForResponse(async (candidate) => {
          if (candidate.request().method() !== "GET" || !/\/analyses\/[0-9a-f-]+$/.test(new URL(candidate.url()).pathname) || !candidate.ok())
            return false
          const run = await candidate.json()
          return run.source_scope === "project" && run.question === expectedTitle && run.status === "succeeded"
        }, { timeout: 40_000 })
        await page.getByTestId("project-analysis-confirm").click()
        const run: ProjectAnalysisRun = await (await completed).json()
        await expect(page.getByTestId("project-analysis-report")).toBeVisible()
        return { preview, run }
      }
      const first = await previewAndRun(title)
      expect(first.preview.summary.counts).toEqual({ protocols: 2, records: 6 })
      expect(first.run.result!.local_results.find(item => item.slot_id === slotIds[0])!.report.groups[0].fields[sources[0].value_field].mean).toBe(4)
      expect(first.run.result!.local_results.find(item => item.slot_id === slotIds[1])!.report.groups[0].fields[sources[1].value_field].mean).toBeCloseTo(70 / 3)
      if (mode === "relational") {
        expect(first.run.result!.join!.audit).toMatchObject({ left: { matched: 2, unmatched: 1 }, right: { matched: 2, unmatched: 1 }, output_rows: 2 })
        expect(first.run.result!.join!.report.groups[0].fields.concentration.mean).toBe(3)
        expect(first.run.result!.join!.report.groups[0].fields.response.mean).toBe(15)
        expect(first.run.result!.join!.rows.every(row => Object.keys(row.sources).length === 2)).toBe(true)
        await page.getByTestId("project-analysis-report").getByTestId("project-join-audit").scrollIntoViewIfNeeded()
      }
      else {
        expect(first.run.result!.join).toBeNull()
        await page.getByTestId("project-analysis-report").getByTestId("project-local-result").first().scrollIntoViewIfNeeded()
      }
      await stableScreenshot(page, page.getByTestId("project-analysis-report"))
      await page.screenshot({ path: testInfo.outputPath(`project-${mode}-${locale}-report-phone.png`) })
      // Save and revise human interpretation independently of the sealed result.
      const interpretation = page.getByTestId("project-interpretation")
      await expect(interpretation.getByTestId("project-finding")).toHaveCount(2)
      await page.getByTestId("project-judgement-summary").locator("textarea").fill("Synthetic evidence is descriptive; no causal conclusion is established.")
      for (const [index] of sources.entries())
        await page.getByTestId("project-finding-note").nth(index).locator("textarea").fill(`Use the real computed ${sources[index].value_field} statistics without pooling units.`)
      async function saveJudgement(expected: number) {
        const response = page.waitForResponse(response => response.url().endsWith(`/analyses/${first.run.id}/interpretations`) && response.request().method() === "POST")
        await page.getByTestId("project-save-judgement").click()
        await page.getByRole("button", { name: locale === "en-US" ? "Confirm" : "确认", exact: true }).click()
        const http = await response
        expect(http.ok(), await http.text()).toBe(true)
        const revision: ProjectInterpretationRevision = await http.json()
        expect(revision.revision).toBe(expected)
        expect(revision.result_digest).toBe(first.run.result_digest)
        expect(revision.resolved_evidence).toBeTruthy()
        await expect(page.getByTestId("project-save-judgement")).toContainText(String(expected + 1))
        await expect(page.locator(".n-dialog")).toHaveCount(0)
        await expect(page.locator(".n-modal-mask")).toHaveCount(0)
      }
      await saveJudgement(1)
      await page.getByTestId("project-judgement-summary").locator("textarea").fill("Revised synthetic interpretation: retain uncertainty and document both sources.")
      await saveJudgement(2)
      const immutable: ProjectAnalysisRun = await get(`/analyses/${first.run.id}`)
      expect(immutable.result_digest).toBe(first.run.result_digest)
      expect(immutable.result).toEqual(first.run.result)
      await interpretation.scrollIntoViewIfNeeded()
      await stableScreenshot(page, interpretation)
      await page.screenshot({ path: testInfo.outputPath(`project-${mode}-${locale}-judgement-phone.png`) })
      const downloaded = page.waitForEvent("download")
      await page.getByTestId("project-download-report").click()
      const file = await (await downloaded).path()
      expect(file).toBeTruthy()
      const exported = JSON.parse(await readFile(file!, "utf8"))
      expect(exported.result_digest).toBe(first.run.result_digest)
      expect(exported.interpretations).toBeTruthy()

      await page.getByTestId("project-save-method").click()
      await page.getByTestId("project-method-title").locator("input").fill(`${title} method`)
      const savedResponse = page.waitForResponse(response => response.url().endsWith("/analysis-pipelines") && response.request().method() === "POST")
      await page.getByTestId("project-confirm-save-method").click()
      const savedHttp = await savedResponse
      expect(savedHttp.ok(), await savedHttp.text()).toBe(true)
      const saved: ProjectAnalysisPipeline = await savedHttp.json()
      const loadedMethod = page.waitForResponse(response => response.url().endsWith(`/analysis-pipelines/${saved.id}`) && response.request().method() === "GET")
      await page.getByTestId("project-analysis-method").filter({ hasText: `${title} method` }).click()
      expect((await loadedMethod).ok()).toBe(true)
      await expect(page.getByTestId("project-analysis-preview")).toBeEnabled()
      for (const card of await slots.all())
        await expect(card.getByTestId("project-source-selection")).toContainText("3")
      if (mode === "relational") {
        await slots.first().getByTestId("project-chart-type").click()
        await selectVisibleOption(page, locale === "en-US" ? "Line chart" : "折线图")
        await expect(page.getByTestId("project-analysis-preview")).toBeDisabled()
        const revisionResponse = page.waitForResponse(response => response.url().endsWith(`/analysis-pipelines/${saved.id}/revisions`) && response.request().method() === "POST")
        await page.getByTestId("project-save-revision").click()
        await page.getByRole("button", { name: locale === "en-US" ? "Confirm" : "确认", exact: true }).click()
        const revisedHttp = await revisionResponse
        expect(revisedHttp.ok(), await revisedHttp.text()).toBe(true)
        const method: ProjectAnalysisPipeline = await get(`/analysis-pipelines/${saved.id}`)
        expect(method.current_revision).toBe(2)
        expect(method.revisions!.find(revision => revision.revision === 1)!.recipe).toEqual(first.run.recipe)
        await expect(page.locator(".n-dialog")).toHaveCount(0)
        await expect(page.locator(".n-modal-mask")).toHaveCount(0)
        await expect(page.getByTestId("project-analysis-preview")).toBeEnabled()
      }
      else {
        // Delay only delivery of the real saved-method response, never its data.
        // A subsequent explicit rerun must win even when that response arrives late.
        let releaseMethod!: () => void
        let methodFetched = false
        const release = new Promise<void>((resolve) => {
          releaseMethod = resolve
        })
        const methodUrl = `**/analysis-pipelines/${saved.id}`
        await page.route(methodUrl, async (route) => {
          const response = await route.fetch()
          methodFetched = true
          await release
          await route.fulfill({ response })
        })
        const lateResponse = page.waitForResponse(response => response.url().endsWith(`/analysis-pipelines/${saved.id}`) && response.request().method() === "GET")
        await page.getByTestId("project-analysis-method").filter({ hasText: `${title} method` }).click()
        await expect.poll(() => methodFetched, { timeout: 15_000 }).toBe(true)
        await expect(page.getByTestId("project-analysis-preview")).toBeDisabled()
        await page.getByTestId("project-analysis-rerun").click()
        releaseMethod()
        expect((await lateResponse).ok()).toBe(true)
        await page.unroute(methodUrl)
        await expect(page.getByTestId("project-analysis-preview")).toBeEnabled()
        await slots.first().getByTestId("project-source-select-records").click()
        const picker = page.getByTestId("project-record-picker")
        await expect(picker.getByRole("checkbox")).toHaveCount(3)
        await picker.getByRole("checkbox").last().uncheck()
        await page.getByTestId("project-confirm-records").click()
      }
      const secondTitle = `${title} follow-up`
      await page.getByTestId("project-analysis-question").locator("textarea").fill(secondTitle)
      await expect(page.getByTestId("project-analysis-question").locator("textarea")).toHaveValue(secondTitle)
      const second = await previewAndRun(secondTitle, mode === "evidence_synthesis" ? first.run.id : null)
      if (mode === "evidence_synthesis") {
        expect(second.run.rerun_of_id).toBe(first.run.id)
        expect(second.preview.summary.counts.records).toBe(5)
      }
      const comparison = page.getByTestId("project-analysis-comparison")
      await comparison.getByTestId("project-comparison-baseline").click()
      await selectVisibleOption(page, `${title} ·`)
      const comparedResponse = page.waitForResponse(response => response.url().includes(`/analyses/${second.run.id}/comparison?`))
      await page.getByTestId("project-compare").click()
      const comparedHttp = await comparedResponse
      expect(comparedHttp.ok(), await comparedHttp.text()).toBe(true)
      const compared: ProjectAnalysisComparison = await comparedHttp.json()
      expect(compared.recipe_changed).toBe(mode === "relational")
      expect(compared.inputs.flatMap(input => input.removed)).toHaveLength(mode === "relational" ? 0 : 1)
      expect((await get(`/analyses/${first.run.id}`)).result_digest).toBe(first.run.result_digest)
      await comparison.scrollIntoViewIfNeeded()
      await stableScreenshot(page, comparison)
      await page.screenshot({ path: testInfo.outputPath(`project-${mode}-${locale}-comparison-phone.png`) })
      // A pre-existing direct analysis URL resolves the Project scope safely.
      await page.goto(`${project}/analysis?runId=${second.run.id}`)
      await expect(page).toHaveURL(new RegExp(`scope=project.*runId=${second.run.id}`))
      await expect(page.getByTestId("project-analysis-report")).toBeVisible()
      await expect(page.getByTestId("analysis-compute-report")).toHaveCount(0)
    })
  }
}

async function stableScreenshot(page: Page, surface: Locator) {
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
