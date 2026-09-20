/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { readFileSync } from "node:fs"
import test from "node:test"
import { compileTemplate, parse } from "@vue/compiler-sfc"
import ts from "typescript"
import { computed, nextTick, ref, watch } from "vue"

function compile(source) {
  const result = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext }, reportDiagnostics: true })
  assert.deepEqual(result.diagnostics, [])
  return result.outputText
}
const apiSource = readFileSync(new URL("../src/service/api/analysis-protocol-drafts.ts", import.meta.url), "utf8")
const requests = []
const api = await import(`data:text/javascript;base64,${Buffer.from(compile(apiSource).replace("import { request } from \"../request\";", "const request = async config => { globalThis.__analysisProtocolRequests.push(config); return { data: { accepted: true }, error: null } };")).toString("base64")}`)
globalThis.__analysisProtocolRequests = requests
const component = readFileSync(new URL("../src/views/analysis/components/analysis-protocol-draft-modal.vue", import.meta.url), "utf8")
const componentDescriptor = parse(component).descriptor
const originalFiles = { "protocol.toml": "[airalogy_protocol]\nname = \"Assay analysis\"\nversion = \"0.1.0\"\n", "protocol.aimd": "# Assay analysis\n", "analysis-method.json": "{\"recipe\":{\"numeric_fields\":[\"signal\"]}}\n" }
const method = { id: "method", project_id: "project", title: "Assay analysis", digest: "m".repeat(64), engine_version: "airalogy.analysis.v1" }
const destination = { project_id: "project", name: "Research Project", visibility: "private", lab_uid: "lab", project_uid: "project" }
function draftFixture(revision = 1, state = "draft", files = originalFiles) {
  const current = { draft_id: "draft", revision, files: { ...files }, package_digest: "a".repeat(64), manifest_digest: "b".repeat(64), method_digest: method.digest, reason: "Prepare this method for reuse", created_by_user_id: "author", created_at: "2026-09-14T00:00:00Z" }
  return { id: "draft", project_id: "project", method_id: "method", target_protocol_id: null, base_protocol_version_id: null, created_by_user_id: "author", revision, state, current_revision: current, revisions: [{ ...current, files: undefined }], reviews: [], applied: null, destination, permissions: { can_edit: true, can_review: true, can_publish: true } }
}
function previewFixture(files) {
  return { preview_digest: "c".repeat(64), preview_token: "exact-preview-token", expires_at: "2026-09-14T00:30:00Z", content: { method_id: "method", project_id: "project", files }, package_digest: "a".repeat(64), manifest_digest: "b".repeat(64), destination, files_manifest: Object.entries(files).map(([path, content]) => ({ path, size_bytes: Buffer.byteLength(content), sha256: "d".repeat(64) })) }
}
let harnessCounter = 0
async function harness(overrides = {}) {
  const props = { show: false, method: structuredClone(method) }
  const calls = []
  const defaults = {
    fetchAnalysisProtocolTemplate: async () => ({ ...method, method_id: method.id, target_protocol_id: null, base_protocol_version_id: null, files: { ...originalFiles }, destination, permissions: { can_create: true } }),
    fetchAnalysisProtocolDrafts: async () => ({ items: [] }),
    fetchAnalysisProtocolDraft: async () => draftFixture(),
    fetchAnalysisProtocolRevision: async (_, revision) => draftFixture(revision).current_revision,
    previewAnalysisProtocolDraft: async payload => previewFixture(payload.files),
    previewAnalysisProtocolRevision: async (_, payload) => previewFixture(payload.files),
    confirmAnalysisProtocolDraft: async payload => draftFixture(1, "draft", payload.files),
    confirmAnalysisProtocolRevision: async (_, payload) => draftFixture(payload.expected_revision + 1, "draft", payload.files),
    reviewAnalysisProtocolDraft: async (_, payload) => draftFixture(payload.expected_revision, payload.decision),
    previewAnalysisProtocolPublish: async () => previewFixture(originalFiles),
    publishAnalysisProtocolDraft: async () => ({ ...draftFixture(1, "applied"), applied: { protocol_id: "formal", protocol_version_id: "formal-v1", version: "0.1.0", lab_uid: "lab", project_uid: "project", protocol_uid: "formal" } }),
    ...overrides,
  }
  const bindings = {
    ...api,
    ...Object.fromEntries(Object.entries(defaults).map(([name, callback]) => [name, async (...args) => {
      calls.push({ name, args: JSON.parse(JSON.stringify(args)) })
      return callback(...args)
    }])),
    defineProps: () => props,
    defineEmits: () => () => {},
    useI18n: () => ({ t: key => key }),
    useRouter: () => ({ resolve: value => ({ href: `/protocol/${value.params.protocolUid}` }) }),
    useDialog: () => ({ warning: config => config.onPositiveClick() }),
    ref,
    computed,
    watch,
    onBeforeUnmount: () => {},
    onBeforeRouteLeave: () => {},
    onBeforeRouteUpdate: () => {},
    createWorkflowId: () => `attempt-${calls.length}`,
    window: { addEventListener: () => {}, removeEventListener: () => {} },
  }
  const id = `__analysisProtocolHarness${++harnessCounter}`
  globalThis[id] = bindings
  const preamble = `const { ${Object.keys(bindings).join(",")} } = globalThis.${id};\n`
  const source = compile(componentDescriptor.scriptSetup.content).replace(/^import .*?;\n/gm, "")
  const exports = "export { props, draft, files, reason, preview, key, uncertain, error, dirty, historical, canEdit, canReview, viewedRevision, reviewAcknowledged, reviewNote, acknowledged, acceptDraft, newDraft, openDraft, openRevision, reloadDraft, editFile, previewSave, confirmPreview, clearPreview, review, previewPublish, appliedHref };"
  const ui = await import(`data:text/javascript;base64,${Buffer.from(preamble + source + exports).toString("base64")}`)
  props.show = true
  return { ui, calls }
}

