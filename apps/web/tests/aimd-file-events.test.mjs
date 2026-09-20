/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { readFileSync } from "node:fs"
import test from "node:test"
import ts from "typescript"

const source = readFileSync(new URL("../src/utils/aimd-file-events.ts", import.meta.url), "utf8")
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext }, reportDiagnostics: true })
assert.deepEqual(compiled.diagnostics, [])
const helperModuleUrl = `data:text/javascript;base64,${Buffer.from(compiled.outputText).toString("base64")}`
const { previewFileFieldChange, previewFileTarget, syncPreviewFileEvent } = await import(helperModuleUrl)
const reference = "airalogy.id.file.synthetic-source.json"
const attachment = { id: "synthetic-source", airalogy_file_id: reference, filename: "original.json", url: "/authorized/original" }
const target = { scope: "research_variable", prop: "attachment" }
const localFile = { id: "local", name: "original.json", status: "pending" }

test("upload selection updates immediately but only finished uploads request dependent calculations", () => {
  const selected = { ...target, value: { type: "add", file: { fileList: [{ id: "local", name: "original.json", status: "pending" }] } } }
  const before = structuredClone(selected)
  const pending = previewFileFieldChange("preview-file-change", selected)
  assert.equal(pending.shouldAssign, false)
  assert.deepEqual(pending.value, selected.value.file.fileList)
  assert.notEqual(pending.value, selected.value.file.fileList)
  assert.notEqual(pending.value[0], selected.value.file.fileList[0])
  const uploaded = previewFileFieldChange("preview-file-uploaded", { ...target, value: attachment, fileInfo: localFile, assigner: { mode: "auto" }, dependent: [{ scope: "research_variable", name: "result" }] }, pending.value)
  assert.equal(uploaded.shouldAssign, true)
  assert.equal(uploaded.value.airalogy_file_id, reference)
  assert.notEqual(uploaded.value, attachment)
  assert.deepEqual(uploaded.dependent, [{ scope: "research_variable", name: "result" }])
  assert.deepEqual(selected, before)
})

test("a parent-only bridge preserves uploads, deletion and replacement without any mounted field item", () => {
  const model = { research_variable: { attachment: { value: [localFile] } } }
  const updates = []
  const apply = (change) => {
    updates.push(change)
    model.research_variable[change.prop].value = change.value
  }
  assert.equal(syncPreviewFileEvent("preview-file-uploaded", { ...target, value: attachment, fileInfo: localFile }, model, apply), true)
  assert.equal(model.research_variable.attachment.value.airalogy_file_id, reference)
  assert.equal(syncPreviewFileEvent("preview-file-change", { ...target, value: { type: "remove", file: { fileList: [] } } }, model, apply), true)
  assert.equal(model.research_variable.attachment.value, null)
  assert.equal(updates[1].shouldAssign, true)
  const replacement = { ...attachment, id: "replacement", airalogy_file_id: "airalogy.id.file.replacement.json" }
  syncPreviewFileEvent("preview-file-change", { ...target, value: { type: "add", file: { fileList: [localFile] } } }, model, apply)
  syncPreviewFileEvent("preview-file-uploaded", { ...target, value: replacement, fileInfo: localFile }, model, apply)
  assert.equal(updates.length, 4)
  assert.equal(model.research_variable.attachment.value.airalogy_file_id, replacement.airalogy_file_id)
})

test("deleted, replaced and already completed uploads reject late responses without any update", () => {
  const payload = { ...target, value: attachment, fileInfo: localFile }
  for (const current of [null, [], [{ ...localFile, id: "new-upload" }], [{ ...localFile, status: "removed" }], attachment, [attachment]]) {
    assert.equal(previewFileFieldChange("preview-file-uploaded", payload, current), undefined)
  }
  assert.equal(previewFileFieldChange("preview-file-uploaded", { ...target, value: attachment }, [localFile]), undefined)
  assert.equal(previewFileFieldChange("preview-file-uploaded", { ...payload, value: { id: "no-file-reference" } }, [localFile]), undefined)
})

