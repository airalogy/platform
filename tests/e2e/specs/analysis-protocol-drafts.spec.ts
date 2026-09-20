import type { Locator, Page } from "@playwright/test"
import type { AnalysisProtocolDraft, AnalysisProtocolPreview, AnalysisProtocolRevision, AnalysisProtocolTemplate } from "../../../apps/web/src/service/api/analysis-protocol-drafts"
import type { ProjectAnalysisPipeline, ProjectAnalysisPreview, ProjectAnalysisRun } from "../../../apps/web/src/service/api/project-analysis"
import type { WorkflowAnalysisPublication, WorkflowAnalysisPublicationPreview, WorkflowAnalysisPublicationRequest } from "../../../apps/web/src/service/api/workflow-analysis-methods"
import type { WorkflowContext } from "../../../apps/web/src/service/api/workflow-definitions"
import { Buffer } from "node:buffer"
import { createHash, randomUUID } from "node:crypto"
import { readFile } from "node:fs/promises"
import { inflateRawSync } from "node:zlib"
import { expect, test } from "@playwright/test"
import { loadFixtures, selectVisibleOption } from "./fixtures"

function sha256(value: string | Buffer) {
  return createHash("sha256").update(value).digest("hex")
}

function canonical(value: unknown): string {
  if (Array.isArray(value))
    return `[${value.map(canonical).join(",")}]`
  if (value && typeof value === "object")
    return `{${Object.entries(value).sort(([left], [right]) => left.localeCompare(right)).map(([key, content]) => `${JSON.stringify(key)}:${canonical(content)}`).join(",")}}`
  return JSON.stringify(value)
}

function fileManifest(files: Record<string, string>) {
  return Object.entries(files).sort(([left], [right]) => left.localeCompare(right)).map(([path, content]) => ({ path, size_bytes: Buffer.byteLength(content, "utf8"), sha256: sha256(content) }))
}

function packageDigest(files: Record<string, string>) {
  return sha256(canonical({ schema: "airalogy.analysis-protocol-package.v1", files: fileManifest(files).map(file => ({ path: file.path, bytes: file.size_bytes, sha256: file.sha256 })) }))
}

// Read the actual server-created ZIP with standard Node APIs, not a fabricated
// Protocol or a dependency on the private Protocol executor. Central-directory
// sizes handle both ordinary ZIPs and streamed local headers/data descriptors.
function packageFiles(archive: Buffer) {
  expect(archive.length).toBeLessThanOrEqual(1_114_112)
  let end = archive.length - 22
  while (end >= Math.max(0, archive.length - 65_557) && archive.readUInt32LE(end) !== 0x06054B50)
    end--
  expect(end).toBeGreaterThanOrEqual(0)
  expect(archive.readUInt16LE(end + 10)).toBe(3)
  let position = archive.readUInt32LE(end + 16)
  const files: Record<string, string> = {}
  for (let index = 0; index < 3; index++) {
    expect(archive.readUInt32LE(position)).toBe(0x02014B50)
    const compression = archive.readUInt16LE(position + 10)
    const compressedSize = archive.readUInt32LE(position + 20)
    const size = archive.readUInt32LE(position + 24)
    const nameLength = archive.readUInt16LE(position + 28)
    const name = archive.subarray(position + 46, position + 46 + nameLength).toString("utf8")
    expect(["protocol.toml", "protocol.aimd", "analysis-method.json"]).toContain(name)
    expect(Object.hasOwn(files, name)).toBe(false)
    expect(size).toBeLessThanOrEqual(524_288)
    const local = archive.readUInt32LE(position + 42)
    expect(archive.readUInt32LE(local)).toBe(0x04034B50)
    const start = local + 30 + archive.readUInt16LE(local + 26) + archive.readUInt16LE(local + 28)
    const compressed = archive.subarray(start, start + compressedSize)
    expect([0, 8]).toContain(compression)
    const content = compression === 0 ? compressed : inflateRawSync(compressed, { maxOutputLength: 524_288 })
    expect(content.length).toBe(size)
    files[name] = content.toString("utf8")
    position += 46 + nameLength + archive.readUInt16LE(position + 30) + archive.readUInt16LE(position + 32)
  }
  return files
}

function editToml(source: string, updates: Record<string, string>) {
  for (const [key, value] of Object.entries(updates)) {
    const pattern = new RegExp(`^${key}\\s*=\\s*.+$`, "gm")
    expect(source.match(pattern)).toHaveLength(1)
    source = source.replace(pattern, `${key} = ${JSON.stringify(value)}`)
  }
  return source
}