test("Protocol promotion supports only declared builtin/Project engines, not Compute or unknown engines", () => {
  for (const engine_version of ["airalogy.analysis.v1", "airalogy.project-analysis.v1"])
    assert.equal(api.supportsAnalysisProtocolDraft({ engine_version }), true)
  for (const value of [null, {}, { engine_version: "airalogy.compute.analysis.v1" }, { engine_version: "future" }])
    assert.equal(api.supportsAnalysisProtocolDraft(value), false)
})

test("only existing AIMD and TOML text can change; manifest and exact file set remain unchanged", () => {
  const edited = api.editAnalysisProtocolFile(originalFiles, "protocol.aimd", "# Updated description\n")
  assert.notEqual(edited, originalFiles)
  assert.equal(originalFiles["protocol.aimd"], "# Assay analysis\n")
  assert.equal(edited["analysis-method.json"], originalFiles["analysis-method.json"])
  for (const path of ["analysis-method.json", "model.py", "../protocol.toml", "PROTOCOL.TOML"])
    assert.equal(api.editAnalysisProtocolFile(originalFiles, path, "changed"), originalFiles)
  const empty = {}
  assert.equal(api.editAnalysisProtocolFile(empty, "protocol.toml", "injected"), empty)
})

test("draft fingerprint preserves exact text and revision reason, regardless of file-map ordering", () => {
  const value = api.analysisProtocolDraftFingerprint(originalFiles, "reason")
  assert.equal(api.analysisProtocolDraftFingerprint(Object.fromEntries(Object.entries(originalFiles).reverse()), "reason"), value)
  assert.notEqual(api.analysisProtocolDraftFingerprint(originalFiles, "different reason"), value)
  assert.notEqual(api.analysisProtocolDraftFingerprint({ ...originalFiles, "protocol.aimd": originalFiles["protocol.aimd"].trim() }, "reason"), value)
})