test("metadata hydration keeps the exact current FileId and never requests calculations", () => {
  for (const current of [reference, { airalogy_file_id: reference }, [{ airalogy_file_id: reference }]]) {
    const hydrated = previewFileFieldChange("preview-file-metadata", { ...target, value: attachment }, current)
    assert.equal(hydrated.shouldAssign, false)
    assert.equal(hydrated.value.airalogy_file_id, reference)
  }
  for (const current of [null, [localFile], "airalogy.id.file.another.json"])
    assert.equal(previewFileFieldChange("preview-file-metadata", { ...target, value: attachment }, current), undefined)
})

test("file target lookup uses literal table names and columns, not another same-name field", () => {
  const model = { research_variable: { "sample.group": { value: [{ "file.column": attachment }] }, "attachment": { value: "unchanged" } } }
  const located = previewFileTarget(model, { scope: "var_table", prop: "file.column", info: { group: "sample.group", row: 0 } })
  assert.equal(located.owner[located.key], attachment)
  located.owner[located.key] = null
  assert.equal(model.research_variable["sample.group"].value[0]["file.column"], null)
  assert.equal(model.research_variable.attachment.value, "unchanged")
})

function compileFunction(relativePath, name) {
  const file = readFileSync(new URL(relativePath, import.meta.url), "utf8")
  const text = relativePath.endsWith(".vue") ? file.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1] : file
  const parsed = ts.createSourceFile(name, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  let declaration
  function visit(node) {
    if (!declaration && ts.isFunctionDeclaration(node) && node.name?.text === name)
      declaration = node
    ts.forEachChild(node, visit)
  }
  visit(parsed)
  assert.ok(declaration, `${name} must remain testable`)
  return ts.transpileModule(declaration.getText(parsed).replace(/^export /, ""), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.None } }).outputText
}

const handlerCode = compileFunction("../src/components/custom/aimd/composables/useAIMDHelpers.ts", "useAIMDFileHandlers")
const handlerModule = `import { previewFileFieldChange, previewFileTarget } from "${helperModuleUrl}";\n${handlerCode}\nexport { useAIMDFileHandlers };`
const { useAIMDFileHandlers: createHandlers } = await import(`data:text/javascript;base64,${Buffer.from(handlerModule).toString("base64")}`)

test("the actual emitter preserves table location and rename identity for strings, objects and arrays", () => {
  for (const current of [reference, attachment, [{ ...attachment, id: reference }]]) {
    const model = { research_variable: { samples: { value: [{ attachment: current }, { attachment: "unchanged" }] } } }
    const table = { value: { samples: [{ attachment: { model: { value: current } } }] } }
    const events = []
    const handlers = createHandlers(model, table, { value: {} }, {}, { emit: (...args) => events.push(args) }, { value: false }, false)
    handlers.handleRename("var_table", "attachment", { id: attachment.id, filename: "renamed.json", url: "/renamed" }, { group: "samples", row: 0 })
    const value = model.research_variable.samples.value[0].attachment
    assert.equal((Array.isArray(value) ? value[0] : value).airalogy_file_id, reference)
    assert.equal(events.length, 1)
    assert.equal(events[0][0], "preview-file-renamed")
    assert.equal(model.research_variable.samples.value[1].attachment, "unchanged")
    assert.equal(table.value.samples[0].attachment.model.value, value)
    assert.equal(model.var_table, undefined)
  }
})

test("the actual emitter ignores late upload responses and keeps readonly handlers non-mutating", () => {
  const model = { research_variable: { attachment: { value: [localFile] } } }
  const events = []
  const readonly = { value: false }
  const handlers = createHandlers(model, { value: {} }, { value: {} }, {}, { emit: (...args) => events.push(args) }, readonly, false)
  handlers.handleFileChange({ ...target, id: "card", fileInfo: { file: { ...localFile, status: "removed" }, fileList: [] } })
  handlers.handleUploadFile({ ...target, type: "file", file: attachment, rawFile: localFile })
  assert.equal(model.research_variable.attachment.value, null)
  assert.equal(events.length, 1)
  model.research_variable.attachment.value = [localFile]
  handlers.handleUploadFile({ ...target, type: "file", file: attachment, rawFile: localFile })
  assert.equal(events.length, 2)
  assert.equal(events[1][1].fileInfo.id, localFile.id)
  handlers.handleUploadFile({ ...target, type: "file", file: attachment, rawFile: localFile })
  assert.equal(events.length, 2)
  readonly.value = true
  const before = structuredClone(model)
  handlers.handleFileChange({ ...target, id: "card", fileInfo: { file: { ...localFile, status: "removed" }, fileList: [] } })
  handlers.handleRename(target.scope, target.prop, { id: attachment.id, filename: "blocked.json" })
  assert.deepEqual(model, before)
  assert.equal(events.length, 2)
})

