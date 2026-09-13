/**
 * Advanced analysis UI CONTRACT tests — no real computation is performed.
 * Authentication, Project/Protocol navigation, Records and applied-filter
 * handoff use the real local fixture API. Compute environments, previews,
 * confirmations, approvals, jobs and downloads are synthetic browser responses.
 * These tests do not establish database persistence, Runner/container execution,
 * scientific validity, cost enforcement or backend authorization. Those belong
 * to the independent PostgreSQL and Compute Runner integration tests.
 */
import type { Locator, Page } from "@playwright/test"
import type { AnalysisAIComputeDraftRequest, AnalysisAIRequest, AnalysisComputeDraftOutput, AnalysisComputeInterpretation, AnalysisSelection, ComputeAnalysisRun } from "../../../apps/web/src/service/api/analysis"
import type {
  AnalysisComputeContext,
  AnalysisComputeContract,
  AnalysisComputeDetail,
  AnalysisComputePreview,
  AnalysisComputePreviewRequest,
  AnalysisComputeRecipe,
} from "../../../apps/web/src/service/api/analysis-compute"
import type { E2EFixtures } from "./fixtures"
import { createHash, randomUUID } from "node:crypto"
import { expect, test } from "@playwright/test"
import { loadFixtures, selectVisibleOption } from "./fixtures"

const untrustedText = "<img src=x onerror=\"window.__computeContractHtmlExecuted=true\">"
const sourceCode = `# Synthetic UI-contract source; not executed by this test.\n# ${untrustedText}\nimport json, os\nfrom pathlib import Path\nrecords = json.loads((Path(os.environ["AIRALOGY_INPUT_DIR"]) / "records.json").read_text())\nPath(os.environ["AIRALOGY_RESULT_JSON"]).write_text(json.dumps({"synthetic_count": len(records["records"])}))`
const sourceDigest = "a".repeat(64)
const contractDigest = "c".repeat(64)
const parameterValues = { threshold: 0.5, note: untrustedText }

interface ConfirmPayload { preview_id: string, preview_digest: string, client_idempotency_key: string }
interface DecisionPayload { decision: "approved" | "rejected", expected_revision: number, contract_digest: string, reason: string }
interface CancelPayload { expected_revision: number, contract_digest: string, reason: string }

interface ComputeUIState {
  aiAvailable: boolean
  runId: string
  context: AnalysisComputeContext
  detail: AnalysisComputeDetail | null
  previews: AnalysisComputePreview[]
  requests: {
    contexts: AnalysisSelection[]
    previews: AnalysisComputePreviewRequest[]
    confirms: ConfirmPayload[]
    decisions: DecisionPayload[]
    cancels: CancelPayload[]
    gets: string[]
    downloads: string[]
    modelWrites: string[]
  }
  loseConfirmResponse: boolean
  loseCancelResponse: boolean
  denyOwnerDetail: boolean
  revokeAfterCancellation: boolean
  rejectNextPreview: boolean
}

function computeContext(): AnalysisComputeContext {
  return {
    environments: [{
      id: randomUUID(),
      revision_id: randomUUID(),
      revision: 7,
      name: "Synthetic private Python and R environment",
      image_ref: `python@sha256:${"d".repeat(64)}`,
      allowed_languages: ["python", "r"],
      resource_limits: { cpu_millis: 1000, memory_mb: 256, gpu_count: 0, timeout_seconds: 60, max_output_bytes: 2_097_152 },
      network_policy: "none",
      allowed_egress_hosts: [],
      input_schema: { type: "object", properties: { threshold: { type: "number" }, note: { type: "string" } } },
      result_schema: { type: "object", properties: { synthetic_count: { type: "integer" } }, required: ["synthetic_count"], additionalProperties: false },
      estimated_cost: "0.25",
      currency: "USD",
      authorized_runner_count: 1,
      ready_runner_count: 0,
    }],
    approvers: [{ id: randomUUID(), name: "Synthetic source-authorized approver" }],
    source: { record_count: 1, source_digest: sourceDigest, filename: "records.json" },
    max_source_bytes: 200_000,
    input_file_fields: [{ field_path: ["var", "synthetic_attachment"], title: "Synthetic attachment", file_extensions: ["csv"], nullable: true }],
    input_file_limits: { max_files: 30, max_file_bytes: 268435456, max_total_bytes: 536870912, manifest_filename: "attachments.json" },
  }
}

function makeContract(fixtures: E2EFixtures, state: ComputeUIState, payload: AnalysisComputePreviewRequest): AnalysisComputeContract {
  const environment = state.context.environments.find(item => item.revision_id === payload.recipe.environment_revision_id)!
  return {
    environment: {
      key: "synthetic-compute-ui-contract",
      version: "7",
      kind: "compute",
      name: environment.name,
      description: "Synthetic browser contract only",
      source_type: "research_compute_environment_revision",
      source_id: environment.id,
      source_revision_id: environment.revision_id,
      executor_types: ["compute_runner"],
      risk: "low",
      input_schema: environment.input_schema,
      output_schema: environment.result_schema,
      available: true,
      unavailable_reason: "",
      metadata: {
        lab_id: fixtures.lab.id,
        environment_key: "synthetic-compute-ui-contract",
        environment_revision: environment.revision,
        runner_protocol_version: "airalogy.compute-runner.v1",
        image_ref: environment.image_ref,
        runtime_version: "UI contract only",
        allowed_languages: environment.allowed_languages,
        resource_limits: environment.resource_limits,
        network_policy: environment.network_policy,
        allowed_egress_hosts: [],
        software_manifest: {},
        change_reason: "Synthetic browser fixture, not a deployment",
      },
    },
    source: { language: payload.recipe.language, code: payload.recipe.source_code, sha256: createHash("sha256").update(payload.recipe.source_code).digest("hex"), bytes: new TextEncoder().encode(payload.recipe.source_code).byteLength },
    input: { filename: "records.json", record_count: state.context.source.record_count, bytes: 1200, sha256: sourceDigest },
    ...(payload.recipe.input_files?.length
      ? {
          input_files: {
            schema: "airalogy.analysis-attachments.v1",
            count: payload.recipe.input_files.length,
            total_bytes: payload.recipe.input_files.length * 12,
            files: payload.recipe.input_files.map(input => ({ ...input, record_id: state.runId, record_version: 1, record_hash: sourceDigest, protocol_version: "1.0.0", file_id: "synthetic-ui-file-id", filename: "synthetic-input.csv", media_type: "text/csv", byte_size: 12, checksum_sha256: "e".repeat(64), mount_name: `${input.input_id}_synthetic.csv`, file_metadata_digest: "f".repeat(64) })),
            manifest: { filename: "attachments.json", byte_size: 800, checksum_sha256: "a".repeat(64) },
          },
        }
      : {}),
    parameters: structuredClone(payload.recipe.parameters),
    output_files: structuredClone(payload.recipe.output_files),
    approver: state.context.approvers.find(item => item.id === payload.approver_user_id)!,
    cost: { estimated_cost: environment.estimated_cost, currency: environment.currency, max_cost: payload.max_cost ?? null, budget_currency: payload.budget_currency ?? null },
    deadline_at: payload.deadline_at ?? null,
    authorized_runner_count: environment.authorized_runner_count,
    ready_runner_count: environment.ready_runner_count,
    approval_required: true,
  }
}

