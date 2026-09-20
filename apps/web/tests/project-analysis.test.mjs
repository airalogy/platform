/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { readFileSync } from "node:fs"
import test from "node:test"
import ts from "typescript"
import { isProxy, ref, toRaw } from "vue"

const source = readFileSync(new URL("../src/utils/project-analysis.ts", import.meta.url), "utf8")
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext }, reportDiagnostics: true })
assert.deepEqual(compiled.diagnostics, [])
const { emptyProjectStatistics, newProjectAnalysisSlot, projectAnalysisLatest, projectAnalysisIdentity, projectJoinFieldsCompatible, projectAnalysisValidation, isProjectAnalysis, copyProjectRecordReferences, createProjectEditorLoader } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString("base64")}`)

test("late method completion cannot clear a newer explicit rerun or its loading state", async () => {
  let loading = false
  let rerunOfId
  const loader = createProjectEditorLoader(value => (loading = value))
  const first = Promise.withResolvers()
  const pending = loader.load(() => first.promise, () => {
    rerunOfId = undefined
  })
  assert.equal(loading, true)
  loader.cancel()
  rerunOfId = "original-run"
  assert.equal(loading, false)
  first.resolve({ id: "old-method" })
  assert.equal(await pending, false)
  assert.equal(rerunOfId, "original-run")
  assert.equal(loading, false)
  const stale = Promise.withResolvers()
  const latest = Promise.withResolvers()
  let applied
  const oldLoad = loader.load(() => stale.promise, value => (applied = value))
  const newLoad = loader.load(() => latest.promise, value => (applied = value))
  stale.resolve("old")
  assert.equal(await oldLoad, false)
  assert.equal(loading, true)
  assert.equal(applied, undefined)
  latest.resolve("new")
  assert.equal(await newLoad, true)
  assert.equal(applied, "new")
  assert.equal(loading, false)
})

test("stale method failures are ignored; current failures still stop loading and surface", async () => {
  let loading = false
  const loader = createProjectEditorLoader(value => (loading = value))
  const delayed = Promise.withResolvers()
  const pending = loader.load(() => delayed.promise, () => assert.fail("must not apply"))
  loader.cancel()
  delayed.reject(new Error("old request"))
  assert.equal(await pending, false)
  await assert.rejects(loader.load(() => Promise.reject(new Error("current failure")), () => {}), /current failure/)
  assert.equal(loading, false)
})

test("Record picker copies exact refs through nested Vue proxies, reopen and deselection", () => {
  const picked = ref([])
  for (const id of ["first", "second", "third"]) {
    picked.value = picked.value.filter(record => record.id !== id)
    picked.value.push({ id, version: 4 })
  }
  assert.equal(toRaw(picked.value).some(isProxy), true)
  assert.throws(() => structuredClone(toRaw(picked.value)), { name: "DataCloneError" })
  const submitted = copyProjectRecordReferences(picked.value)
  assert.deepEqual(submitted, [{ id: "first", version: 4 }, { id: "second", version: 4 }, { id: "third", version: 4 }])
  assert.equal(submitted.some(isProxy), false)
  assert.deepEqual(structuredClone(submitted), submitted)
  const reopened = ref(copyProjectRecordReferences(ref(submitted).value))
  reopened.value = reopened.value.filter(record => record.id !== "second")
  const next = copyProjectRecordReferences(reopened.value)
  assert.deepEqual(next.map(record => record.id), ["first", "third"])
  assert.equal(submitted.length, 3)
  assert.deepEqual(copyProjectRecordReferences([{ id: "private", version: 7, data: "excluded" }]), [{ id: "private", version: 7 }])
})

function fixture(mode = "evidence_synthesis") {
  const stats = () => ({ ...emptyProjectStatistics(), numeric_fields: ["measurement"] })
  const recipe = { kind: "project", schema_version: 1, mode, slots: [{ slot_id: "input_1", label: "Concentration", recipe: stats() }, { slot_id: "input_2", label: "Response", recipe: stats() }], join: null }
  const selection = { schema: "airalogy.project-selection.v1", inputs: recipe.slots.map((slot, index) => ({ slot_id: slot.slot_id, protocol_id: `protocol-${index}`, selection: { mode: "selected", filters: {}, records: [{ id: `record-${index}`, version: 4 }] } })) }
  const fields = { input_1: [{ key: "sample", type: "string" }, { key: "measurement", type: "number", unit: "mg/L" }], input_2: [{ key: "sample", type: "string" }, { key: "measurement", type: "number", unit: "%" }] }
  if (mode === "relational")
    recipe.join = { left_slot_id: "input_1", right_slot_id: "input_2", kind: "inner", cardinality: "one_to_one", keys: [{ left_field: "sample", right_field: "sample" }], missing_key_policy: "error", duplicate_key_policy: "error", semantic_alignment_confirmed: true, outputs: [{ output_id: "concentration", slot_id: "input_1", field: "measurement", semantic_label: "Measured concentration", unit: "mg/L" }, { output_id: "response", slot_id: "input_2", field: "measurement", semantic_label: "Response rate", unit: "%" }], recipe: { ...stats(), numeric_fields: ["concentration", "response"] } }
  return { recipe, selection, fields }
}

test("Project discrimination isolates existing built-in and Compute reports", () => {
  assert.equal(isProjectAnalysis({ recipe: { kind: "project" } }), true)
  for (const value of [null, {}, { recipe: null }, { recipe: emptyProjectStatistics() }, { recipe: { kind: "compute" } }])
    assert.equal(isProjectAnalysis(value), false)
})
test("new source IDs preserve existing slots", () => {
  const existing = fixture().recipe.slots
  const prior = structuredClone(existing)
  assert.equal(newProjectAnalysisSlot(existing, "Other evidence").slot_id, "input_3")
  assert.deepEqual(existing, prior)
})
test("only an explicit latest action expands saved exact Record selections", () => {
  const { selection } = fixture()
  const previous = structuredClone(selection)
  const latest = projectAnalysisLatest(selection)
  assert.deepEqual(selection, previous)
  assert.deepEqual(latest.inputs.map(input => input.selection), [{ mode: "latest", filters: {} }, { mode: "latest", filters: {} }])
  assert.deepEqual(latest.inputs.map(input => [input.slot_id, input.protocol_id]), selection.inputs.map(input => [input.slot_id, input.protocol_id]))
  assert.notEqual(projectAnalysisIdentity(latest), projectAnalysisIdentity(selection))
})
test("canonical identity retains method meaning while ignoring object key order", () => {
  const { recipe } = fixture("relational")
  const reordered = Object.fromEntries(Object.entries(recipe).reverse())
  assert.equal(projectAnalysisIdentity(recipe), projectAnalysisIdentity(reordered))
  reordered.join = { ...recipe.join, semantic_alignment_confirmed: false }
  assert.notEqual(projectAnalysisIdentity(recipe), projectAnalysisIdentity(reordered))
})
test("typed keys never coerce bool, numeric, string or incompatible units", () => {
  assert.equal(projectJoinFieldsCompatible({ type: ["string", "null"] }, { type: "string" }), true)
  for (const [left, right] of [[{ type: "number" }, { type: "integer" }], [{ type: "number" }, { type: "boolean" }], [{ type: "string" }, { type: "number" }], [{ type: "number", unit: "mg" }, { type: "number", unit: "g" }], [{ type: "string", unsupported_reason: "FileId" }, { type: "string" }]])
    assert.equal(projectJoinFieldsCompatible(left, right), false)
})
test("independent evidence permits distinct units without pooling columns", () => {
  const { recipe, selection, fields } = fixture()
  const previous = structuredClone(recipe)
  assert.equal(projectAnalysisValidation(recipe, selection, fields), null)
  assert.deepEqual(recipe, previous)
  recipe.join = fixture("relational").recipe.join
  assert.equal(projectAnalysisValidation(recipe, selection, fields), "invalidJoin")
})
test("sources must be distinct and exact selections cannot be empty", () => {
  const { recipe, selection, fields } = fixture()
  selection.inputs[1].protocol_id = selection.inputs[0].protocol_id
  assert.equal(projectAnalysisValidation(recipe, selection, fields), "invalidSlots")
  selection.inputs[1].protocol_id = "second"
  selection.inputs[1].selection.records = []
  assert.equal(projectAnalysisValidation(recipe, selection, fields), "invalidSlots")
})
test("typed joins require explicit semantics and preserve exact output units", () => {
  const { recipe, selection, fields } = fixture("relational")
  assert.equal(projectAnalysisValidation(recipe, selection, fields), null)
  recipe.join.semantic_alignment_confirmed = false
  assert.equal(projectAnalysisValidation(recipe, selection, fields), "confirmSemantics")
  recipe.join.semantic_alignment_confirmed = true
  recipe.join.outputs[0].unit = "g/L"
  assert.equal(projectAnalysisValidation(recipe, selection, fields), "invalidOutputs")
})
test("unsupported file fields and removed outputs cannot retain stale references", () => {
  const { recipe, selection, fields } = fixture("relational")
  fields.input_1[0].unsupported_reason = "FileId is not a Project scalar key"
  assert.equal(projectAnalysisValidation(recipe, selection, fields), "incompatibleKeys")
  delete fields.input_1[0].unsupported_reason
  recipe.join.outputs.splice(0, 1)
  assert.equal(projectAnalysisValidation(recipe, selection, fields), "invalidOutputs")
})
test("filters must reference the actual selected-version field catalog", () => {
  const { recipe, selection, fields } = fixture()
  recipe.slots[0].recipe.filters.push({ field: "not_here", op: "eq", value: 5 })
  assert.equal(projectAnalysisValidation(recipe, selection, fields), "invalidFields")
})
test("both locales disclose source privacy and human evidence boundaries", () => {
  const en = JSON.parse(readFileSync(new URL("../../../packages/shared/src/locales/langs/en-us.json", import.meta.url), "utf8")).page.projectAnalysis
  const zh = JSON.parse(readFileSync(new URL("../../../packages/shared/src/locales/langs/zh-cn.json", import.meta.url), "utf8")).page.projectAnalysis
  const keys = value => Object.entries(value).flatMap(([key, child]) => typeof child === "string" ? [key] : keys(child).map(subkey => `${key}.${subkey}`))
  assert.deepEqual(keys(en), keys(zh))
  assert.match(en.privateHint, /does not invoke Aira/)
  assert.match(en.interpretation.hint, /numerical report never changes/)
  assert.match(zh.semanticConfirmation, /科学对象或样本/)
})