test("review and publish identify only the exact saved package and revision, never client-generated ZIPs", async () => {
  requests.length = 0
  const draft = draftFixture(3)
  const review = api.analysisProtocolReviewRequest(draft, "reviewed", "Confirmed sharing scope")
  assert.deepEqual(review, { expected_revision: 3, package_digest: "a".repeat(64), decision: "reviewed", note: "Confirmed sharing scope" })
  await api.reviewAnalysisProtocolDraft(draft.id, review)
  const publication = { ...api.analysisProtocolPublishRequest(draft), preview_digest: "c".repeat(64), preview_token: "receipt" }
  await api.publishAnalysisProtocolDraft(draft.id, publication)
  assert.equal(requests[0].url, "/analysis-protocol-drafts/draft/review")
  assert.equal(requests[1].url, "/analysis-protocol-drafts/draft/publish")
  assert.deepEqual(requests[1].data, publication)
  assert.equal(Object.hasOwn(requests[1].data, "files"), false)
  assert.equal(Object.hasOwn(requests[1].data, "file"), false)
})

test("a save preview freezes exact files and keeps the same idempotency key after an uncertain response", async () => {
  let attempt = 0
  const { ui, calls } = await harness({ confirmAnalysisProtocolDraft: async (payload) => {
    if (++attempt === 1)
      throw Object.assign(new Error("Response was lost"), { response: { status: 503 } })
    return draftFixture(1, "draft", payload.files)
  } })
  await ui.newDraft()
  ui.reason.value = "Prepare reusable method"
  ui.editFile("protocol.aimd", "# Explicitly shared method\n")
  await ui.previewSave()
  assert.equal(ui.canEdit.value, false)
  ui.editFile("protocol.aimd", "cannot change frozen preview")
  assert.equal(ui.files.value["protocol.aimd"], "# Explicitly shared method\n")
  ui.acknowledged.value = true
  await ui.confirmPreview()
  assert.equal(ui.uncertain.value, true)
  await ui.confirmPreview()
  const confirmations = calls.filter(call => call.name === "confirmAnalysisProtocolDraft")
  assert.equal(confirmations.length, 2)
  assert.deepEqual(confirmations[0].args, confirmations[1].args)
  assert.equal(ui.draft.value.revision, 1)
  assert.equal(ui.preview.value, null)
  assert.equal(ui.uncertain.value, false)
})

test("editing a reviewed package blocks publication and saves a fresh Draft revision", async () => {
  const { ui, calls } = await harness()
  ui.acceptDraft(draftFixture(2, "reviewed"))
  ui.editFile("protocol.toml", `${originalFiles["protocol.toml"]}description = "Changed scope"\n`)
  await ui.previewPublish()
  assert.equal(calls.some(call => call.name === "previewAnalysisProtocolPublish"), false)
  await ui.previewSave()
  ui.acknowledged.value = true
  await ui.confirmPreview()
  assert.equal(ui.draft.value.revision, 3)
  assert.equal(ui.draft.value.state, "draft")
  assert.equal(calls.find(call => call.name === "confirmAnalysisProtocolRevision").args[1].expected_revision, 2)
})

test("review requires explicit acknowledgement, a note, current revision, and backend capability", async () => {
  const { ui, calls } = await harness()
  ui.acceptDraft(draftFixture())
  await ui.review("reviewed")
  assert.equal(calls.length, 0)
  ui.reviewNote.value = "Checked scope and manifest"
  ui.reviewAcknowledged.value = true
  assert.equal(ui.canReview.value, true)
  ui.draft.value.permissions.can_review = false
  await ui.review("reviewed")
  assert.equal(calls.length, 0)
  ui.draft.value.permissions.can_review = true
  await ui.review("reviewed")
  assert.equal(ui.draft.value.state, "reviewed")
  assert.equal(calls[0].args[1].package_digest, "a".repeat(64))
})