function makePreview(fixtures: E2EFixtures, state: ComputeUIState, payload: AnalysisComputePreviewRequest): AnalysisComputePreview {
  const count = state.context.source.record_count
  return {
    id: randomUUID(),
    protocol_id: fixtures.analysis.protocol_id,
    project_id: fixtures.project.id,
    question: payload.question,
    recipe: structuredClone(payload.recipe),
    source_selection: structuredClone(payload.selection),
    source_digest: sourceDigest,
    recipe_digest: "b".repeat(64),
    preview_digest: contractDigest,
    ai_provenance: {},
    expires_at: new Date(Date.now() + 600_000).toISOString(),
    summary: {
      compute: makeContract(fixtures, state, payload),
      counts: { total: count, included: count, filtered_out: 0 },
      sources: [],
      source_digest: sourceDigest,
      protocol_name: "Synthetic UI-contract Protocol",
      project_name: "Synthetic UI-contract Project",
      visibility: "private",
    },
  }
}

function makeDetail(state: ComputeUIState, preview: AnalysisComputePreview): AnalysisComputeDetail {
  const now = new Date().toISOString()
  const run: ComputeAnalysisRun = {
    id: state.runId,
    status: "pending",
    protocol_id: preview.protocol_id,
    project_id: preview.project_id,
    created_by_user_id: randomUUID(),
    question: preview.question,
    recipe: preview.recipe,
    source_selection: preview.source_selection,
    source_digest: preview.source_digest,
    recipe_digest: preview.recipe_digest,
    preview_digest: preview.preview_digest,
    result_digest: null,
    result: null,
    pipeline_revision_id: null,
    rerun_of_id: null,
    created_at: now,
    started_at: null,
    finished_at: null,
    engine_version: "airalogy.compute.analysis.v1",
    error: null,
  }
  return {
    run,
    contract: preview.summary.compute,
    approval: { state: "pending", revision: 2, approver_user_id: preview.summary.compute.approver.id, can_approve: false, contract_digest: contractDigest },
    job: {
      id: randomUUID(),
      action_id: randomUUID(),
      compute_environment_id: preview.summary.compute.environment.source_id,
      compute_environment_revision_id: preview.recipe.environment_revision_id,
      compute_environment_revision: 7,
      language: preview.recipe.language,
      source_code: preview.recipe.source_code,
      source_sha256: preview.summary.compute.source.sha256,
      source_bytes: preview.summary.compute.source.bytes,
      input_payload: preview.recipe.parameters,
      environment_snapshot: { ...preview.summary.compute.environment },
      result_schema: preview.summary.compute.environment.output_schema,
      resource_limits: { ...preview.summary.compute.environment.metadata.resource_limits },
      timeout_seconds: 60,
      estimated_cost: "0.25",
      actual_cost: null,
      currency: "USD",
      status: "awaiting_approval",
      attempt_count: 0,
      result: {},
      output_manifest: [],
      usage: {},
      revision: 4,
      created_at: now,
    },
    events: [{ id: randomUUID(), kind: "compute.requested", created_at: now, details: {} }],
  }
}

function redactedDetail(detail: AnalysisComputeDetail): AnalysisComputeDetail {
  const copy = structuredClone(detail)
  delete copy.run.source_snapshot
  delete copy.run.result
  copy.job.result = {}
  copy.job.output_manifest = []
  copy.job.error = null
  return copy
}

