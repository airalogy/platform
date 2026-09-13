/**
 * Aira UI CONTRACT tests, not model/scientific/AI-persistence acceptance.
 * Only AI capability metadata and generation/history/recovery responses are
 * replaced in the browser. Protocols, Records, source authorization and preview
 * remain real. Synthetic AI IDs must be rejected by the real preview API; these
 * tests never confirm them or add a production mock-provider mechanism.
 * Real numerical execution and AI provenance are tested independently in
 * record-analysis.spec.ts and test_record_analysis_ai_postgres.py.
 */
import type { Page } from "@playwright/test"
import type { AnalysisAIDraftRequest, AnalysisAIRequest, AnalysisDraftOutput } from "../../../apps/web/src/service/api/analysis"
import type { E2EFixtures } from "./fixtures"
import { randomUUID } from "node:crypto"
import { expect, test } from "@playwright/test"
import { loadFixtures, selectVisibleOption } from "./fixtures"

interface UIContractState {
  aiAvailable: boolean
  mode: AnalysisDraftOutput["mode"]
  saved: Map<string, AnalysisAIRequest>
  posts: AnalysisAIDraftRequest[]
  reads: string[]
  loseNextPostResponse: boolean
  rejectNextPost: boolean
  failReads: number
  deniedIds: Set<string>
}

function draftOutput(mode: AnalysisDraftOutput["mode"]): AnalysisDraftOutput {
  return {
    mode,
    title: `UI contract: ${mode}`,
    explanation: "Synthetic interface response only; no model or analysis was executed.",
    assumptions: ["Review the selected Records and declared measurement units."],
    recipe: mode === "builtin"
      ? { schema_version: 1, numeric_fields: ["measurement"], group_by: [], filters: [], missing_policy: "exclude", chart: "bar" }
      : null,
    clarification_questions: mode === "clarification_required" ? ["Which measured endpoint should be compared?"] : [],
    compute_requirements: mode === "compute_required" ? ["A separately reviewed regression implementation is required."] : [],
  }
}

function savedDraft(fixtures: E2EFixtures, payload: AnalysisAIDraftRequest, mode: AnalysisDraftOutput["mode"]): AnalysisAIRequest {
  const now = new Date().toISOString()
  return {
    id: payload.id,
    kind: "draft",
    project_id: fixtures.project.id,
    protocol_id: fixtures.analysis.protocol_id,
    analysis_run_id: null,
    previous_request_id: payload.previous_request_id || null,
    question: payload.question,
    locale: payload.locale,
    model: "synthetic-ui-contract-not-a-real-model",
    operation_id: `ui-contract-${payload.id}`,
    state: "generated",
    output: draftOutput(mode),
    error: null,
    source_selection: structuredClone(payload.selection),
    source_digest: "a".repeat(64),
    input_digest: "b".repeat(64),
    output_digest: "c".repeat(64),
    created_at: now,
    finished_at: now,
    deadline: new Date(Date.now() + 75_000).toISOString(),
  }
}

