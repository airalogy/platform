/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { readFileSync } from "node:fs"
import test from "node:test"
import ts from "typescript"

const source = readFileSync(new URL("../src/utils/analysis-ai.ts", import.meta.url), "utf8")
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
  reportDiagnostics: true,
})
assert.deepEqual(compiled.diagnostics, [])
const { createAnalysisAIRequestId, analysisSelectionIdentity, canAdoptAnalysisDraft, canAdoptAnalysisComputeDraft, resolveAnalysisComputeMetric, resolveAnalysisMetric, shouldRecoverAnalysisAIRequest } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString("base64")}`)

function draft(selection = { mode: "latest", filters: { protocol_version: "1.0.0", q: "control" } }) {
  return { kind: "draft", state: "generated", protocol_id: "protocol", project_id: "project", source_selection: selection, output: { mode: "builtin", recipe: { schema_version: 1 } } }
}

test("request IDs are unique RFC4122 v4 UUIDs without secure-context randomUUID", () => {
  const ids = Array.from({ length: 100 }, () => createAnalysisAIRequestId())
  assert.equal(new Set(ids).size, ids.length)
  for (const id of ids)
    assert.match(id, /^[\da-f]{8}-[\da-f]{4}-4[\da-f]{3}-[89ab][\da-f]{3}-[\da-f]{12}$/)
})

test("explicit API rejections do not leave a permanently pending request", () => {
  for (const status of [400, 401, 403, 404, 409, 422, 429])
    assert.equal(shouldRecoverAnalysisAIRequest({ response: { status } }), false)
})

test("network timeouts and unknown server failures retain the same request for recovery", () => {
  for (const error of [null, new Error("timeout"), { code: "ECONNABORTED" }, { response: { status: 500 } }, { response: { status: 502 } }, { response: { status: 503 } }, { response: { status: 504 } }, { response: { status: "422" } }])
    assert.equal(shouldRecoverAnalysisAIRequest(error), true)
})

test("HTTP timeout and unknown client-error statuses remain uncertain to avoid duplicate model calls", () => {
  for (const status of [408, 402, 405, 410, 418, 499])
    assert.equal(shouldRecoverAnalysisAIRequest({ response: { status } }), true)
})

test("same filter semantics permit adoption regardless of property insertion order", () => {
  assert.equal(canAdoptAnalysisDraft(draft(), "protocol", "project", { mode: "latest", filters: { q: "control", protocol_version: "1.0.0" } }), true)
})

test("adoption cannot broaden applied filters, scope or pinned Record revisions", () => {
  const request = draft()
  for (const [protocol, project, selection] of [
    ["other", "project", request.source_selection],
    ["protocol", "other", request.source_selection],
    ["protocol", "project", { mode: "latest", filters: {} }],
    ["protocol", "project", { mode: "latest", filters: { q: "control", protocol_version: "2.0.0" } }],
    ["protocol", "project", null],
  ])
    assert.equal(canAdoptAnalysisDraft(request, protocol, project, selection), false)
  const selected = draft({ mode: "selected", filters: {}, records: [{ id: "a", version: 1 }] })
  assert.equal(canAdoptAnalysisDraft(selected, "protocol", "project", { mode: "selected", filters: {}, records: [{ id: "a", version: 2 }] }), false)
})

test("selected Record ordering is not a scope change, but record membership is", () => {
  const selection = { mode: "selected", filters: {}, records: [{ id: "b", version: 2 }, { id: "a", version: 1 }] }
  assert.equal(analysisSelectionIdentity(selection), analysisSelectionIdentity({ ...selection, records: [...selection.records].reverse() }))
  assert.notEqual(analysisSelectionIdentity(selection), analysisSelectionIdentity({ ...selection, records: selection.records.slice(1) }))
})

test("failed, generating, clarification and compute suggestions cannot execute as recipes", () => {
  for (const changes of [{ state: "failed" }, { state: "generating" }, { kind: "interpretation" }, { output: null }, { output: { mode: "clarification_required", recipe: null } }, { output: { mode: "compute_required", recipe: null } }]) {
    const request = { ...draft(), ...changes }
    assert.equal(canAdoptAnalysisDraft(request, "protocol", "project", request.source_selection), false)
  }
})

function evidence(value = 12) {
  const group = [{ field: "batch", type: "string", value: "control" }]
  const metric = { field: "mass", group_index: 0, statistic: "mean", value, unit: "mg", n: 2, row_count: 3, group }
  const result = { fields: [{ key: "mass", unit: "mg" }], groups: [{ key: group, row_count: 3, fields: { mass: { mean: value, count: 2, missing: 1, invalid: 0 } } }] }
  return { metric, result }
}

test("grounded numeric references use actual report statistics and preserve real null/zero", () => {
  for (const value of [12, null, 0]) {
    const { metric, result } = evidence(value)
    const original = structuredClone(result)
    const resolved = resolveAnalysisMetric(metric, result)
    assert.equal(resolved.value, value)
    assert.deepEqual(result, original)
  }
})

test("wrong model value, unit, n, group or statistic is rejected instead of replacing results", () => {
  const { metric, result } = evidence()
  for (const changes of [{ value: 99 }, { unit: "g" }, { n: 3 }, { row_count: 4 }, { group_index: 1 }, { field: "other" }, { statistic: "p_value" }, { group: [{ field: "batch", type: "string", value: "treatment" }] }])
    assert.equal(resolveAnalysisMetric({ ...metric, ...changes }, result), null)
})

test("sample counts have no measurement unit, while calculated measurements retain their unit", () => {
  const { metric, result } = evidence()
  assert.equal(resolveAnalysisMetric({ ...metric, statistic: "count", value: 2, unit: "" }, result).unit, "")
  assert.equal(resolveAnalysisMetric({ ...metric, statistic: "count", value: 2, unit: "mg" }, result), null)
  assert.equal(resolveAnalysisMetric(metric, result).unit, "mg")
})

test("compute draft adoption pins scope, exact environment revision and language without checking Runner readiness", () => {
  const request = { ...draft(), kind: "compute_draft", output: { mode: "compute", recipe: { kind: "compute", environment_revision_id: "env-rev-1", language: "python" } } }
  assert.equal(canAdoptAnalysisComputeDraft(request, "protocol", "project", request.source_selection, "env-rev-1", "python"), true)
  for (const [project, selection, environment, language] of [
    ["other", request.source_selection, "env-rev-1", "python"],
    ["project", { mode: "latest", filters: {} }, "env-rev-1", "python"],
    ["project", request.source_selection, "env-rev-2", "python"],
    ["project", request.source_selection, "env-rev-1", "r"],
    ["project", request.source_selection, undefined, "python"],
  ])
    assert.equal(canAdoptAnalysisComputeDraft(request, "protocol", project, selection, environment, language), false)
  for (const changes of [{ kind: "draft" }, { state: "generating" }, { state: "failed" }, { output: { mode: "clarification_required", recipe: null } }])
    assert.equal(canAdoptAnalysisComputeDraft({ ...request, ...changes }, "protocol", "project", request.source_selection, "env-rev-1", "python"), false)
  assert.equal(canAdoptAnalysisDraft(request, "protocol", "project", request.source_selection), false)
})

test("compute result pointers preserve exact stored scalars, RFC6901 escapes and array positions", () => {
  const result = { "a/b": { "~count": 0 }, "": null, "values": [false, "3", 3, 0.12345678912345678] }
  for (const [pointer, value] of [["/a~1b/~0count", 0], ["/", null], ["/values/0", false], ["/values/1", "3"], ["/values/2", 3], ["/values/3", 0.12345678912345678]])
    assert.deepEqual(resolveAnalysisComputeMetric({ pointer, value }, result), { pointer, value })
})

test("compute interpretation refuses invented, mistyped, inherited or nonscalar references", () => {
  const result = { values: [0, 3], bool: true, object: { count: 2 }, bad: Number.POSITIVE_INFINITY, large: Number.MAX_SAFE_INTEGER + 1 }
  for (const metric of [
    { pointer: "values/0", value: 0 },
    { pointer: "", value: result },
    { pointer: "/values/00", value: 0 },
    { pointer: "/values/-", value: 0 },
    { pointer: "/values/length", value: 2 },
    { pointer: "/values/1", value: "3" },
    { pointer: "/bool", value: 1 },
    { pointer: "/values/1", value: 99 },
    { pointer: "/object", value: result.object },
    { pointer: "/values", value: result.values },
    { pointer: "/object~2", value: null },
    { pointer: "/object~", value: null },
    { pointer: "/toString", value: Object.prototype.toString },
    { pointer: "/__proto__", value: Object.prototype },
    { pointer: "/bad", value: Number.POSITIVE_INFINITY },
    { pointer: "/missing", value: null },
    { pointer: "/large", value: Number.MAX_SAFE_INTEGER + 1 },
  ])
    assert.equal(resolveAnalysisComputeMetric(metric, result), null)
})