async function installComputeUIContract(page: Page, fixtures: E2EFixtures): Promise<ComputeUIState> {
  const state: ComputeUIState = {
    aiAvailable: false,
    runId: randomUUID(),
    context: computeContext(),
    detail: null,
    previews: [],
    requests: { contexts: [], previews: [], confirms: [], decisions: [], cancels: [], gets: [], downloads: [], modelWrites: [] },
    loseConfirmResponse: false,
    loseCancelResponse: false,
    denyOwnerDetail: false,
    revokeAfterCancellation: false,
    rejectNextPreview: false,
  }
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "en-US", expire: null })))
  page.on("request", (request) => {
    if (request.method() === "POST" && /\/(?:aira-drafts|aira-compute-drafts|aira-interpretations)$/.test(new URL(request.url()).pathname))
      state.requests.modelWrites.push(request.url())
  })
  await page.route(`**/api/protocols/${fixtures.analysis.protocol_id}/analysis-context`, async (route) => {
    const response = await route.fetch()
    expect(response.ok()).toBe(true)
    await route.fulfill({ response, json: { ...await response.json(), ai_available: state.aiAvailable } })
  })
  await page.route(`**/api/protocols/${fixtures.analysis.protocol_id}/analysis-ai-drafts`, route => route.fulfill({ json: { items: [] } }))
  await page.route(`**/api/protocols/${fixtures.analysis.protocol_id}/analysis-ai-compute-drafts`, route => route.fulfill({ json: { items: [] } }))
  await page.route(`**/api/projects/${fixtures.project.id}/analyses`, route => route.fulfill({ json: { items: state.detail ? [state.detail.run] : [] } }))
  await page.route(`**/api/projects/${fixtures.project.id}/analysis-pipelines`, route => route.fulfill({ json: { items: [] } }))
  await page.route("**/api/analysis-compute-approvals?*", route => route.fulfill({ json: { items: [] } }))
  await page.route(`**/api/protocols/${fixtures.analysis.protocol_id}/analysis-compute-context`, async (route) => {
    expect(route.request().method()).toBe("POST")
    state.requests.contexts.push(route.request().postDataJSON() as AnalysisSelection)
    await route.fulfill({ json: state.context })
  })
  await page.route("**/api/analyses/compute/preview", async (route) => {
    expect(route.request().method()).toBe("POST")
    const payload = route.request().postDataJSON() as AnalysisComputePreviewRequest
    state.requests.previews.push(payload)
    if (state.rejectNextPreview) {
      state.rejectNextPreview = false
      await route.fulfill({ status: 409, json: { detail: "Synthetic source snapshot changed after Aira generation" } })
      return
    }
    const preview = makePreview(fixtures, state, payload)
    state.previews.push(preview)
    await route.fulfill({ json: preview })
  })
  await page.route("**/api/analyses/compute", async (route) => {
    expect(route.request().method()).toBe("POST")
    const payload = route.request().postDataJSON() as ConfirmPayload
    state.requests.confirms.push(payload)
    const preview = state.previews.find(item => item.id === payload.preview_id)!
    expect(payload.preview_digest).toBe(preview.preview_digest)
    state.detail ||= makeDetail(state, preview)
    if (state.loseConfirmResponse) {
      state.loseConfirmResponse = false
      await route.abort("failed")
      return
    }
    await route.fulfill({ json: state.detail.run })
  })
  await page.route(`**/api/analyses/${state.runId}`, async (route) => {
    state.requests.gets.push("run")
    await route.fulfill(state.detail ? { json: state.detail.run } : { status: 404, json: { detail: "Synthetic run not found" } })
  })
  await page.route(`**/api/analyses/${state.runId}/compute`, async (route) => {
    state.requests.gets.push("owner-detail")
    await route.fulfill(state.denyOwnerDetail ? { status: 403, json: { detail: "Synthetic source access revoked" } } : { json: state.detail })
  })
  await page.route(`**/api/analyses/${state.runId}/compute-approval`, async (route) => {
    const detail = state.detail!
    if (route.request().method() === "POST") {
      const payload = route.request().postDataJSON() as DecisionPayload
      state.requests.decisions.push(payload)
      expect(payload.contract_digest).toBe(detail.approval.contract_digest)
      expect(payload.expected_revision).toBe(detail.approval.revision)
      detail.approval.state = payload.decision
      detail.approval.revision += 1
      detail.approval.can_approve = false
      detail.job.status = payload.decision === "approved" ? "queued" : "cancelled"
      detail.run.status = payload.decision === "approved" ? "pending" : "cancelled"
    }
    else {
      state.requests.gets.push("approval-detail")
    }
    await route.fulfill({ json: redactedDetail(detail) })
  })
  await page.route(`**/api/analyses/${state.runId}/compute-cancel`, async (route) => {
    const payload = route.request().postDataJSON() as CancelPayload
    state.requests.cancels.push(payload)
    const detail = state.detail!
    expect(payload.contract_digest).toBe(contractDigest)
    if (state.requests.cancels.length === 1) {
      expect(payload.expected_revision).toBe(detail.job.revision)
      detail.job.status = "cancel_requested"
      detail.job.revision += 1
    }
    else {
      expect(payload).toEqual(state.requests.cancels[0])
    }
    if (state.revokeAfterCancellation)
      state.denyOwnerDetail = true
    if (state.loseCancelResponse) {
      state.loseCancelResponse = false
      await route.abort("failed")
      return
    }
    // Intentionally receipt-only: raw source/result must not be available here.
    await route.fulfill({ json: { analysis_id: state.runId, job_id: detail.job.id, status: detail.job.status, revision: detail.job.revision } })
  })
  await page.route(`**/api/analyses/${state.runId}/compute/outputs/*`, async (route) => {
    const id = new URL(route.request().url()).pathname.split("/").at(-1)!
    state.requests.downloads.push(id)
    await route.fulfill({ body: "synthetic_count\n1\n", contentType: "text/csv", headers: { "Content-Disposition": "attachment; filename=synthetic-count.csv", "Cache-Control": "private, no-store" } })
  })
  return state
}

function workbenchUrl(fixtures: E2EFixtures) {
  return `/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}/analysis`
}

async function openFromFilteredRecords(page: Page, fixtures: E2EFixtures, aiAvailable = false) {
  const recordsPath = `/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}/protocols/${fixtures.analysis.protocol_uid}/records`
  await page.goto(recordsPath)
  await page.getByRole("button", { name: "Advanced search", exact: true }).click()
  const numberInput = page.getByPlaceholder("Enter record number", { exact: true })
  await numberInput.fill("1")
  const applied = page.waitForResponse(response => new URL(response.url()).pathname.endsWith(`/protocols/${fixtures.analysis.protocol_id}/records`) && new URL(response.url()).searchParams.get("number") === "1")
  await page.getByRole("button", { name: "Apply filters", exact: true }).click()
  expect((await applied).ok()).toBe(true)
  await expect(page.getByTestId("analysis-filtered-trigger")).toBeEnabled()
  // Unapplied editor text must not replace the last successfully applied scope.
  await numberInput.fill("2")
  const context = page.waitForResponse(response => response.url().endsWith(`/protocols/${fixtures.analysis.protocol_id}/analysis-context`) && response.request().method() === "POST")
  await page.getByTestId("analysis-filtered-trigger").click()
  const response = await context
  expect(response.ok()).toBe(true)
  expect(response.request().postDataJSON()).toEqual({ mode: "latest", filters: { number: 1 } })
  await expect(page.getByTestId("analysis-mode")).toBeVisible()
  if (!aiAvailable)
    await expect(page.getByTestId("analysis-ai-draft-generate")).toHaveCount(0)
  await page.getByTestId("analysis-mode").click()
  await selectVisibleOption(page, "Advanced Python / R computation")
  await expect(page.getByTestId("analysis-compute-source")).toBeVisible()
}

async function fillManualSource(page: Page) {
  await page.getByTestId("analysis-question").locator("textarea").fill("Synthetic UI-contract private computation")
  await page.getByTestId("analysis-compute-source").locator("textarea").fill(sourceCode)
  await page.getByTestId("analysis-compute-parameters").locator("textarea").fill(JSON.stringify(parameterValues))
}

async function assertPhoneContained(page: Page, locator: Locator, margin = 0) {
  await expect(locator).toBeVisible()
  await expect.poll(async () => (await locator.boundingBox())?.width).toBeLessThanOrEqual(390 - 2 * margin)
  const box = (await locator.boundingBox())!
  expect(box.x).toBeGreaterThanOrEqual(margin - 1)
  expect(box.x + box.width).toBeLessThanOrEqual(391 - margin)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
}

async function waitForStableDialog(dialog: Locator) {
  await expect(dialog).toBeVisible()
  // Await the real modal opacity/scale transitions, not an arbitrary sleep or
  // a disabled-animation screenshot that could conceal a rendering regression.
  await expect.poll(() => dialog.evaluate((element) => {
    for (let node: Element | null = element; node; node = node.parentElement) {
      if (getComputedStyle(node).opacity !== "1" || node.getAnimations().some(animation => animation.playState === "running" || animation.pending))
        return false
    }
    return true
  })).toBe(true)
}

function seedDetail(fixtures: E2EFixtures, state: ComputeUIState) {
  const recipe: AnalysisComputeRecipe = { kind: "compute", environment_revision_id: state.context.environments[0].revision_id, language: "python", source_code: sourceCode, parameters: parameterValues, output_files: [] }
  const preview = makePreview(fixtures, state, { protocol_id: fixtures.analysis.protocol_id, selection: { mode: "latest", filters: { number: 1 } }, question: "Synthetic UI-contract seeded request", recipe, approver_user_id: state.context.approvers[0].id, max_cost: "1.50", budget_currency: "USD" })
  const detail = makeDetail(state, preview)
  state.detail = detail
  return detail
}

