/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { readFileSync } from "node:fs"
import test from "node:test"
import ts from "typescript"

const source = readFileSync(new URL("../src/utils/aimd-files.ts", import.meta.url), "utf8")
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext }, reportDiagnostics: true })
assert.deepEqual(compiled.diagnostics, [])
const { normalizeAimdUploadFiles, aimdFileReference, loadCurrentAimdFileMetadata } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString("base64")}`)

test("authorized attachment metadata supplies its actual filename to inline upload cards", () => {
  const api = { airalogy_file_id: "airalogy.id.file.synthetic.json", filename: "synthetic-workflow-input-v1.json", url: "/api/controlled-preview?token=synthetic", type: "application/json" }
  const before = structuredClone(api)
  for (const value of [api, [api]]) {
    const [file] = normalizeAimdUploadFiles(value)
    assert.equal(file.name, api.filename)
    assert.equal(file.id, api.airalogy_file_id)
    assert.equal(file.url, api.url)
    assert.equal(file.airalogy_file_id, api.airalogy_file_id)
  }
  assert.deepEqual(api, before)
})

test("existing upload names and local file objects are preserved without changing Record values", () => {
  const localFile = { synthetic: true }
  const upload = { id: "local-upload", name: "selected.csv", file: localFile, status: "pending" }
  const [normalized] = normalizeAimdUploadFiles([upload])
  assert.deepEqual(normalized, upload)
  assert.notEqual(normalized, upload)
  assert.equal(normalized.file, localFile)
  assert.equal(normalizeAimdUploadFiles({ ...upload, filename: "previous.csv" })[0].name, "selected.csv")
  assert.deepEqual(normalizeAimdUploadFiles("airalogy.id.file.synthetic.json"), [])
  assert.deepEqual(normalizeAimdUploadFiles([null, "airalogy.id.file.synthetic.json"]), [])
})

test("metadata requests use the exact current FileId and never an arbitrary URL", () => {
  const id = "airalogy.id.file.synthetic.json"
  for (const value of [id, [id], { airalogy_file_id: id }, [{ airalogy_file_id: id, url: "/old-preview" }]])
    assert.equal(aimdFileReference(value), id)
  for (const value of [null, {}, { url: "https://example.test/file" }, { airalogy_file_id: "https://example.test/file" }, []])
    assert.equal(aimdFileReference(value), undefined)
})

test("late attachment metadata cannot overwrite a replacement or an unmounted field", async () => {
  const original = "airalogy.id.file.original.json"
  for (const mode of ["replacement", "unmounted", "wrong-response", "current"]) {
    let current = original
    let active = true
    let complete
    const pending = loadCurrentAimdFileMetadata(() => current, () => new Promise((resolve) => {
      complete = resolve
    }), () => active)
    if (mode === "replacement")
      current = "airalogy.id.file.replacement.json"
    if (mode === "unmounted")
      active = false
    const metadata = { airalogy_file_id: mode === "wrong-response" ? "airalogy.id.file.wrong.json" : original, filename: "original.json" }
    complete(metadata)
    assert.equal(await pending, mode === "current" ? metadata : undefined)
  }
})

test("mobile Record layout is opt-in and retains both inline editing and the same field slot", () => {
  const layout = readFileSync(new URL("../src/components/custom/add-record-layout.vue", import.meta.url), "utf8")
  const form = readFileSync(new URL("../src/views/project-protocols/modules/protocol/protocol-add-record-form.vue", import.meta.url), "utf8")
  assert.match(layout, /responsive: false/)
  assert.match(layout, /props\.responsive && narrow\.value/)
  const compact = layout.slice(0, layout.indexOf("<n-split v-else"))
  assert.match(compact, /data-testid="record-main-content"[\s\S]*?<slot name="content"/)
  assert.match(compact, /<n-drawer[\s\S]*?<slot name="tabs"/)
  assert.match(compact, /data-testid="record-open-fields"/)
  assert.match(form, /<add-record-layout[\s\S]*?\sresponsive\s/)
})

test("the parent owns canonical file updates independently of lazy field-panel mounting", () => {
  const form = readFileSync(new URL("../src/views/project-protocols/modules/protocol/protocol-add-record-form.vue", import.meta.url), "utf8")
  const item = readFileSync(new URL("../src/views/project-protocols/modules/protocol/composables/useProtocolForm.ts", import.meta.url), "utf8")
  const queue = readFileSync(new URL("../src/views/project-protocols/modules/protocol/composables/useFieldEventBus.ts", import.meta.url), "utf8")
  assert.match(form, /provide\(protocolFileEventOwnerKey, true\)/)
  assert.match(form, /if \(!props\.readonly\)\s+syncPreviewFileEvent\(event, payload, fieldModel, handleFieldChange\)/)
  assert.match(item, /inject\(protocolFileEventOwnerKey, false\)/)
  assert.equal((item.match(/!parentOwnsFileEvents && !readonly\.value/g) || []).length, 3)
  assert.match(queue, /await updateField\(fieldModel, payload\)\s+if \(payload\.shouldAssign === false\) \{[\s\S]*?return\s+\}/)
})