test("Naive finish then uploaded events update the always-mounted canonical owner exactly once", () => {
  const model = { research_variable: { attachment: { value: null } } }
  const canonical = structuredClone(model)
  const updates = []
  const bus = { emit: (event, payload) => syncPreviewFileEvent(event, payload, canonical, (change) => {
    updates.push(change)
    const location = previewFileTarget(canonical, change)
    location.owner[location.key] = change.value
  }) }
  const handlers = createHandlers(model, { value: {} }, { value: {} }, {}, bus, { value: false }, false)
  // Selection, the upload widget's onFinish/change, then uploaded:file.
  handlers.handleFileChange({ ...target, id: "card", fileInfo: { file: localFile, fileList: [localFile] } })
  const finished = { ...localFile, status: "finished" }
  handlers.handleFileChange({ ...target, id: "card", fileInfo: { file: finished, fileList: [finished] } })
  handlers.handleUploadFile({ ...target, type: "file", file: attachment, rawFile: localFile })
  assert.equal(canonical.research_variable.attachment.value.airalogy_file_id, reference)
  assert.equal(model.research_variable.attachment.value.airalogy_file_id, reference)
  assert.equal(updates.filter(change => change.shouldAssign).length, 1)
})

test("rename sends the filename in the existing HTTP query contract", async () => {
  const code = compileFunction("../src/service/api/project-protocols.ts", "putRenameAssets")
  const requestModule = `export const requests = [];\nconst request = async (payload) => { requests.push(payload); return {}; };\n${code}\nexport { putRenameAssets };`
  const { putRenameAssets, requests } = await import(`data:text/javascript;base64,${Buffer.from(requestModule).toString("base64")}`)
  await putRenameAssets(attachment.id, "new name.json")
  const [sent] = requests
  assert.deepEqual(sent.params, { filename: "new name.json" })
  assert.equal(sent.data, undefined)
  assert.equal(sent.method, "PUT")
})

test("custom upload requests do not call widget finish after deletion or replacement", async () => {
  const code = compileFunction("../src/components/common/form-upload-file.vue", "customRequest")
  const module = `import { isCurrentFileUpload } from "${helperModuleUrl}";
export function createHarness() {
  const props = { disabled: false, endpoint: "/test-upload" };
  const mergedFileList = { value: [] };
  const emitted = [];
  const emit = (...args) => emitted.push(args);
  const startLoading = () => {};
  const endLoading = () => {};
  const message = { error() {} };
  let complete;
  const request = () => new Promise(resolve => { complete = resolve; });
  ${code}
  return { props, mergedFileList, emitted, customRequest, complete: result => complete({ data: result }) };
}`
  const { createHarness } = await import(`data:text/javascript;base64,${Buffer.from(module).toString("base64")}`)
  for (const next of [[], [{ ...localFile, id: "replacement" }], [localFile]]) {
    const harness = createHarness()
    harness.mergedFileList.value = [localFile]
    let finished = 0
    const pending = harness.customRequest({ file: { ...localFile, file: new Blob(["synthetic"]) }, onFinish: () => finished++, onError: () => assert.fail("unexpected upload error") })
    harness.mergedFileList.value = next
    harness.complete(attachment)
    await pending
    const accepted = next[0]?.id === localFile.id
    assert.equal(finished, accepted ? 1 : 0)
    assert.equal(harness.emitted.length, accepted ? 1 : 0)
  }
})