async function installUIContract(page: Page, fixtures: E2EFixtures): Promise<UIContractState> {
  const state: UIContractState = {
    aiAvailable: true,
    mode: "builtin",
    saved: new Map(),
    posts: [],
    reads: [],
    loseNextPostResponse: false,
    rejectNextPost: false,
    failReads: 0,
    deniedIds: new Set(),
  }
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "en-US", expire: null })))
  // Preserve the real fields and authorized scope; replace only the AI capability
  // bit so this interface contract can run against the real AI-disabled backend.
  await page.route(`**/api/protocols/${fixtures.analysis.protocol_id}/analysis-context`, async (route) => {
    const response = await route.fetch()
    expect(response.ok()).toBe(true)
    await route.fulfill({ response, json: { ...await response.json(), ai_available: state.aiAvailable } })
  })
  await page.route(`**/api/protocols/${fixtures.analysis.protocol_id}/analysis-ai-drafts`, async (route) => {
    expect(route.request().method()).toBe("GET")
    await route.fulfill({ json: { items: [...state.saved.values()].reverse() } })
  })
  await page.route("**/api/analyses/aira-drafts", async (route) => {
    expect(route.request().method()).toBe("POST")
    const payload = route.request().postDataJSON() as AnalysisAIDraftRequest
    state.posts.push(payload)
    if (state.rejectNextPost) {
      state.rejectNextPost = false
      await route.fulfill({ status: 422, json: { detail: "Synthetic question requires correction before generation" } })
      return
    }
    const saved = state.saved.get(payload.id) || savedDraft(fixtures, payload, state.mode)
    state.saved.set(payload.id, saved)
    if (state.loseNextPostResponse) {
      state.loseNextPostResponse = false
      // Simulated receipt loss after saving the synthetic interface response.
      await route.abort("failed")
      return
    }
    await route.fulfill({ json: saved })
  })
  await page.route("**/api/analysis-ai-requests/*", async (route) => {
    expect(route.request().method()).toBe("GET")
    const id = new URL(route.request().url()).pathname.split("/").at(-1)!
    state.reads.push(id)
    if (state.failReads > 0) {
      state.failReads -= 1
      await route.abort("failed")
      return
    }
    if (state.deniedIds.has(id)) {
      await route.fulfill({ status: 403, json: { detail: "Synthetic source access revoked" } })
      return
    }
    const saved = state.saved.get(id)
    await route.fulfill(saved ? { json: saved } : { status: 404, json: { detail: "Synthetic request not found" } })
  })
  return state
}

async function openWorkbench(page: Page, fixtures: E2EFixtures) {
  const project = `/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}`
  await page.goto(`${project}/protocols/${fixtures.analysis.protocol_uid}/records`)
  const context = page.waitForResponse(response => response.url().endsWith(`/protocols/${fixtures.analysis.protocol_id}/analysis-context`) && response.request().method() === "POST")
  await page.getByTestId("analysis-filtered-trigger").click()
  const response = await context
  expect(response.ok()).toBe(true)
  expect(response.request().postDataJSON()).toEqual({ mode: "latest", filters: {} })
  await expect(page.getByTestId("analysis-question")).toBeVisible()
  await expect(page.getByTestId("analysis-workbench")).toBeVisible()
}

function recordExecutionWrites(page: Page) {
  const writes: string[] = []
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname
    if (request.method() === "POST" && /^\/api\/(?:analyses(?:\/preview)?|research-tasks(?:\/preview)?)$/.test(path))
      writes.push(path)
  })
  return writes
}

async function assertPhoneLayout(page: Page) {
  const panel = page.getByTestId("analysis-ai-draft")
  await expect(panel).toBeVisible()
  const box = (await panel.boundingBox())!
  expect(box.x).toBeGreaterThanOrEqual(0)
  expect(box.x + box.width).toBeLessThanOrEqual(391)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
}