async function stablePhoneSurface(page: Page, surface: Locator) {
  await expect(surface).toBeVisible()
  await surface.scrollIntoViewIfNeeded()
  await expect(page.locator(".n-base-select-option:visible")).toHaveCount(0)
  await expect(page.locator(".n-message")).toHaveCount(0, { timeout: 10_000 })
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
  await expect.poll(() => surface.evaluate((element) => {
    for (let node: Element | null = element; node; node = node.parentElement) {
      if (getComputedStyle(node).opacity !== "1" || node.getAnimations().some(animation => animation.playState === "running" || animation.pending))
        return false
    }
    return true
  })).toBe(true)
}

for (const locale of ["en-US", "zh-CN"] as const) {
  test(`published Project method becomes an exact reviewed ordinary Protocol (${locale}, AI off, phone)`, async ({ page, request }, testInfo) => {
    test.setTimeout(300_000)
    page.setDefaultTimeout(15_000)
    const messages = JSON.parse(await readFile(new URL(`../../../packages/shared/src/locales/langs/${locale === "en-US" ? "en-us" : "zh-cn"}.json`, import.meta.url), "utf8"))
    const labels = messages.page.analysisProtocolDraft
    const fixtures = await loadFixtures()
    const sources = fixtures.project_analysis.inputs
    expect(sources).toHaveLength(2)
    const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
    const signIn = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
    expect(signIn.ok()).toBe(true)
    const headers = { "Auth-Token": (await signIn.json()).token }
    async function call(path: string, data?: unknown) {
      const response = await request.fetch(`${api}${path}`, { method: data === undefined ? "GET" : "POST", headers, data })
      expect(response.ok(), `${path}: ${await response.text()}`).toBe(true)
      return response.json()
    }
    expect((await call("/instance")).ai_enabled).toBe(false)
    const unique = randomUUID().replaceAll("-", "").slice(0, 12)
    const methodTitle = `Synthetic reusable Project method ${locale} ${unique}`
    const protocolTitle = `Synthetic analysis Protocol ${locale} ${unique}`
    const privateQuestion = `Private run purpose must not become portable ${unique}`
    const exactRecords: Array<Array<{ record_id: string, record_version: number }>> = []
    for (const source of sources) {
      const data = await call(`/protocols/${source.protocol_id}/records?page_size=20`)
      expect(data.records).toHaveLength(3)
      exactRecords.push(data.records)
    }
    // This setup submits a real deterministic job and waits for the ordinary
    // worker. Neither results nor the promoted Protocol parser are mocked.
    const analysisPreview: ProjectAnalysisPreview = await call("/analyses/project/preview", {
      project_id: fixtures.project.id,
      question: privateQuestion,
      selection: {
        schema: "airalogy.project-selection.v1",
        inputs: sources.map((source, index) => ({ slot_id: `source_${index}`, protocol_id: source.protocol_id, selection: { mode: "selected", records: exactRecords[index].map(record => ({ id: record.record_id, version: record.record_version })) } })),
      },
      recipe: { kind: "project", schema_version: 1, mode: "evidence_synthesis", slots: sources.map((source, index) => ({ slot_id: `source_${index}`, label: `Synthetic ${source.value_field}`, recipe: { numeric_fields: [source.value_field], group_by: [], chart: "none" } })), join: null },
    })
    expect(analysisPreview.summary.counts).toEqual({ protocols: 2, records: 6 })
    const queued: ProjectAnalysisRun = await call("/analyses/project", { preview_id: analysisPreview.id, preview_digest: analysisPreview.preview_digest, client_idempotency_key: `protocol-draft-${unique}` })
    let computed: ProjectAnalysisRun = queued
    await expect.poll(async () => {
      computed = await call(`/analyses/${queued.id}`)
      return computed.status
    }, { timeout: 40_000 }).toBe("succeeded")
    expect(computed.result!.local_results.find(result => result.slot_id === "source_0")!.report.groups[0].fields[sources[0].value_field].mean).toBe(4)
    expect(computed.result!.local_results.find(result => result.slot_id === "source_1")!.report.groups[0].fields[sources[1].value_field].mean).toBeCloseTo(70 / 3)
    const savedMethod: ProjectAnalysisPipeline = await call("/analysis-pipelines", { run_id: computed.id, title: methodTitle })
    const workflowContext: WorkflowContext = await call(`/workflow-definitions/context?project_id=${fixtures.project.id}`)
    const publicationRequest: WorkflowAnalysisPublicationRequest = {
      project_id: fixtures.project.id,
      pipeline_revision_id: savedMethod.revisions!.find(revision => revision.revision === savedMethod.current_revision)!.id,
      protocol_version_id: null,
      title: methodTitle,
      project_inputs: sources.map((source, index) => ({ slot_id: `source_${index}`, protocol_id: source.protocol_id, protocol_version_ids: [workflowContext.protocols.find(protocol => protocol.id === source.protocol_id)!.versions[0].id] })),
    }
    const publicationPreview: WorkflowAnalysisPublicationPreview = await call("/workflow-analysis-methods/preview", publicationRequest)
    const publication: WorkflowAnalysisPublication = await call("/workflow-analysis-methods/confirm", { ...publicationRequest, preview_digest: publicationPreview.preview_digest, preview_token: publicationPreview.preview_token, idempotency_key: randomUUID() })
    expect(publication.engine_version).toBe("airalogy.project-analysis.v1")

    const pageErrors: string[] = []
    page.on("pageerror", error => pageErrors.push(error.message))
    await page.addInitScript(language => localStorage.setItem("lang", JSON.stringify({ data: language, expire: null })), locale)
    await page.setViewportSize({ width: 390, height: 844 })
    const projectPath = `/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}`
    const loaded = page.waitForResponse(response => response.url().includes("/workflow-definitions/context?") && response.ok())
    await page.goto(`${projectPath}/workflows`)
    await loaded
    await page.getByTestId("workflow-card-kind").locator("input[value=\"analysis\"]").check()
    await page.getByTestId("workflow-add-analysis-method").click()
    await selectVisibleOption(page, methodTitle)
    await expect(page.locator(".n-base-select-option:visible")).toHaveCount(0)
    const templateResponse = page.waitForResponse(response => response.url().endsWith("/analysis-protocol-drafts/template") && response.request().method() === "POST")
    await page.getByTestId("workflow-analysis-protocol-draft").click()
    const templateHttp = await templateResponse
    expect(templateHttp.ok(), await templateHttp.text()).toBe(true)
    const template: AnalysisProtocolTemplate = await templateHttp.json()
    expect(template.method_id).toBe(publication.id)
    expect(template.target_protocol_id).toBeNull()
    expect(Object.keys(template.files).sort()).toEqual(["analysis-method.json", "protocol.aimd", "protocol.toml"])
    const dialog = page.getByTestId("analysis-protocol-draft-dialog")
    await expect(dialog).toBeVisible()
    await expect(dialog).toContainText(labels.title)
    await expect(page.getByTestId("analysis-protocol-draft-destination")).toContainText(template.destination.name)
    const manifest = template.files["analysis-method.json"]
    const sourceIdentities = [privateQuestion, computed.id, savedMethod.id, publication.id, ...sources.map(source => source.protocol_id), ...exactRecords.flat().map(record => record.record_id)]
    for (const identity of sourceIdentities)
      expect(manifest).not.toContain(identity)
    await dialog.locator(".n-tabs-tab[data-name=\"analysis-method.json\"]").click()
    await expect(page.getByTestId("analysis-protocol-draft-manifest")).toHaveText(manifest)
    await expect(page.getByTestId("analysis-protocol-draft-manifest").locator("textarea,input,[contenteditable=true]")).toHaveCount(0)

    async function editMetadata(values: Record<string, string>) {
      await dialog.locator(".n-tabs-tab[data-name=\"protocol.toml\"]").click()
      const input = page.getByTestId("analysis-protocol-draft-toml").locator("textarea")
      await expect(input).toBeEditable()
      await input.fill(editToml(await input.inputValue(), values))
    }
    async function appendAimd(text: string) {
      await dialog.locator(".n-tabs-tab[data-name=\"protocol.aimd\"]").click()
      const editor = page.getByTestId("analysis-protocol-draft-aimd").locator(".monaco-editor:visible")
      await expect(editor).toBeVisible({ timeout: 30_000 })
      const input = editor.locator("textarea.inputarea")
      await input.focus()
      await input.press("ControlOrMeta+End")
      await page.keyboard.insertText(`\n\n${text}\n`)
      await expect(editor.locator(".view-lines")).toContainText(text)
    }
    async function saveDraft(current: AnalysisProtocolDraft | null, reason: string) {
      await page.getByTestId("analysis-protocol-draft-reason").locator("textarea").fill(reason)
      const prefix = current ? `/analysis-protocol-drafts/${current.id}/revisions` : "/analysis-protocol-drafts"
      const response = page.waitForResponse(response => response.url().endsWith(`${prefix}/preview`) && response.request().method() === "POST")
      await page.getByTestId("analysis-protocol-draft-preview-save").click()
      const http = await response
      expect(http.ok(), await http.text()).toBe(true)
      const preview: AnalysisProtocolPreview = await http.json()
      expect(preview.content.files["analysis-method.json"]).toBe(manifest)
      expect(preview.files_manifest).toEqual(fileManifest(preview.content.files))
      expect(preview.package_digest).toBe(packageDigest(preview.content.files))
      expect(preview.manifest_digest).toBe(sha256(canonical(JSON.parse(manifest))))
      expect(preview.destination).toEqual(template.destination)
      await expect(page.getByTestId("analysis-protocol-draft-preview")).toContainText(preview.package_digest)
      await expect(page.getByTestId("analysis-protocol-draft-confirm")).toBeDisabled()
      await page.getByTestId("analysis-protocol-draft-acknowledge").check()
      const confirmation = page.waitForResponse(response => response.url().endsWith(`${prefix}/confirm`) && response.request().method() === "POST")
      await page.getByTestId("analysis-protocol-draft-confirm").click()
      const confirmed = await confirmation
      expect(confirmed.ok(), await confirmed.text()).toBe(true)
      expect(confirmed.request().postDataJSON()).toMatchObject({ preview_digest: preview.preview_digest, preview_token: preview.preview_token, files: preview.content.files })
      const draft: AnalysisProtocolDraft = await confirmed.json()
      expect(draft.current_revision.files).toEqual(preview.content.files)
      expect(draft.current_revision.package_digest).toBe(preview.package_digest)
      expect(draft.state).toBe("draft")
      expect(draft.revision).toBe(current ? current.revision + 1 : 1)
      await expect(page.getByTestId("analysis-protocol-draft-state")).toHaveText(labels.states.draft)
      return draft
    }
    async function reviewDraft(draft: AnalysisProtocolDraft) {
      await expect(page.getByTestId("analysis-protocol-draft-approve")).toBeDisabled()
      await page.getByTestId("analysis-protocol-draft-review-note").locator("textarea").fill("Reviewed the exact files, portable recipe and sharing scope; this is not scientific validation.")
      await page.getByTestId("analysis-protocol-draft-review-acknowledge").check()
      const reviewedResponse = page.waitForResponse(response => response.url().endsWith(`/analysis-protocol-drafts/${draft.id}/review`) && response.request().method() === "POST")
      await page.getByTestId("analysis-protocol-draft-approve").click()
      const reviewedHttp = await reviewedResponse
      expect(reviewedHttp.ok(), await reviewedHttp.text()).toBe(true)
      expect(reviewedHttp.request().postDataJSON()).toMatchObject({ expected_revision: draft.revision, package_digest: draft.current_revision.package_digest, decision: "reviewed" })
      const reviewed: AnalysisProtocolDraft = await reviewedHttp.json()
      expect(reviewed.state).toBe("reviewed")
      await expect(page.getByTestId("analysis-protocol-draft-state")).toHaveText(labels.states.reviewed)
      return reviewed
    }
    async function publishDraft(draft: AnalysisProtocolDraft, screenshot: string) {
      const previewResponse = page.waitForResponse(response => response.url().endsWith(`/analysis-protocol-drafts/${draft.id}/publish/preview`) && response.request().method() === "POST")
      await page.getByTestId("analysis-protocol-draft-preview-publish").click()
      const previewHttp = await previewResponse
      expect(previewHttp.ok(), await previewHttp.text()).toBe(true)
      const preview: AnalysisProtocolPreview = await previewHttp.json()
      expect(preview.package_digest).toBe(draft.current_revision.package_digest)
      expect(preview.files_manifest).toEqual(fileManifest(draft.current_revision.files))
      await expect(page.getByTestId("analysis-protocol-draft-destination")).toContainText(preview.destination.visibility === "public" ? labels.publicScope : labels.privateScope)
      await expect(page.getByTestId("analysis-protocol-draft-confirm")).toBeDisabled()
      await page.getByTestId("analysis-protocol-draft-acknowledge").check()
      await stablePhoneSurface(page, page.getByTestId("analysis-protocol-draft-preview"))
      expect((await dialog.boundingBox())!.width).toBeLessThanOrEqual(358)
      await page.screenshot({ path: testInfo.outputPath(`${screenshot}-review-${locale}-phone.png`) })
      const publishedResponse = page.waitForResponse(response => response.url().endsWith(`/analysis-protocol-drafts/${draft.id}/publish`) && response.request().method() === "POST")
      await page.getByTestId("analysis-protocol-draft-confirm").click()
      const publishedHttp = await publishedResponse
      expect(publishedHttp.ok(), await publishedHttp.text()).toBe(true)
      expect(publishedHttp.request().postDataJSON()).toEqual({ expected_revision: draft.revision, package_digest: draft.current_revision.package_digest, preview_digest: preview.preview_digest, preview_token: preview.preview_token })
      const applied: AnalysisProtocolDraft = await publishedHttp.json()
      expect(applied.state).toBe("applied")
      expect(applied.current_revision.files).toEqual(draft.current_revision.files)
      await expect(page.getByTestId("analysis-protocol-draft-applied")).toContainText(applied.applied!.version)
      await expect(page.getByTestId("analysis-protocol-draft-open-protocol")).toHaveAttribute("href", `${projectPath}/protocols/${applied.applied!.protocol_uid}/protocol`)
      await stablePhoneSurface(page, page.getByTestId("analysis-protocol-draft-applied"))
      await page.screenshot({ path: testInfo.outputPath(`${screenshot}-result-${locale}-phone.png`) })
      return applied
    }
    async function inspectPublished(draft: AnalysisProtocolDraft) {
      const identity = draft.applied!
      const ordinary = await call(`/protocols/${identity.protocol_id}?version=${identity.version}`)
      expect(ordinary.aimd).toBe(draft.current_revision.files["protocol.aimd"].replaceAll("\r\n", "\n"))
      expect(ordinary.metadata.version).toBe(identity.version)
      expect(ordinary.records_count).toBe(0)
      expect(ordinary.assigners).toEqual({})
      expect(Object.keys(ordinary.json_schema.vars.properties).length).toBeGreaterThan(0)
      expect(ordinary.analysis_method_sources).toEqual([{ method_publication_id: publication.id, title: publication.title, draft_id: draft.id, draft_revision: draft.revision, protocol_version_id: identity.protocol_version_id, protocol_version: identity.version, package_digest: draft.current_revision.package_digest }])
      const download = await call(`/protocols/${identity.protocol_id}/download_package?version=${identity.version}`)
      const response = await request.get(new URL(download.url, api).href)
      expect(response.ok(), "The actual reviewed Protocol ZIP should be downloadable").toBe(true)
      const archive = await response.body()
      const files = packageFiles(archive)
      expect(files).toEqual(draft.current_revision.files)
      expect(packageDigest(files)).toBe(draft.current_revision.package_digest)
      expect(files["analysis-method.json"]).toBe(manifest)
      for (const identity of sourceIdentities)
        expect(files["analysis-method.json"]).not.toContain(identity)
      return { archive, ordinary }
    }

    await editMetadata({ id: `synthetic_analysis_${unique}`, name: protocolTitle, version: "0.1.0" })
    const marker = `Synthetic human instructions ${unique}; inspect actual data before drawing conclusions.`
    await appendAimd(marker)
    let draft = await saveDraft(null, "First explicit reusable Protocol draft")
    expect(draft.current_revision.files["protocol.aimd"]).toContain(marker)
    const firstRevision = draft.current_revision
    draft = await reviewDraft(draft)
    if (locale === "en-US") {
      await editMetadata({ name: `${protocolTitle} revised` })
      await expect(page.getByTestId("analysis-protocol-draft-preview-publish")).toBeDisabled()
      draft = await saveDraft(draft, "Revise the Protocol name after review")
      expect(draft.reviews).toHaveLength(1)
      const historyResponse = page.waitForResponse(response => response.url().endsWith(`/analysis-protocol-drafts/${draft.id}/revisions/1`) && response.request().method() === "GET")
      await page.getByTestId("analysis-protocol-draft-revision").click()
      await selectVisibleOption(page, messages.page.workflowDefinitions.revision.replace("{number}", "1"))
      const historical: AnalysisProtocolRevision = await (await historyResponse).json()
      expect(historical).toEqual(firstRevision)
      await expect(dialog).toContainText(labels.historical)
      await expect(page.getByTestId("analysis-protocol-draft-toml").locator("textarea")).toHaveValue(firstRevision.files["protocol.toml"])
      await expect(page.getByTestId("analysis-protocol-draft-toml").locator("textarea")).toHaveJSProperty("readOnly", true)
      await expect(page.getByTestId("analysis-protocol-draft-preview-save")).toHaveCount(0)
      await expect(page.getByTestId("analysis-protocol-draft-approve")).toHaveCount(0)
      await page.getByTestId("analysis-protocol-draft-revision").click()
      await selectVisibleOption(page, messages.page.workflowDefinitions.revision.replace("{number}", String(draft.revision)))
      await expect(page.getByTestId("analysis-protocol-draft-toml").locator("textarea")).toHaveJSProperty("readOnly", false)
      draft = await reviewDraft(draft)
    }
    const applied = await publishDraft(draft, "analysis-protocol")
    const firstPublished = await inspectPublished(applied)

    // Reopening uses the server's saved draft/revision history, not local OPFS
    // state or the analysis conversation. No new draft is silently created.
    await dialog.getByRole("button", { name: messages.common.close, exact: true }).click()
    await expect(dialog).toBeHidden()
    const reopenedResponse = page.waitForResponse(response => response.url().endsWith(`/analysis-protocol-drafts/${applied.id}`) && response.request().method() === "GET")
    await page.getByTestId("workflow-analysis-protocol-draft").click()
    const reopened: AnalysisProtocolDraft = await (await reopenedResponse).json()
    expect(reopened.id).toBe(applied.id)
    expect(reopened.revisions).toEqual(applied.revisions)
    await expect(page.getByTestId("analysis-protocol-draft-state")).toHaveText(labels.states.applied)
    await expect(page.getByTestId("analysis-protocol-draft-toml").locator("textarea")).toHaveJSProperty("readOnly", true)

    if (locale === "en-US") {
      const nextTemplateResponse = page.waitForResponse(response => response.url().endsWith("/analysis-protocol-drafts/template") && response.request().method() === "POST")
      await page.getByTestId("analysis-protocol-draft-next-version").click()
      const nextHttp = await nextTemplateResponse
      expect(nextHttp.ok(), await nextHttp.text()).toBe(true)
      expect(nextHttp.request().postDataJSON()).toEqual({ method_id: publication.id, target_protocol_id: applied.applied!.protocol_id })
      const next: AnalysisProtocolTemplate = await nextHttp.json()
      expect(next.target_protocol_id).toBe(applied.applied!.protocol_id)
      expect(next.base_protocol_version_id).toBe(applied.applied!.protocol_version_id)
      expect(next.files["protocol.toml"]).toMatch(/^version\s*=\s*"0\.1\.0"$/m)
      await expect(dialog).toContainText(labels.increaseVersion)
      await editMetadata({ version: "0.1.1" })
      await appendAimd(`Second explicitly approved version ${unique}.`)
      const nextDraft = await saveDraft(null, "Explicit version update to 0.1.1")
      expect(nextDraft.id).not.toBe(applied.id)
      expect(nextDraft.target_protocol_id).toBe(applied.applied!.protocol_id)
      const secondApplied = await publishDraft(await reviewDraft(nextDraft), "analysis-protocol-next-version")
      expect(secondApplied.applied!.protocol_id).toBe(applied.applied!.protocol_id)
      expect(secondApplied.applied!.protocol_version_id).not.toBe(applied.applied!.protocol_version_id)
      expect(secondApplied.applied!.version).toBe("0.1.1")
      await inspectPublished(secondApplied)
      const unchanged = await inspectPublished(applied)
      expect(unchanged.archive.equals(firstPublished.archive)).toBe(true)
      for (const field of ["aimd", "metadata", "json_schema", "analysis_method_sources"])
        expect(unchanged.ordinary[field]).toEqual(firstPublished.ordinary[field])
    }
    const unchangedRun: ProjectAnalysisRun = await call(`/analyses/${computed.id}`)
    expect(unchangedRun.result_digest).toBe(computed.result_digest)
    expect(unchangedRun.result).toEqual(computed.result)
    expect(pageErrors).toEqual([])
  })
}