test("rename rechecks readonly and replacement after asynchronous validation", async () => {
  const code = compileFunction("../src/components/common/form-upload-file.vue", "handleRename")
  const filesSource = readFileSync(new URL("../src/utils/aimd-files.ts", import.meta.url), "utf8")
  const filesCompiled = ts.transpileModule(filesSource, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText
  const filesUrl = `data:text/javascript;base64,${Buffer.from(filesCompiled).toString("base64")}`
  const module = `import { aimdFileReference } from "${filesUrl}";
export function createHarness(file) {
  const props = { disabled: false };
  const mergedFileList = { value: [file] };
  const fileNameRecord = { [file.id]: "renamed.json" };
  let finishValidation;
  const formItemRecord = { [file.id]: { validate: () => new Promise(resolve => { finishValidation = resolve; }) } };
  const writes = [];
  const putRenameAssets = async (...args) => { writes.push(args); return { data: { ...file, filename: "renamed.json" } }; };
  const cacheAttachmentMetadata = () => {};
  const startLoading = () => {};
  const endLoading = () => {};
  const emit = () => {};
  const message = { error() {}, success() {} };
  const fileText = { value: {} };
  ${code}
  return { props, mergedFileList, writes, handleRename, finishValidation: () => finishValidation() };
}`
  const { createHarness } = await import(`data:text/javascript;base64,${Buffer.from(module).toString("base64")}`)
  for (const mode of ["readonly", "replacement", "current"]) {
    const harness = createHarness(attachment)
    const pending = harness.handleRename(attachment)
    if (mode === "readonly")
      harness.props.disabled = true
    if (mode === "replacement")
      harness.mergedFileList.value = [{ id: "another", airalogy_file_id: "airalogy.id.file.another.json" }]
    harness.finishValidation()
    await pending
    assert.equal(harness.writes.length, mode === "current" ? 1 : 0)
  }
})

test("drawer canonical edits and file deletion remain inert when readonly", async () => {
  const fieldChange = compileFunction("../src/views/project-protocols/modules/protocol/composables/useProtocolForm.ts", "handleFieldChange")
  const fileChange = compileFunction("../src/views/project-protocols/modules/protocol/composables/useProtocolForm.ts", "handleFileChange")
  const module = `export function createHarness() {
  const readonly = { value: true };
  const imageFileList = { value: [{ id: "original" }] };
  const imageFileListRecord = { value: {} };
  const events = [];
  const clearAssignerState = () => events.push("clear");
  const fieldEventBus = { emit: (...args) => events.push(args) };
  const emit = (...args) => events.push(args);
  const assignerLoadingRecord = { value: {} };
  ${fieldChange}
  ${fileChange}
  return { readonly, imageFileList, events, handleFieldChange, handleFileChange };
}`
  const { createHarness } = await import(`data:text/javascript;base64,${Buffer.from(module).toString("base64")}`)
  const harness = createHarness()
  harness.handleFieldChange({ ...target, value: null })
  harness.handleFileChange(target.scope, target.prop, { file: { id: "original", status: "removed" }, fileList: [] })
  assert.deepEqual(harness.events, [])
  assert.deepEqual(harness.imageFileList.value, [{ id: "original" }])
  harness.readonly.value = false
  harness.handleFileChange(target.scope, target.prop, { file: { id: "original", status: "removed" }, fileList: [] })
  assert.deepEqual(harness.imageFileList.value, [])
  assert.ok(harness.events.some(event => event[0] === "field:change" && event[1].value === null))
})

test("confirmed rename metadata wins over an older in-flight cache response", async () => {
  const cache = compileFunction("../src/service/api/attachments.ts", "cacheAttachmentMetadata")
  const getCached = compileFunction("../src/service/api/attachments.ts", "getCachedAttachment")
  const module = `export const cachedAttachments = new Map();
const AIRALOGY_FILE_ID_PREFIX = "airalogy.id.file.";
const parseAiralogyId = () => undefined;
const cleanupCache = () => {};
let complete;
const getAttachments = () => new Promise(resolve => { complete = resolve; });
export function completeRead(data) { complete({ data }); }
${cache}
${getCached}
export { cacheAttachmentMetadata, getCachedAttachment };
`
  const api = await import(`data:text/javascript;base64,${Buffer.from(module).toString("base64")}`)
  const pending = api.getCachedAttachment(attachment.id)
  const renamed = { ...attachment, filename: "renamed.json" }
  api.cacheAttachmentMetadata(renamed)
  api.completeRead(attachment)
  assert.equal(await pending, renamed)
  assert.equal(await api.getCachedAttachment(attachment.id), renamed)
  assert.equal(api.cachedAttachments.get(attachment.id).data, renamed)
})

test("a precision-constrained numeric input commits on blur, not programmatic file selection", async () => {
  const code = compileFunction("../src/components/custom/custom-input-number/custom-input-number.vue", "handleUpdateDisplayedValue")
  const module = `export const displayedValueRef = { value: "" };
const displayedValueInvalidRef = { value: false };
const props = { precision: 100, updateValueOnInput: true };
export const commits = [];
const deriveValueFromDisplayedValue = value => commits.push(value);
${code}
export { handleUpdateDisplayedValue };
`
  const input = await import(`data:text/javascript;base64,${Buffer.from(module).toString("base64")}`)
  input.handleUpdateDisplayedValue("7")
  assert.equal(input.displayedValueRef.value, "7")
  assert.deepEqual(input.commits, [])
})

test("rename preserves exact FileId and other metadata for strings, objects and upload arrays", () => {
  for (const current of [reference, attachment, [attachment]]) {
    const before = structuredClone(current)
    const renamed = previewFileFieldChange("preview-file-renamed", { ...target, value: { id: "synthetic-source", filename: "renamed.json", url: "/authorized/renamed" } }, current)
    const value = Array.isArray(renamed.value) ? renamed.value[0] : renamed.value
    assert.equal(value.airalogy_file_id, reference)
    assert.equal(value.filename, "renamed.json")
    assert.equal(value.name, "renamed.json")
    assert.equal(value.url, "/authorized/renamed")
    assert.equal(renamed.shouldAssign, false)
    assert.deepEqual(current, before)
  }
})

test("stale or mismatching rename callbacks cannot replace the current attachment", () => {
  for (const value of [
    { id: "another-file", filename: "renamed.json" },
    { id: attachment.id, airalogy_file_id: "airalogy.id.file.other.json" },
    { filename: "missing-identity.json" },
  ])
    assert.equal(previewFileFieldChange("preview-file-renamed", { ...target, value }, attachment), undefined)
})

test("table file events preserve row identity and do not affect another row", () => {
  const second = { ...attachment, id: "second", airalogy_file_id: "airalogy.id.file.second.json" }
  const model = { research_variable: { samples: { value: [{ attachment }, { attachment: second }] } } }
  const before = structuredClone(model)
  const updates = []
  const payload = { scope: "var_table", prop: "attachment", info: { group: "samples", row: 1, col: 0 }, value: { id: "second", filename: "second-renamed.json" } }
  assert.equal(syncPreviewFileEvent("preview-file-renamed", payload, model, change => updates.push(change)), true)
  assert.deepEqual(updates[0].info, payload.info)
  assert.equal(updates[0].value.airalogy_file_id, second.airalogy_file_id)
  assert.deepEqual(model, before)
})

test("unknown targets, invalid rows and unrelated events cannot create fields", () => {
  const model = { research_variable: { attachment: { value: attachment }, samples: { value: [{ attachment }] } } }
  let changed = 0
  const apply = () => changed++
  for (const payload of [
    { ...target, prop: "missing", value: attachment },
    { ...target, scope: "missing", value: attachment },
    { scope: "var_table", prop: "attachment", info: { group: "samples", row: -1 }, value: attachment },
    { scope: "var_table", prop: "attachment", info: { group: "samples", row: 2 }, value: attachment },
    { scope: "var_table", prop: "missing", info: { group: "samples", row: 0 }, value: attachment },
  ])
    assert.equal(syncPreviewFileEvent("preview-file-uploaded", payload, model, apply), false)
  assert.equal(syncPreviewFileEvent("preview-field-focus", target, model, apply), false)
  assert.equal(previewFileFieldChange("preview-file-change", { ...target, value: { type: "unknown" } }), undefined)
  assert.equal(changed, 0)
})