test.describe("Aira analysis UI contract — synthetic generation, real source/preview boundary", () => {
  test.beforeEach(async ({ page }, testInfo) => {
    testInfo.annotations.push({ type: "verification-boundary", description: "UI contract only: generation/history/capability responses are synthetic; no AI provider or synthetic request is persisted by Platform." })
    await page.setViewportSize({ width: 390, height: 844 })
  })

  test("requires consent, adopts an editable draft and sends exact scope/provenance to real preview", async ({ page }, testInfo) => {
    const fixtures = await loadFixtures()
    const state = await installUIContract(page, fixtures)
    const writes = recordExecutionWrites(page)
    await openWorkbench(page, fixtures)
    await page.getByTestId("analysis-question").locator("textarea").fill("Compare the measurement using the current Records")
    const generate = page.getByTestId("analysis-ai-draft-generate")
    await expect(generate).toBeDisabled()
    expect(state.posts).toHaveLength(0)
    await page.getByTestId("analysis-ai-draft-consent").click()
    await expect(generate).toBeEnabled()
    await generate.click()
    const output = page.getByTestId("analysis-ai-draft-output")
    await expect(output).toContainText("UI contract: builtin")
    expect(state.posts).toHaveLength(1)
    const request = state.posts[0]
    expect(request).toMatchObject({ protocol_id: fixtures.analysis.protocol_id, selection: { mode: "latest", filters: {} }, locale: "en-US" })
    expect(request.id).toMatch(/^[0-9a-f-]{36}$/)
    expect(writes).toEqual([])
    await page.getByTestId("analysis-ai-adopt").click()
    await expect(page.getByTestId("analysis-ai-adopted")).toBeVisible()
    await expect(page.getByTestId("analysis-numeric-fields")).toContainText("Measurement")
    await page.getByTestId("analysis-chart-type").click()
    await selectVisibleOption(page, "Line chart")
    await page.getByTestId("analysis-question").locator("textarea").fill("Researcher-edited descriptive comparison")
    const previewResponse = page.waitForResponse(response => response.url().endsWith("/analyses/preview") && response.request().method() === "POST")
    await page.getByTestId("analysis-preview").click()
    const preview = await previewResponse
    expect(preview.request().postDataJSON()).toMatchObject({
      ai_draft_id: request.id,
      protocol_id: fixtures.analysis.protocol_id,
      selection: request.selection,
      question: "Researcher-edited descriptive comparison",
      recipe: { numeric_fields: ["measurement"], group_by: [], filters: [], chart: "line" },
    })
    // This ID exists only in the UI fixture. The REAL API must reject it;
    // bypassing this check or mocking successful confirmation would be dishonest.
    expect(preview.status()).toBe(404)
    await expect(page.getByTestId("analysis-preview-dialog")).toBeHidden()
    await expect(page.getByTestId("analysis-confirm")).toBeHidden()
    expect(writes).toEqual(["/api/analyses/preview"])
    await assertPhoneLayout(page)
    await page.screenshot({ path: testInfo.outputPath("aira-ui-contract-adopt-phone.png"), fullPage: true })
  })

  for (const mode of ["clarification_required", "compute_required"] as const) {
    test(`${mode} remains a non-executing proposal`, async ({ page }, testInfo) => {
      const fixtures = await loadFixtures()
      const state = await installUIContract(page, fixtures)
      state.mode = mode
      const writes = recordExecutionWrites(page)
      await openWorkbench(page, fixtures)
      await page.getByTestId("analysis-question").locator("textarea").fill(mode === "compute_required" ? "Fit a regression model" : "Which comparison is appropriate?")
      await page.getByTestId("analysis-ai-draft-consent").click()
      await page.getByTestId("analysis-ai-draft-generate").click()
      const output = page.getByTestId("analysis-ai-draft-output")
      await expect(output).toContainText(`UI contract: ${mode}`)
      await expect(output).toContainText(mode === "compute_required" ? "A separately reviewed regression implementation" : "Which measured endpoint")
      await expect(page.getByTestId("analysis-ai-adopt")).toHaveCount(0)
      await expect(page.getByTestId("analysis-preview")).toBeDisabled()
      await expect(page.getByTestId("analysis-confirm")).toBeHidden()
      expect(state.posts).toHaveLength(1)
      expect(writes).toEqual([])
      await assertPhoneLayout(page)
      if (mode === "compute_required") {
        await page.getByRole("button", { name: "Configure advanced computation", exact: true }).click()
        await expect(page.getByTestId("analysis-compute-form")).toBeVisible()
        await expect(page.getByTestId("analysis-mode")).toContainText("Advanced Python / R computation")
        await expect(page.getByTestId("analysis-compute-source").locator("textarea")).toHaveValue("")
        await expect(page.getByTestId("analysis-compute-confirm")).toBeHidden()
        expect(new URL(page.url()).pathname).toMatch(/\/analysis$/)
        expect(writes).toEqual([])
      }
      await page.screenshot({ path: testInfo.outputPath(`aira-ui-contract-${mode}-phone.png`), fullPage: true })
    })
  }

  test("lost response recovers by GET with the same paid-attempt identity and no second POST", async ({ page }) => {
    const fixtures = await loadFixtures()
    const state = await installUIContract(page, fixtures)
    state.loseNextPostResponse = true
    state.failReads = 1
    const writes = recordExecutionWrites(page)
    await openWorkbench(page, fixtures)
    await page.getByTestId("analysis-question").locator("textarea").fill("Recover this one draft attempt")
    await page.getByTestId("analysis-ai-draft-consent").click()
    await page.getByTestId("analysis-ai-draft-generate").click()
    const recover = page.getByTestId("analysis-ai-draft-recover")
    await expect(recover).toBeEnabled()
    expect(state.posts).toHaveLength(1)
    const requestId = state.posts[0].id
    expect(state.reads).toEqual([requestId])
    await expect(page.getByTestId("analysis-ai-draft-generate")).toBeDisabled()
    await recover.click()
    await expect(page.getByTestId("analysis-ai-draft-output")).toContainText("UI contract: builtin")
    expect(state.reads).toEqual([requestId, requestId])
    expect(state.posts.map(request => request.id)).toEqual([requestId])
    await expect(recover).toBeHidden()
    expect(writes).toEqual([])
    await assertPhoneLayout(page)
  })

  test("an explicit 422 rejection allows a corrected new request without uncertain GET recovery", async ({ page }) => {
    const fixtures = await loadFixtures()
    const state = await installUIContract(page, fixtures)
    state.rejectNextPost = true
    const writes = recordExecutionWrites(page)
    await openWorkbench(page, fixtures)
    const question = page.getByTestId("analysis-question").locator("textarea")
    await question.fill("An incomplete interface-contract question")
    await page.getByTestId("analysis-ai-draft-consent").click()
    await page.getByTestId("analysis-ai-draft-generate").click()
    await expect(page.getByTestId("analysis-ai-draft-error")).toBeVisible()
    await expect(page.getByTestId("analysis-ai-draft-recover")).toHaveCount(0)
    expect(state.posts).toHaveLength(1)
    expect(state.reads).toEqual([])
    await question.fill("A corrected explicit comparison of measurement")
    await expect(page.getByTestId("analysis-ai-draft-generate")).toBeEnabled()
    await page.getByTestId("analysis-ai-draft-generate").click()
    await expect(page.getByTestId("analysis-ai-draft-output")).toContainText("UI contract: builtin")
    expect(state.posts).toHaveLength(2)
    expect(state.posts[0].id).not.toBe(state.posts[1].id)
    expect(state.reads).toEqual([])
    expect(writes).toEqual([])
  })

  test("AI-off keeps readable history without consent/generation controls and rechecks access on open", async ({ page }, testInfo) => {
    const fixtures = await loadFixtures()
    const state = await installUIContract(page, fixtures)
    state.aiAvailable = false
    const previous = savedDraft(fixtures, {
      id: randomUUID(),
      protocol_id: fixtures.analysis.protocol_id,
      selection: { mode: "latest", filters: {} },
      question: "Previously reviewed UI contract draft",
      locale: "en-US",
    }, "builtin")
    state.saved.set(previous.id, previous)
    const writes = recordExecutionWrites(page)
    await openWorkbench(page, fixtures)
    const panel = page.getByTestId("analysis-ai-draft")
    await expect(panel).toBeVisible()
    await expect(page.getByTestId("analysis-ai-draft-generate")).toHaveCount(0)
    await expect(page.getByTestId("analysis-ai-draft-consent")).toHaveCount(0)
    const history = panel.locator(".analysis-ai-history")
    await history.getByRole("button", { name: /Previously reviewed UI contract draft/ }).click()
    await expect(page.getByTestId("analysis-ai-draft-output")).toContainText(previous.question)
    expect(state.reads).toEqual([previous.id])
    expect(state.posts).toEqual([])
    await assertPhoneLayout(page)
    await page.screenshot({ path: testInfo.outputPath("aira-ui-contract-ai-off-history-phone.png"), fullPage: true })
    // Opening saved history is a fresh authorization fetch, not a stale cache.
    state.deniedIds.add(previous.id)
    await panel.locator("details").filter({ has: page.locator(".analysis-ai-history") }).locator("summary").click()
    await history.getByRole("button", { name: /Previously reviewed UI contract draft/ }).click()
    await expect(page.getByTestId("analysis-ai-draft-output")).toBeHidden()
    await expect(history.getByRole("button")).toHaveCount(0)
    expect(state.reads).toEqual([previous.id, previous.id])
    expect(state.posts).toEqual([])
    expect(writes).toEqual([])
  })
})
