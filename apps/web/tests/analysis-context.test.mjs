/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { readFileSync } from "node:fs"
import test from "node:test"
import ts from "typescript"

const source = readFileSync(new URL("../src/utils/analysis-context.ts", import.meta.url), "utf8")
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
  reportDiagnostics: true,
})
assert.deepEqual(compiled.diagnostics, [])
const { createAnalysisContextRequest, analysisFieldType, parseAnalysisFieldOperand } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString("base64")}`)

test("legacy context lookup remains GET only when no selection was supplied", () => {
  assert.deepEqual(createAnalysisContextRequest("protocol"), { url: "/protocols/protocol/analysis-context", method: "GET" })
})

test("default latest scope uses a selection-aware POST instead of latest-Schema GET", () => {
  const selection = { mode: "latest", filters: {} }
  assert.deepEqual(createAnalysisContextRequest("protocol", selection), { url: "/protocols/protocol/analysis-context", method: "POST", data: selection })
})

test("selection-aware lookup pins exact Record revisions and never adds a latest scope", () => {
  const selection = { mode: "selected", filters: {}, records: [{ id: "record", version: 2 }] }
  const request = createAnalysisContextRequest("protocol", selection)
  selection.records[0].version = 3
  assert.deepEqual(request, { url: "/protocols/protocol/analysis-context", method: "POST", data: { mode: "selected", filters: {}, records: [{ id: "record", version: 2 }] } })
})

test("saved Protocol-version and keyword filters survive context refresh unchanged", () => {
  const selection = { mode: "latest", filters: { protocol_version: "1.0.0", q: "baseline", version: 4 } }
  const request = createAnalysisContextRequest("protocol", selection)
  selection.filters.protocol_version = "2.0.0"
  assert.deepEqual(request.data.filters, { protocol_version: "1.0.0", q: "baseline", version: 4 })
})

test("missing or malformed inherited selection never becomes a GET or all-Records POST", () => {
  for (const selection of [null, {}, { mode: "all" }])
    assert.throws(() => createAnalysisContextRequest("protocol", selection))
})

test("historical numeric fields use the selected version type, not latest string metadata", () => {
  const historical = { key: "signal", title: "Signal", type: "number", protocol_version: "1.0.0" }
  const latest = { ...historical, type: "string", protocol_version: "2.0.0" }
  assert.equal(parseAnalysisFieldOperand("12.5", historical), 12.5)
  assert.equal(parseAnalysisFieldOperand("12.5", latest), "12.5")
})

test("nullable historical scalar metadata preserves numeric filter types", () => {
  const field = { key: "signal", title: "Signal", type: ["integer", "null"] }
  assert.equal(analysisFieldType(field), "integer")
  assert.equal(parseAnalysisFieldOperand("4", field), 4)
  assert.throws(() => parseAnalysisFieldOperand("4.1", field))
})

test("incompatible or missing fields cannot silently fall back to string operands", () => {
  for (const field of [undefined, { type: "unsupported" }, { type: ["number", "string"] }, { type: "number", unsupported_reason: "Conflicting units across selected versions" }]) {
    assert.equal(analysisFieldType(field), "unsupported")
    assert.throws(() => parseAnalysisFieldOperand("12.5", field))
  }
})

test("numeric and boolean operands remain strict after catalogue resolution", () => {
  for (const value of ["", "  ", "Infinity", "NaN", "many"])
    assert.throws(() => parseAnalysisFieldOperand(value, { type: "number" }))
  assert.equal(parseAnalysisFieldOperand("true", { type: "boolean" }), true)
  assert.equal(parseAnalysisFieldOperand("false", { type: "boolean" }), false)
  assert.throws(() => parseAnalysisFieldOperand("1", { type: "boolean" }))
})