async function installComputeAiraContract(page: Page, fixtures: E2EFixtures, compute: ComputeUIState) {
  const state = {
    saved: new Map<string, AnalysisAIRequest>(),
    posts: [] as AnalysisAIComputeDraftRequest[],
    interpretationPosts: [] as Array<{ id: string, locale: string, question?: string }>,
    reads: [] as string[],
    loseNextResponse: false,
    failReads: false,
    releasePost: null as (() => void) | null,
    holdPost: false,
    wrongMetric: false,
  }
  compute.aiAvailable = true
  const responseBase = (id: string, kind: AnalysisAIRequest["kind"], question: string, locale: AnalysisAIRequest["locale"]): AnalysisAIRequest => ({
    id,
    kind,
    question,
    locale,
    protocol_id: fixtures.analysis.protocol_id,
    project_id: fixtures.project.id,
    analysis_run_id: kind === "interpretation" ? compute.runId : null,
    previous_request_id: null,
    model: "synthetic-compute-aira-ui-contract",
    operation_id: `ui-contract-${id}`,
    state: "generated",
    output: null,
    error: null,
    source_selection: { mode: "latest", filters: { number: 1 } },
    source_digest: sourceDigest,
    input_digest: "b".repeat(64),
    output_digest: "c".repeat(64),
    created_at: new Date().toISOString(),
    finished_at: new Date().toISOString(),
    deadline: new Date(Date.now() + 60_000).toISOString(),
  })
  await page.route(`**/api/protocols/${fixtures.analysis.protocol_id}/analysis-ai-compute-drafts`, route => route.fulfill({ json: { items: [...state.saved.values()].filter(item => item.kind === "compute_draft").reverse() } }))
  await page.route("**/api/analyses/aira-compute-drafts", async (route) => {
    const payload = route.request().postDataJSON() as AnalysisAIComputeDraftRequest
    state.posts.push(payload)
    const output: AnalysisComputeDraftOutput = { mode: "compute", title: "Synthetic editable code draft", explanation: "UI contract only; no model or computation executed.", assumptions: ["Review the selected environment result schema."], clarification_questions: [], recipe: { kind: "compute", environment_revision_id: payload.environment_revision_id, language: payload.language, source_code: sourceCode, parameters: parameterValues, output_files: [] } }
    const saved = state.saved.get(payload.id) || { ...responseBase(payload.id, "compute_draft", payload.question, payload.locale), source_selection: structuredClone(payload.selection), output }
    state.saved.set(saved.id, saved)
    if (state.holdPost)
      await new Promise<void>((resolve) => { state.releasePost = resolve })
    if (state.loseNextResponse) {
      state.loseNextResponse = false
      await route.abort("failed")
      return
    }
    await route.fulfill({ json: saved })
  })
  await page.route(`**/api/analyses/${compute.runId}/aira-interpretations`, async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ json: { items: [...state.saved.values()].filter(item => item.kind === "interpretation").reverse() } })
      return
    }
    const payload = route.request().postDataJSON() as { id: string, locale: "en-US" | "zh-CN", question?: string }
    state.interpretationPosts.push(payload)
    const output: AnalysisComputeInterpretation = { result_kind: "compute", summary: "Synthetic grounded compute interpretation", observations: [{ text: `Synthetic interpretation ${untrustedText}`, metrics: [{ pointer: "/synthetic_count", value: state.wrongMetric ? 99 : 1 }, { pointer: "/labels/a~1b", value: "sample" }] }], limitations: ["No causal claim is established."], next_steps: ["Review assumptions before further research."], interpretation_origin: "ai", numeric_values_origin: "computed_result" }
    const saved = { ...responseBase(payload.id, "interpretation", payload.question || "", payload.locale), output }
    state.saved.set(saved.id, saved)
    await route.fulfill({ json: saved })
  })
  await page.route("**/api/analysis-ai-requests/*", async (route) => {
    const id = new URL(route.request().url()).pathname.split("/").at(-1)!
    state.reads.push(id)
    if (state.failReads) {
      await route.abort("failed")
      return
    }
    const saved = state.saved.get(id)
    await route.fulfill(saved ? { json: saved } : { status: 404, json: { detail: "Synthetic request not found" } })
  })
  return state
}

