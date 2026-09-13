/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { readFileSync } from "node:fs"
import test from "node:test"
import ts from "typescript"

const source = readFileSync(new URL("../src/utils/analysis-compute.ts", import.meta.url), "utf8")
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext }, reportDiagnostics: true })
assert.deepEqual(compiled.diagnostics, [])
const { isComputeAnalysisRecipe, isBuiltinAnalysisRun, parseAnalysisComputeParameters, analysisComputeRecipeIdentity, analysisComputeGovernance, validateAnalysisComputeRecipe } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString("base64")}`)

function fixture() {
  return {
    recipe: { kind: "compute", environment_revision_id: "env-r1", language: "python", source_code: "print('example')", parameters: {}, output_files: [] },
    context: { max_source_bytes: 200000, environments: [{ revision_id: "env-r1", allowed_languages: ["python", "r"], authorized_runner_count: 1, ready_runner_count: 1, resource_limits: { max_output_bytes: 10000 } }] },
  }
}

test("compute methods and arbitrary results never enter built-in statistics rendering", () => {
  const { recipe } = fixture()
  assert.equal(isComputeAnalysisRecipe(recipe), true)
  assert.equal(isBuiltinAnalysisRun({ recipe, result: { computed_result: { answer: 42 } } }), false)
  assert.equal(isBuiltinAnalysisRun({ recipe: { schema_version: 1, numeric_fields: ["x"] } }), true)
})

test("manual Python and R are valid with an authorized environment, independent of AI", () => {
  const { recipe, context } = fixture()
  assert.equal(validateAnalysisComputeRecipe(recipe, context), null)
  assert.equal(validateAnalysisComputeRecipe({ ...recipe, language: "r" }, context), null)
})

test("missing environments and unauthorized Runners block; offline authorized Runners can queue", () => {
  const { recipe, context } = fixture()
  assert.equal(validateAnalysisComputeRecipe({ ...recipe, environment_revision_id: "other" }, context), "environmentUnavailable")
  context.environments[0].ready_runner_count = 0
  assert.equal(validateAnalysisComputeRecipe(recipe, context), null)
  context.environments[0].authorized_runner_count = 0
  assert.equal(validateAnalysisComputeRecipe(recipe, context), "noAuthorizedRunner")
})

test("source validation uses UTF-8 bytes and the selected environment language contract", () => {
  const { recipe, context } = fixture()
  context.max_source_bytes = 6
  assert.equal(validateAnalysisComputeRecipe({ ...recipe, source_code: "中文" }, context), null)
  assert.equal(validateAnalysisComputeRecipe({ ...recipe, source_code: "中文a" }, context), "invalidSource")
  assert.equal(validateAnalysisComputeRecipe({ ...recipe, source_code: "  " }, context), "invalidSource")
  assert.equal(validateAnalysisComputeRecipe({ ...recipe, language: "javascript" }, context), "invalidLanguage")
})

test("parameters must be a JSON object and cannot silently serialize Infinity as null", () => {
  assert.deepEqual(parseAnalysisComputeParameters('{"groups": [1, null, "a"]}'), { groups: [1, null, "a"] })
  for (const text of ["[]", "null", "5", "{bad}", '{"x":1e999}', '{"nested":[1e999]}'])
    assert.throws(() => parseAnalysisComputeParameters(text))
})

test("output declarations reject path traversal, duplicates and excessive output budgets", () => {
  const { recipe, context } = fixture()
  const output = { mount_name: "results.csv", asset_name: "Results", media_type: "text/csv", max_bytes: 1000 }
  assert.equal(validateAnalysisComputeRecipe({ ...recipe, output_files: [output] }, context), null)
  for (const outputs of [[{ ...output, mount_name: "../secret" }], [output, output], [{ ...output, max_bytes: 10000 }], [{ ...output, max_bytes: 0 }], [{ ...output, media_type: "not mime" }]])
    assert.equal(validateAnalysisComputeRecipe({ ...recipe, output_files: outputs }, context), "invalidOutputs")
})

test("saved methods compare semantically rather than object property insertion order", () => {
  const { recipe } = fixture()
  const reordered = Object.fromEntries(Object.entries(recipe).reverse())
  assert.equal(analysisComputeRecipeIdentity(recipe), analysisComputeRecipeIdentity(reordered))
  assert.notEqual(analysisComputeRecipeIdentity(recipe), analysisComputeRecipeIdentity({ ...recipe, source_code: "new_source" }))
})

test("prefilled currency without a selected cap is not submitted as an invalid half-budget", () => {
  assert.deepEqual(analysisComputeGovernance("", "USD", null), {})
  assert.deepEqual(analysisComputeGovernance("0", "USD", null), { max_cost: "0", budget_currency: "USD" })
  assert.deepEqual(analysisComputeGovernance("0.000000000000000001", "CNY", null), { max_cost: "0.000000000000000001", budget_currency: "CNY" })
})

test("budget and deadline validation never invents a currency or accepts stale limits", () => {
  for (const cost of ["-1", "Infinity", "1e9", "not-a-price"])
    assert.throws(() => analysisComputeGovernance(cost, "USD", null))
  assert.throws(() => analysisComputeGovernance("1", "", null))
  assert.throws(() => analysisComputeGovernance("1", "usd", null))
  assert.throws(() => analysisComputeGovernance("", "", 999, 1000))
  assert.throws(() => analysisComputeGovernance("", "", Number.POSITIVE_INFINITY, 1000))
  assert.equal(analysisComputeGovernance("", "", 2000, 1000).deadline_at, "1970-01-01T00:00:02.000Z")
})
