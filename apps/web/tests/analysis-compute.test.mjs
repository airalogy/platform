/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { readFileSync } from "node:fs"
import test from "node:test"
import ts from "typescript"

const source = readFileSync(new URL("../src/utils/analysis-compute.ts", import.meta.url), "utf8")
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext }, reportDiagnostics: true })
assert.deepEqual(compiled.diagnostics, [])
const { isComputeAnalysisRecipe, isBuiltinAnalysisRun, parseAnalysisComputeParameters, analysisComputeRecipeIdentity, analysisComputeGovernance, validateAnalysisComputeRecipe, validateAnalysisComputeInputFiles, withAnalysisComputeInputFiles, analysisComputeInputFileFieldLabel } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString("base64")}`)

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

function attachmentFixture() {
  const base = fixture()
  return {
    ...base,
    inputs: [{ input_id: "measurement_file", field_path: ["var", "attachment"] }],
    context: {
      ...base.context,
      source: { record_count: 2, source_digest: "synthetic", filename: "records.json" },
      input_file_fields: [
        { field_path: ["var", "attachment"], title: "Measurements", file_extensions: ["csv"], nullable: true },
        { field_path: ["var", "raw.file"], title: "Raw data", file_extensions: null, nullable: false },
      ],
      input_file_limits: { max_files: 30, max_file_bytes: 268435456, max_total_bytes: 536870912, manifest_filename: "attachments.json" },
    },
  }
}

test("empty attachments preserve the exact legacy recipe JSON and method identity", () => {
  const { recipe } = fixture()
  assert.equal(JSON.stringify(withAnalysisComputeInputFiles(recipe, [])), JSON.stringify(recipe))
  assert.equal(analysisComputeRecipeIdentity({ ...recipe, input_files: [] }), analysisComputeRecipeIdentity(recipe))
  assert.equal(validateAnalysisComputeRecipe(recipe, fixture().context), null)
  assert.equal(Object.hasOwn(withAnalysisComputeInputFiles({ ...recipe, input_files: [{ input_id: "old", field_path: ["var", "old"] }] }, []), "input_files"), false)
})

test("explicit attachments change the method identity and serialize only field declarations", () => {
  const { recipe, inputs, context } = attachmentFixture()
  const withInputs = withAnalysisComputeInputFiles(recipe, inputs.map(input => ({ ...input, file_id: "private-file", url: "https://private.invalid" })))
  assert.deepEqual(withInputs.input_files, inputs)
  assert.notEqual(analysisComputeRecipeIdentity(recipe), analysisComputeRecipeIdentity(withInputs))
  assert.equal(validateAnalysisComputeRecipe(withInputs, context), null)
  assert.equal(JSON.stringify(withInputs).includes("private-file"), false)
  withInputs.input_files[0].field_path[1] = "changed"
  assert.equal(inputs[0].field_path[1], "attachment")
})

test("attachment declarations require authorized literal FileId fields and unique safe names", () => {
  const { inputs, context } = attachmentFixture()
  for (const input_id of ["", "Uppercase", "../private", "https://file", "has-hyphen", "x".repeat(25)])
    assert.equal(validateAnalysisComputeInputFiles([{ ...inputs[0], input_id }], context), "invalidInputFiles")
  for (const field_path of [["var", "unknown"], ["var", "raw", "file"], ["record", "attachment"], ["https://private.invalid"]])
    assert.equal(validateAnalysisComputeInputFiles([{ ...inputs[0], field_path }], context), "invalidInputFiles")
  assert.equal(validateAnalysisComputeInputFiles([inputs[0], { ...inputs[0], input_id: "second" }], context), "invalidInputFiles")
  assert.equal(validateAnalysisComputeInputFiles([inputs[0], { ...inputs[0], field_path: ["var", "raw.file"] }], context), "invalidInputFiles")
  assert.equal(validateAnalysisComputeInputFiles([{ input_id: "raw", field_path: ["var", "raw.file"] }], context), null)
  assert.equal(analysisComputeInputFileFieldLabel(context.input_file_fields[1]), "Raw data [raw.file] (*)")
})

test("actual attachment counts expand every selected Record and never truncate the source scope", () => {
  const { inputs, context } = attachmentFixture()
  context.source.record_count = 30
  assert.equal(validateAnalysisComputeInputFiles(inputs, context), null)
  context.source.record_count = 31
  assert.equal(validateAnalysisComputeInputFiles(inputs, context), "tooManyInputFiles")
  const twoFields = [...inputs, { input_id: "raw", field_path: ["var", "raw.file"] }]
  context.source.record_count = 15
  assert.equal(validateAnalysisComputeInputFiles(twoFields, context), null)
  context.source.record_count = 16
  assert.equal(validateAnalysisComputeInputFiles(twoFields, context), "tooManyInputFiles")
  assert.equal(context.source.record_count, 16)
  assert.equal(validateAnalysisComputeInputFiles(Array.from({ length: 17 }, () => inputs[0]), context), "invalidInputFiles")
})

test("missing catalogs fail closed for attachments without breaking older records-only methods", () => {
  const { inputs, context } = attachmentFixture()
  for (const missing of [{ ...context, input_file_fields: undefined }, { ...context, input_file_limits: undefined }]) {
    assert.equal(validateAnalysisComputeInputFiles(inputs, missing), "inputFilesUnavailable")
    assert.equal(validateAnalysisComputeInputFiles([], missing), null)
  }
})

test("Aira recipe adoption cannot introduce or replace explicit user attachment selections", () => {
  const { recipe, inputs } = attachmentFixture()
  const generated = { ...recipe, input_files: [{ input_id: "untrusted", field_path: ["var", "other"] }] }
  assert.deepEqual(withAnalysisComputeInputFiles(generated, inputs).input_files, inputs)
  assert.equal(Object.hasOwn(withAnalysisComputeInputFiles(generated, []), "input_files"), false)
})

test("attachment display and validation terminology exists in both supported locales", () => {
  const en = JSON.parse(readFileSync(new URL("../../../packages/shared/src/locales/langs/en-us.json", import.meta.url), "utf8")).page.analysis.compute
  const zh = JSON.parse(readFileSync(new URL("../../../packages/shared/src/locales/langs/zh-cn.json", import.meta.url), "utf8")).page.analysis.compute
  for (const key of ["inputFiles", "inputFilesHint", "inputFilesNone", "inputFilesAiHint", "inputFilesDeclarationHint", "inputFilesWorkflowHint", "inputFilesReceipt", "inputFilesUnavailable", "invalidInputFiles", "tooManyInputFiles"])
    assert.ok(en[key] && zh[key], key)
})