test.describe("Advanced Aira UI contract — synthetic code generation and grounded interpretation", () => {
  test.beforeEach(async ({ page }, testInfo) => {
    testInfo.annotations.push({ type: "verification-boundary", description: "Synthetic Aira and Compute API responses; real navigation and source handoff only. No model calls or code execution." })
    await page.setViewportSize({ width: 390, height: 844 })
  })

  test("separate consent generates an editable exact-environment draft while the Runner is offline, without executing", async ({ page }, testInfo) => {
    const fixtures = await loadFixtures()
    const compute = await installComputeUIContract(page, fixtures)
    const ai = await installComputeAiraContract(page, fixtures, compute)
    await openFromFilteredRecords(page, fixtures, true)
    await page.getByTestId("analysis-question").locator("textarea").fill("Draft a scoped count calculation")
    const generate = page.getByTestId("analysis-ai-compute_draft-generate")
    await expect(generate).toBeDisabled()
    await page.getByTestId("analysis-ai-compute_draft-consent").click()
    await expect(generate).toBeEnabled()
    await generate.click()
    await expect(page.getByTestId("analysis-ai-compute_draft-output")).toContainText("Synthetic editable code draft")
    expect(ai.posts).toHaveLength(1)
    expect(ai.posts[0]).toMatchObject({ protocol_id: fixtures.analysis.protocol_id, selection: { mode: "latest", filters: { number: 1 } }, environment_revision_id: compute.context.environments[0].revision_id, language: "python", locale: "en-US" })
    expect(Object.keys(ai.posts[0])).not.toContain("records")
    expect(compute.requests.previews).toEqual([])
    expect(compute.requests.confirms).toEqual([])
    await page.getByTestId("analysis-ai-compute-adopt").click()
    await expect(page.getByTestId("analysis-ai-compute-adopted")).toBeVisible()
    await expect(page.getByTestId("analysis-compute-source").locator("textarea")).toHaveValue(sourceCode)
    const edited = `${sourceCode}\n# Researcher reviewed and edited this draft.`
    await page.getByTestId("analysis-compute-source").locator("textarea").fill(edited)
    await page.getByTestId("analysis-compute-parameters").locator("textarea").fill("{\"threshold\":0.75}")
    await page.getByTestId("analysis-compute-preview").click()
    await expect(page.getByTestId("analysis-compute-preview-dialog")).toBeVisible()
    expect(compute.requests.previews[0]).toMatchObject({ ai_draft_id: ai.posts[0].id, selection: ai.posts[0].selection, recipe: { environment_revision_id: ai.posts[0].environment_revision_id, language: "python", source_code: edited, parameters: { threshold: 0.75 } } })
    expect(compute.requests.confirms).toEqual([])
    await assertPhoneContained(page, page.getByTestId("analysis-compute-preview-dialog"), 16)
    await waitForStableDialog(page.getByTestId("analysis-compute-preview-dialog"))
    await page.screenshot({ path: testInfo.outputPath("compute-aira-edited-preview-phone.png"), fullPage: true })
  })

  test("lost generation recovery keeps one request identity and saved drafts remain readable with AI off", async ({ page }) => {
    const fixtures = await loadFixtures()
    const compute = await installComputeUIContract(page, fixtures)
    const ai = await installComputeAiraContract(page, fixtures, compute)
    ai.loseNextResponse = true
    ai.failReads = true
    await openFromFilteredRecords(page, fixtures, true)
    await page.getByTestId("analysis-question").locator("textarea").fill("Draft a recoverable analysis")
    await page.getByTestId("analysis-ai-compute_draft-consent").click()
    await page.getByTestId("analysis-ai-compute_draft-generate").click()
    await expect(page.getByTestId("analysis-ai-compute_draft-recover")).toBeVisible()
    await expect.poll(() => ai.reads.length).toBeGreaterThan(0)
    await expect(page.getByTestId("analysis-ai-compute_draft-generate")).toBeDisabled()
    const firstId = ai.posts[0].id
    ai.failReads = false
    await page.getByTestId("analysis-ai-compute_draft-recover").click()
    await expect(page.getByTestId("analysis-ai-compute_draft-output")).toContainText("Synthetic editable code draft")
    expect(ai.posts).toHaveLength(1)
    expect(ai.reads.every(id => id === firstId)).toBe(true)
    compute.aiAvailable = false
    await openFromFilteredRecords(page, fixtures)
    await expect(page.getByTestId("analysis-ai-compute_draft-generate")).toHaveCount(0)
    await page.getByTestId("analysis-ai-compute_draft").getByRole("button", { name: /Draft a recoverable analysis/ }).click()
    await expect(page.getByTestId("analysis-ai-compute_draft-output")).toContainText("Synthetic editable code draft")
    await expect(page.getByTestId("analysis-ai-compute-adopt")).toBeEnabled()
    expect(ai.posts).toHaveLength(1)
    await page.getByTestId("analysis-ai-compute-adopt").click()
    const edited = `${sourceCode}\n# Manual recovery review`
    await page.getByTestId("analysis-compute-source").locator("textarea").fill(edited)
    compute.rejectNextPreview = true
    await page.getByTestId("analysis-compute-preview").click()
    await expect(page.getByTestId("analysis-compute-preview-dialog")).toBeHidden()
    await expect(page.getByTestId("analysis-ai-compute-manual")).toBeEnabled()
    await page.getByTestId("analysis-ai-compute-manual").click()
    await page.getByRole("button", { name: "Confirm", exact: true }).click()
    await expect(page.getByTestId("analysis-ai-compute-adopted")).toHaveCount(0)
    await expect(page.getByTestId("analysis-compute-source").locator("textarea")).toHaveValue(edited)
    await page.getByTestId("analysis-compute-preview").click()
    await expect(page.getByTestId("analysis-compute-preview-dialog")).toBeVisible()
    expect(compute.requests.previews).toHaveLength(2)
    expect(compute.requests.previews[0].ai_draft_id).toBe(firstId)
    expect(compute.requests.previews[1].ai_draft_id).toBeUndefined()
    expect(compute.requests.previews[1].recipe.source_code).toBe(edited)
    expect(ai.posts).toHaveLength(1)
  })

  test("adopting an Aira draft preserves only user-selected attachments and retains edited provenance", async ({ page }, testInfo) => {
    const fixtures = await loadFixtures()
    const compute = await installComputeUIContract(page, fixtures)
    const ai = await installComputeAiraContract(page, fixtures, compute)
    await openFromFilteredRecords(page, fixtures, true)
    await page.getByTestId("analysis-question").locator("textarea").fill("Draft a calculation while preserving my explicitly selected attachment fields")
    await expect(page.getByTestId("analysis-compute-input-declaration")).toHaveCount(0)
    await page.getByTestId("analysis-compute-add-input").click()
    await page.getByTestId("analysis-compute-input-id").locator("input").fill("chosen_csv")
    await page.getByTestId("analysis-compute-input-field").click()
    await selectVisibleOption(page, "Synthetic attachment [synthetic_attachment] (csv)")
    await page.getByTestId("analysis-ai-compute_draft-consent").click()
    await expect(page.getByTestId("analysis-ai-compute_draft-generate")).toBeEnabled()
    await page.getByTestId("analysis-ai-compute_draft-generate").click()
    await expect(page.getByTestId("analysis-ai-compute_draft-output")).toBeVisible()
    expect(ai.posts[0]).not.toHaveProperty("input_files")
    expect(ai.posts[0]).not.toHaveProperty("attachments")
    const output = ai.saved.get(ai.posts[0].id)!.output as AnalysisComputeDraftOutput
    expect(output.recipe).not.toHaveProperty("input_files")
    await page.getByTestId("analysis-ai-compute-adopt").click()
    await expect(page.getByTestId("analysis-compute-input-id").locator("input")).toHaveValue("chosen_csv")
    await expect(page.getByTestId("analysis-compute-input-declaration")).toHaveCount(1)
    await page.getByTestId("analysis-compute-preview").click()
    await expect(page.getByTestId("analysis-compute-preview-dialog")).toBeVisible()
    expect(compute.requests.previews[0]).toMatchObject({ ai_draft_id: ai.posts[0].id, recipe: { input_files: [{ input_id: "chosen_csv", field_path: ["var", "synthetic_attachment"] }] } })
    await expect(page.getByTestId("analysis-compute-input-file")).toContainText("synthetic-input.csv")
    await assertPhoneContained(page, page.getByTestId("analysis-compute-preview-dialog"), 16)
    await waitForStableDialog(page.getByTestId("analysis-compute-preview-dialog"))
    await page.screenshot({ path: testInfo.outputPath("compute-aira-explicit-attachment-phone.png") })
    expect(compute.requests.confirms).toEqual([])
  })

  test("changing language discards an in-flight response, clears consent and rejects adoption from another environment revision", async ({ page }) => {
    const fixtures = await loadFixtures()
    const compute = await installComputeUIContract(page, fixtures)
    const ai = await installComputeAiraContract(page, fixtures, compute)
    ai.holdPost = true
    await openFromFilteredRecords(page, fixtures, true)
    await page.getByTestId("analysis-question").locator("textarea").fill("Draft Python code for these Records")
    await page.getByTestId("analysis-ai-compute_draft-consent").click()
    await page.getByTestId("analysis-ai-compute_draft-generate").click()
    await expect.poll(() => Boolean(ai.releasePost)).toBe(true)
    await page.getByTestId("analysis-compute-language").click()
    await selectVisibleOption(page, "R")
    ai.releasePost!()
    ai.holdPost = false
    await expect(page.getByTestId("analysis-ai-compute_draft-generate")).toBeDisabled()
    await expect(page.getByTestId("analysis-ai-compute-adopted")).toHaveCount(0)
    await expect(page.getByTestId("analysis-compute-source").locator("textarea")).toHaveValue("")
    const panel = page.getByTestId("analysis-ai-compute_draft")
    await panel.getByRole("button", { name: /Draft Python code for these Records/ }).click()
    await expect(page.getByTestId("analysis-ai-compute-adopt")).toBeDisabled()
    const saved = ai.saved.get(ai.posts[0].id)!
    if (saved.output && "recipe" in saved.output && saved.output.recipe && "kind" in saved.output.recipe) {
      saved.output.recipe.language = "r"
      saved.output.recipe.environment_revision_id = randomUUID()
    }
    await panel.locator("details").last().locator("summary").click()
    await panel.getByRole("button", { name: /Draft Python code for these Records/ }).click()
    await expect(page.getByTestId("analysis-ai-compute-adopt")).toBeDisabled()
    expect(ai.posts).toHaveLength(1)
    expect(compute.requests.previews).toEqual([])
  })

  for (const locale of ["en-US", "zh-CN"] as const) {
    test(`${locale} compute interpretation resolves sealed JSON pointers and withholds mismatched model values`, async ({ page }, testInfo) => {
      const fixtures = await loadFixtures()
      const compute = await installComputeUIContract(page, fixtures)
      const ai = await installComputeAiraContract(page, fixtures, compute)
      await page.addInitScript(value => localStorage.setItem("lang", JSON.stringify({ data: value, expire: null })), locale)
      const detail = seedDetail(fixtures, compute)
      detail.run.status = "succeeded"
      detail.job.status = "completed"
      detail.approval.state = "approved"
      detail.job.result = { synthetic_count: 1, labels: { "a/b": "sample" } }
      detail.run.result = { computed_result: structuredClone(detail.job.result), outputs: [], usage: {}, actual_cost: null, currency: null }
      await page.goto(`${workbenchUrl(fixtures)}?protocolId=${fixtures.analysis.protocol_id}&runId=${compute.runId}`)
      const report = page.getByTestId("analysis-compute-report")
      const contractHistory = page.getByTestId("analysis-compute-historical-contract")
      await expect(page.getByTestId("analysis-compute-result")).toBeVisible()
      await expect(contractHistory).not.toHaveAttribute("open")
      await expect(report.getByTestId("analysis-compute-review-code")).toBeHidden()
      await expect(report.getByTestId("analysis-compute-contract-review-warning")).toHaveCount(0)
      await expect(report.getByTestId("analysis-compute-contract-offline-warning")).toHaveCount(0)
      await contractHistory.locator("summary").click()
      const code = report.getByTestId("analysis-compute-review-code")
      await expect(code).toHaveText(sourceCode)
      await expect(code).toBeVisible()
      await code.focus()
      await expect(code).toBeFocused()
      await expect(contractHistory).toContainText(locale === "zh-CN" ? "约定快照中记录的 Runner 可用状态" : "Recorded Runner availability (contract snapshot)")
      await contractHistory.locator("summary").click()
      await expect(code).toBeHidden()
      const panel = page.getByTestId("analysis-ai-interpretation")
      const generate = page.getByTestId("analysis-ai-interpretation-generate")
      await expect(generate).toBeDisabled()
      await page.getByTestId("analysis-ai-interpretation-consent").click()
      await generate.click()
      await expect(panel).toContainText("Synthetic grounded compute interpretation")
      await expect(panel.getByTestId("analysis-ai-metric").first()).toHaveText("/synthetic_count: 1")
      await expect(panel.getByTestId("analysis-ai-metric").last()).toHaveText("/labels/a~1b: \"sample\"")
      await expect(panel.locator("img, script, iframe")).toHaveCount(0)
      expect(ai.interpretationPosts[0].locale).toBe(locale)
      await assertPhoneContained(page, panel)
      await page.screenshot({ path: testInfo.outputPath(`compute-aira-grounded-${locale}-phone.png`), fullPage: true })
      ai.wrongMetric = true
      await generate.click()
      await expect(page.getByTestId("analysis-ai-grounding-rejected")).toBeVisible()
      await expect(panel).not.toContainText("Synthetic grounded compute interpretation")
      await expect(panel.getByTestId("analysis-ai-metric")).toHaveCount(0)
      await expect(page.getByTestId("analysis-compute-result")).toContainText("\"synthetic_count\": 1")
      expect(compute.requests.confirms).toEqual([])
    })
  }
})

