/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { readFileSync } from "node:fs"
import test from "node:test"
import { compileTemplate, parse } from "@vue/compiler-sfc"
import ts from "typescript"
import { computed, nextTick, ref, watch } from "vue"

function compile(source) {
  return ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText
}
const apiSource = readFileSync(new URL("../src/service/api/record-import.ts", import.meta.url), "utf8")
const requests = []
globalThis.__recordImportRequests = requests
const api = await import(`data:text/javascript;base64,${Buffer.from(compile(apiSource).replace("import { request } from \"../request\";", "const request = async config => { globalThis.__recordImportRequests.push(config); return { data: { ok: true } } };")).toString("base64")}`)
const component = parse(readFileSync(new URL("../src/views/project-protocols/modules/bulk-import-records-modal.vue", import.meta.url), "utf8")).descriptor
const good = { protocol_name: "Synthetic", protocol_version: "1.0.0", fields: [], row_count: 2, valid_count: 2, errors: [], preview_token: "signed-preview" }
let serial = 0
async function harness(preview = async () => good) {
  const calls = []
  const props = { protocolId: "protocol-a" }
  const bindings = {
    ...api,
    defineOptions: () => {},
    defineProps: () => props,
    defineEmits: () => (...args) => calls.push(["emit", ...args]),
    useClosableMessage: () => ({ warning() {}, success() {}, error() {} }),
    useI18n: () => ({ t: key => key, te: () => true }),
    fetchRecordImportTemplate: async () => ({ ...good, csv: "var.sample_id\r\n" }),
    previewRecordImport: async (...args) => {
      calls.push(["preview", ...args])
      return preview(...args)
    },
    postImportProtocolRecords: async (...args) => {
      calls.push(["import", ...args])
      return { imported_count: 2, record_ids: ["1", "2"] }
    },
    ref,
    computed,
    watch,
  }
  const key = `__recordImportHarness${++serial}`
  globalThis[key] = bindings
  const source = `const { ${Object.keys(bindings).join(",")} } = globalThis.${key};\n${compile(component.scriptSetup.content).replace(/^import .*?;\n/gm, "")}\nexport { showModal, template, loading, previewResult, acknowledged, canConfirm, importErrors, errorMessage, handlePreview, handleImport, handleFileListUpdate, resetState, parseImportErrors, issueMessage };`
  const ui = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`)
  ui.showModal.value = true
  await nextTick()
  await nextTick()
  ui.handleFileListUpdate([{ name: "sample.csv", file: new File(["sample_id\nS-001\n"], "sample.csv") }])
  return { ui, calls }
}

test("API downloads the current authorized template and previews without writing", async () => {
  await api.fetchRecordImportTemplate("p1")
  await api.previewRecordImport("p1", new File(["a\n1"], "test.csv"), "csv")
  assert.equal(requests[0].url, "/protocols/p1/records/import-template")
  assert.equal(requests[1].data.get("preview"), "true")
  assert.equal(requests[1].data.get("input_format"), "csv")
})

test("errors group by field, rule and physical line without losing locations", () => {
  const groups = api.groupImportIssues([
    { code: "required", column: "score", line_number: 4 },
    { code: "required", column: "score", line_number: 7 },
    { code: "range", column: "score", line_number: 8 },
  ])
  assert.equal(groups.length, 2)
  assert.deepEqual(groups[0].locations, [4, 7])
  assert.equal(groups[0].count, 2)
  assert.equal(api.canConfirmRecordImport(null), false)
  assert.equal(api.canConfirmRecordImport({ ...good, errors: [{ code: "required" }] }), false)
  assert.equal(api.canConfirmRecordImport({ ...good, preview_token: null }), false)
  assert.equal(api.importFieldType({ anyOf: [{ type: "number" }, { type: "null" }] }), "number / null")
})

test("successful preview still requires explicit confirmation and sends exact token", async () => {
  const { ui, calls } = await harness()
  await ui.handleImport()
  assert.equal(calls.length, 0)
  await ui.handlePreview()
  assert.equal(ui.canConfirm.value, true)
  await ui.handleImport()
  assert.equal(calls.filter(c => c[0] === "import").length, 0)
  ui.acknowledged.value = true
  await ui.handleImport()
  assert.equal(calls.find(c => c[0] === "import")[2].previewToken, "signed-preview")
  assert.equal(calls.find(c => c[0] === "emit")[1], "imported")
})

test("validation errors block import and changing files invalidates acknowledgement", async () => {
  const { ui, calls } = await harness(async () => ({ ...good, preview_token: null, errors: [{ code: "required", column: "score", row_number: 1 }] }))
  await ui.handlePreview()
  ui.acknowledged.value = true
  await ui.handleImport()
  assert.equal(calls.filter(c => c[0] === "import").length, 0)
  ui.handleFileListUpdate([])
  assert.equal(ui.previewResult.value, null)
  assert.equal(ui.acknowledged.value, false)
})

test("late preview cannot restore a closed/reset dialog", async () => {
  let finish
  const { ui } = await harness(() => new Promise((resolve) => {
    finish = resolve
  }))
  const pending = ui.handlePreview()
  ui.resetState()
  finish(good)
  await pending
  assert.equal(ui.previewResult.value, null)
  assert.equal(ui.canConfirm.value, false)
})

test("structured errors without raw engine text remain translatable", async () => {
  const { ui } = await harness()
  const errors = ui.parseImportErrors({ response: { data: { detail: { errors: [{ code: "stale_preview" }] } } } })
  assert.equal(errors[0].code, "stale_preview")
  assert.equal(ui.issueMessage(errors[0]), "page.protocol.records.importErrors.stale_preview")
})

test("template compiles and import UI has no mapping or silent skip controls", () => {
  const compiled = compileTemplate({ source: component.template.content, filename: "bulk-import-records-modal.vue", id: "import" })
  assert.deepEqual(compiled.errors, [])
  assert.ok(component.template.content.includes("downloadTemplate"))
  assert.ok(component.template.content.includes("acknowledged"))
  assert.ok(!component.template.content.includes("n-select"))
})