test("historical revisions are read-only; applied packages create next-version drafts without mutating old revisions", async () => {
  const { ui, calls } = await harness()
  const draft = draftFixture(2)
  draft.revisions.unshift({ ...draftFixture(1).current_revision, files: undefined })
  ui.acceptDraft(draft)
  await ui.openRevision(1)
  assert.equal(ui.historical.value, true)
  assert.equal(ui.canEdit.value, false)
  ui.editFile("protocol.toml", "invalid history mutation")
  assert.equal(ui.files.value["protocol.toml"], originalFiles["protocol.toml"])
  await ui.previewPublish()
  assert.equal(calls.some(call => call.name === "previewAnalysisProtocolPublish"), false)
  ui.acceptDraft(draftFixture(2, "applied"))
  assert.equal(ui.canEdit.value, false)
  await ui.newDraft("formal-protocol")
  assert.equal(calls.at(-1).name, "fetchAnalysisProtocolTemplate")
  assert.deepEqual(calls.at(-1).args, ["method", "formal-protocol"])
})

test("uncertain review can reload saved state without repeating the approval action", async () => {
  const { ui, calls } = await harness({ reviewAnalysisProtocolDraft: async () => {
    throw Object.assign(new Error("Response was lost"), { response: { status: 503 } })
  }, fetchAnalysisProtocolDraft: async () => draftFixture(1, "reviewed") })
  ui.acceptDraft(draftFixture())
  ui.reviewNote.value = "Checked sharing"
  ui.reviewAcknowledged.value = true
  await ui.review("reviewed")
  assert.equal(ui.uncertain.value, true)
  await ui.reloadDraft()
  assert.equal(ui.uncertain.value, false)
  assert.equal(ui.draft.value.state, "reviewed")
  assert.equal(calls.filter(call => call.name === "reviewAnalysisProtocolDraft").length, 1)
})

test("reviewed package publication confirms the saved revision and returns the ordinary Protocol link", async () => {
  const { ui, calls } = await harness()
  ui.acceptDraft(draftFixture())
  ui.reviewNote.value = "Checked exact reusable package"
  ui.reviewAcknowledged.value = true
  await ui.review("reviewed")
  await ui.previewPublish()
  assert.equal(ui.canEdit.value, false)
  await ui.confirmPreview()
  assert.equal(calls.some(call => call.name === "publishAnalysisProtocolDraft"), false)
  ui.acknowledged.value = true
  await ui.confirmPreview()
  assert.deepEqual(calls.find(call => call.name === "publishAnalysisProtocolDraft").args, ["draft", { expected_revision: 1, package_digest: "a".repeat(64), preview_digest: "c".repeat(64), preview_token: "exact-preview-token" }])
  assert.equal(ui.draft.value.state, "applied")
  assert.equal(ui.canEdit.value, false)
  assert.equal(ui.appliedHref.value, "/protocol/formal")
})

test("draft controls have complete matching English and Chinese text", () => {
  const locales = ["en-us", "zh-cn"].map(locale => JSON.parse(readFileSync(new URL(`../../../packages/shared/src/locales/langs/${locale}.json`, import.meta.url), "utf8")).page.analysisProtocolDraft)
  const flatten = value => Object.entries(value).flatMap(([key, text]) => typeof text === "object" ? flatten(text).map(([nested, text]) => [`${key}.${nested}`, text]) : [[key, text]])
  const english = flatten(locales[0])
  const chinese = flatten(locales[1])
  assert.deepEqual(english.map(([key]) => key), chinese.map(([key]) => key))
  assert.ok([...english, ...chinese].every(([, value]) => typeof value === "string" && value.trim().length > 0))
})

test("modal template compiles, keeps manifest readonly and contains no local ZIP/OPFS publishing path", async () => {
  assert.deepEqual(compileTemplate({ source: componentDescriptor.template.content, filename: "analysis-protocol-draft-modal.vue", id: "analysis-protocol-draft" }).errors, [])
  assert.doesNotMatch(component, /applyProtocol|compressFiles|saveProjectData|createInitialFileData|postUploadProtocol|useInstanceStore/)
  assert.match(component, /analysis-protocol-draft-manifest/)
  assert.match(component, /:readonly="!canEdit"/)
  const { ui } = await harness()
  const invalid = draftFixture()
  invalid.project_id = "different-project"
  assert.throws(() => ui.acceptDraft(invalid), /scope mismatch/)
  await nextTick()
})