test.describe("Advanced Record analysis UI contract — synthetic Compute service, no Runner execution", () => {
  test.beforeEach(async ({ page }, testInfo) => {
    testInfo.annotations.push({ type: "verification-boundary", description: "UI contract only: Compute service/jobs/outputs are synthetic browser responses. No computation, budget charge, persisted approval or private-file backend authorization is verified here." })
    await page.setViewportSize({ width: 1280, height: 900 })
  })

  test("AI-off manual configuration preserves applied filters, reviews the full private contract and retries lost confirmation with the same identity", async ({ page }, testInfo) => {
    const fixtures = await loadFixtures()
    const state = await installComputeUIContract(page, fixtures)
    state.loseConfirmResponse = true
    await openFromFilteredRecords(page, fixtures)
    expect(state.requests.contexts).toEqual([{ mode: "latest", filters: { number: 1 } }])
    await fillManualSource(page)
    const previewButton = page.getByTestId("analysis-compute-preview")
    await page.getByTestId("analysis-compute-parameters").locator("textarea").fill("[1,2]")
    await expect(previewButton).toBeDisabled()
    await page.getByTestId("analysis-compute-parameters").locator("textarea").fill(JSON.stringify(parameterValues))
    await page.getByRole("button", { name: "Add output file", exact: true }).click()
    const output = page.locator(".compute-output")
    const filename = output.locator(".n-form-item").filter({ hasText: "Safe output filename" }).locator("input")
    await filename.fill("../private.csv")
    await expect(previewButton).toBeDisabled()
    await filename.fill("synthetic-count.csv")
    await output.locator(".n-form-item").filter({ hasText: "Output name" }).locator("input").fill("Synthetic count, not real computation")
    await output.locator(".n-form-item").filter({ hasText: "Media type" }).locator("input").fill("text/csv")
    await page.getByTestId("analysis-compute-max-cost").locator("input").fill("1.50")
    await expect(previewButton).toBeEnabled()
    await expect(page.getByTestId("analysis-compute-form")).toContainText("Authorized Runners are currently offline or occupied")
    await page.setViewportSize({ width: 390, height: 844 })
    await assertPhoneContained(page, page.getByTestId("analysis-compute-form"))
    await previewButton.click()
    const previewDialog = page.getByTestId("analysis-compute-preview-dialog")
    await expect(previewDialog).toBeVisible()
    const payload = state.requests.previews[0]
    expect(payload).toMatchObject({
      protocol_id: fixtures.analysis.protocol_id,
      selection: { mode: "latest", filters: { number: 1 } },
      approver_user_id: state.context.approvers[0].id,
      max_cost: "1.50",
      budget_currency: "USD",
      recipe: { kind: "compute", environment_revision_id: state.context.environments[0].revision_id, language: "python", source_code: sourceCode, parameters: parameterValues, output_files: [{ mount_name: "synthetic-count.csv", asset_name: "Synthetic count, not real computation", media_type: "text/csv", required: true, data_schema: {}, metadata: {} }] },
    })
    expect(state.requests.confirms).toEqual([])
    const contract = previewDialog.getByTestId("analysis-compute-contract")
    await expect(previewDialog).toContainText("Synthetic UI-contract Project")
    await expect(previewDialog).toContainText("Synthetic UI-contract Protocol")
    for (const value of ["records.json", sourceDigest, "1 Records", "1.50 USD", "0.25 USD", "synthetic-count.csv", "\"threshold\": 0.5", "Synthetic source-authorized approver", state.context.environments[0].image_ref])
      await expect(contract).toContainText(value)
    await expect(previewDialog.getByTestId("analysis-compute-review-code")).toHaveText(sourceCode)
    await expect(previewDialog.getByTestId("analysis-compute-review-schemas")).toContainText("\"synthetic_count\"")
    await expect(previewDialog.getByTestId("analysis-compute-review-schemas")).toContainText("\"additionalProperties\": false")
    await expect(contract.locator("img, script, iframe")).toHaveCount(0)
    expect(await page.evaluate(() => Reflect.get(window, "__computeContractHtmlExecuted"))).toBeUndefined()
    await assertPhoneContained(page, previewDialog, 16)
    const code = previewDialog.getByTestId("analysis-compute-review-code")
    await expect(code).toHaveCSS("overflow-x", "auto")
    await code.focus()
    await page.keyboard.press("ArrowRight")
    await expect.poll(() => code.evaluate(element => element.scrollLeft)).toBeGreaterThan(0)
    await waitForStableDialog(previewDialog)
    await page.screenshot({ path: testInfo.outputPath("compute-ui-contract-private-preview-phone.png"), fullPage: true })
    await page.getByTestId("analysis-compute-confirm").click()
    await expect(previewDialog).toContainText("could not be completed")
    await expect(page.getByTestId("analysis-compute-confirm")).toBeEnabled()
    expect(state.requests.confirms).toHaveLength(1)
    await page.getByTestId("analysis-compute-confirm").click()
    await expect(page.getByTestId("analysis-compute-report")).toContainText("Awaiting approval")
    expect(state.requests.confirms).toHaveLength(2)
    expect(state.requests.confirms[1]).toEqual(state.requests.confirms[0])
    expect(state.requests.confirms[0].client_idempotency_key).toMatch(/^[0-9a-f-]{36}$/)
    expect(state.requests.modelWrites).toEqual([])
    expect(state.requests.decisions).toEqual([])
    await expect(page.getByTestId("analysis-compute-result")).toHaveCount(0)
    await assertPhoneContained(page, page.getByTestId("analysis-compute-report"))
  })

  test("no authorized Runner blocks preview and confirmation without blocking ordinary AI-off analysis", async ({ page }) => {
    const fixtures = await loadFixtures()
    const state = await installComputeUIContract(page, fixtures)
    state.context.environments[0].authorized_runner_count = 0
    await openFromFilteredRecords(page, fixtures)
    await fillManualSource(page)
    await expect(page.getByTestId("analysis-compute-form")).toContainText("No Runner is authorized for this exact environment revision")
    await expect(page.getByTestId("analysis-compute-preview")).toBeDisabled()
    await expect(page.getByTestId("analysis-compute-confirm")).toBeHidden()
    expect(state.requests.previews).toEqual([])
    expect(state.requests.confirms).toEqual([])
    await page.getByTestId("analysis-mode").click()
    await selectVisibleOption(page, "Built-in descriptive statistics")
    await expect(page.getByTestId("analysis-numeric-fields")).toBeVisible()
    await expect(page.getByTestId("analysis-compute-form")).toHaveCount(0)
    expect(state.requests.modelWrites).toEqual([])
  })

  for (const decision of ["approved", "rejected"] as const) {
    test(`the selected approver explicitly confirms ${decision} against the sealed revision without loading owner-only data`, async ({ page }) => {
      const fixtures = await loadFixtures()
      const state = await installComputeUIContract(page, fixtures)
      const detail = seedDetail(fixtures, state)
      detail.approval.can_approve = true
      detail.job.result = { secret: "raw-output-must-not-be-shown-to-approver" }
      await page.setViewportSize({ width: 390, height: 844 })
      await page.goto(`${workbenchUrl(fixtures)}?computeApproval=${state.runId}`)
      const report = page.getByTestId("analysis-compute-report")
      await expect(report).toContainText("Review private computation approval")
      await expect(report).not.toContainText("raw-output-must-not-be-shown-to-approver")
      await expect(page.getByTestId("analysis-compute-result")).toHaveCount(0)
      await expect(page.getByTestId("analysis-compute-output-download")).toHaveCount(0)
      await expect(page.getByTestId("analysis-compute-cancel")).toHaveCount(0)
      await expect(report.getByTestId("analysis-compute-review-schemas")).toContainText("synthetic_count")
      await expect(page.getByTestId("analysis-compute-approve")).toBeDisabled()
      await expect(report.getByTestId("analysis-compute-review-code")).toBeVisible()
      await expect(page.getByTestId("analysis-compute-historical-contract")).toHaveCount(0)
      await page.getByTestId("analysis-compute-reviewed").click()
      await expect(page.getByTestId("analysis-compute-approve")).toBeEnabled()
      await page.getByTestId(decision === "approved" ? "analysis-compute-approve" : "analysis-compute-reject").click()
      const dialog = page.getByTestId("analysis-compute-decision-dialog")
      await expect(dialog).toContainText(contractDigest)
      await expect(page.getByTestId("analysis-compute-confirm-decision")).toBeDisabled()
      expect(state.requests.decisions).toEqual([])
      await page.getByTestId("analysis-compute-reason").locator("textarea").fill(`Synthetic UI-contract ${decision} reason`)
      await assertPhoneContained(page, dialog, 16)
      await page.getByTestId("analysis-compute-confirm-decision").click()
      await expect(dialog).toBeHidden()
      expect(state.requests.decisions).toEqual([{ decision, expected_revision: 2, contract_digest: contractDigest, reason: `Synthetic UI-contract ${decision} reason` }])
      await expect(report).toContainText(decision === "approved" ? "Queued — waiting for Runner" : "Cancelled")
      await expect(report.getByTestId("analysis-compute-contract-review-warning")).toHaveCount(0)
      await expect(report.getByTestId("analysis-compute-contract-offline-warning")).toHaveCount(0)
      if (decision === "rejected") {
        await expect(page.getByTestId("analysis-compute-historical-contract")).not.toHaveAttribute("open")
        await expect(report.getByTestId("analysis-compute-review-code")).toBeHidden()
      }
      expect(state.requests.gets.every(value => value === "approval-detail")).toBe(true)
      expect(state.requests.modelWrites).toEqual([])
      await assertPhoneContained(page, report)
    })
  }

  test("a lost cancellation response is explicitly retried with the identical payload after source access is revoked, returning only a safe receipt", async ({ page }) => {
    const fixtures = await loadFixtures()
    const state = await installComputeUIContract(page, fixtures)
    const detail = seedDetail(fixtures, state)
    detail.job.status = "running"
    detail.run.status = "running"
    detail.approval.state = "approved"
    state.loseCancelResponse = true
    state.revokeAfterCancellation = true
    await page.goto(`${workbenchUrl(fixtures)}?protocolId=${fixtures.analysis.protocol_id}&runId=${state.runId}`)
    await expect(page.getByTestId("analysis-compute-report")).toContainText("Running")
    await page.getByTestId("analysis-compute-cancel").click()
    const dialog = page.getByTestId("analysis-compute-decision-dialog")
    const confirm = page.getByTestId("analysis-compute-confirm-decision")
    await expect(confirm).toBeDisabled()
    expect(state.requests.cancels).toEqual([])
    const reason = "Synthetic UI-contract stop request"
    await page.getByTestId("analysis-compute-reason").locator("textarea").fill(reason)
    await confirm.click()
    await expect(dialog).toContainText("The cancellation response was not received")
    await expect(page.getByTestId("analysis-compute-reason").locator("textarea")).toBeDisabled()
    await expect(page.getByTestId("analysis-compute-cancel-receipt")).toHaveCount(0)
    // Let the normal detail poll recheck permissions; no artificial sleep and no
    // cached raw result can keep the report readable after this synthetic 403.
    await expect(page.getByTestId("analysis-compute-report")).toContainText("no longer authorized", { timeout: 12_000 })
    await expect(page.getByTestId("analysis-compute-review-code")).toHaveCount(0)
    expect(state.requests.cancels).toEqual([{ expected_revision: 4, contract_digest: contractDigest, reason }])
    await expect(dialog).toContainText(contractDigest)
    await expect(confirm).toBeEnabled()
    await confirm.click()
    await expect(dialog).toBeHidden()
    const receipt = page.getByTestId("analysis-compute-cancel-receipt")
    await expect(receipt).toContainText("Cancellation request recorded")
    await expect(receipt).toContainText("Cancellation requested")
    await expect(receipt).not.toContainText("Current state: Cancelled")
    expect(state.requests.cancels).toHaveLength(2)
    expect(state.requests.cancels[1]).toEqual(state.requests.cancels[0])
    await expect(page.getByTestId("analysis-compute-result")).toHaveCount(0)
    await expect(page.getByTestId("analysis-compute-review-code")).toHaveCount(0)
    expect(state.requests.confirms).toEqual([])
    expect(state.requests.modelWrites).toEqual([])
  })

  test("synthetic completed output is escaped text, downloads privately and reruns with the original source selection", async ({ page }, testInfo) => {
    const fixtures = await loadFixtures()
    const state = await installComputeUIContract(page, fixtures)
    const detail = seedDetail(fixtures, state)
    detail.approval.state = "approved"
    detail.job.status = "completed"
    detail.run.status = "succeeded"
    detail.job.result = { synthetic_count: 1, note: untrustedText }
    detail.job.output_manifest = [{ id: randomUUID(), mount_name: "synthetic-count.csv", asset_name: "Synthetic count fixture", media_type: "text/csv", max_bytes: 1024, byte_size: 18, checksum_sha256: "e".repeat(64), required: true, status: "registered" }]
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto(`${workbenchUrl(fixtures)}?protocolId=${fixtures.analysis.protocol_id}&runId=${state.runId}`)
    const report = page.getByTestId("analysis-compute-report")
    await expect(page.getByTestId("analysis-compute-result")).toContainText(untrustedText.replaceAll("\"", "\\\""))
    await expect(report.locator("img, script, iframe")).toHaveCount(0)
    await expect(page.getByTestId("analysis-result-table")).toHaveCount(0)
    await expect(page.getByTestId("analysis-ai-interpretation-generate")).toHaveCount(0)
    expect(await page.evaluate(() => Reflect.get(window, "__computeContractHtmlExecuted"))).toBeUndefined()
    await assertPhoneContained(page, report)
    const downloading = page.waitForEvent("download")
    await page.getByTestId("analysis-compute-output-download").click()
    const download = await downloading
    expect(download.suggestedFilename()).toBe("synthetic-count.csv")
    expect(state.requests.downloads).toEqual([detail.job.output_manifest[0].id])
    await page.getByTestId("analysis-rerun").click()
    await expect(page.getByTestId("analysis-mode")).toContainText("Advanced Python / R computation")
    await expect(page.getByTestId("analysis-compute-source").locator("textarea")).toHaveValue(sourceCode)
    await expect.poll(() => state.requests.contexts.at(-1)).toEqual({ mode: "latest", filters: { number: 1 } })
    await page.getByTestId("analysis-compute-preview").click()
    await expect(page.getByTestId("analysis-compute-preview-dialog")).toBeVisible()
    expect(state.requests.previews[0]).toMatchObject({ selection: { mode: "latest", filters: { number: 1 } }, rerun_of_id: state.runId, recipe: detail.run.recipe })
    expect(state.requests.confirms).toEqual([])
    expect(state.requests.modelWrites).toEqual([])
    await waitForStableDialog(page.getByTestId("analysis-compute-preview-dialog"))
    await page.screenshot({ path: testInfo.outputPath("compute-ui-contract-rerun-phone.png"), fullPage: true })
  })
})
