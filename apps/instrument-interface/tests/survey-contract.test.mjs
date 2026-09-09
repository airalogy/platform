/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { digest } from "../src/contract.mjs"
import { assembleSurveyDefinition, validateSurveyAnalysis, validateSurveyReport } from "../src/survey-contract.mjs"
import { fixture } from "./fixture.mjs"

const report = JSON.parse(await readFile(new URL("fixtures/survey.json", import.meta.url), "utf8"))
const analysis = { summary: "A synthetic interface with a readable status.", features: [{ control_id: "observed.3", interpretation: "The visible status reads Ready; physical readiness is unknown.", basis: "observed", risk: "read_only" }], identity_control: "observed.1", read_controls: ["observed.3"], route: "browser", limitations: ["Only one snapshot; no operation tested."], missing_information: ["Vendor documentation and real instrument validation."] }

test("survey report schema, canonical digest and privacy/readback invariants are bounded", () => {
  validateSurveyReport(report)
  assert.equal(digest(report), "9d8a358b89858829cbbf99c21d6191203e818e702a45fc99cc9fdef80e54461e")
  for (const change of [
    item => item.controls.push(item.controls[0]),
    item => item.controls[1].read = "value",
    item => item.controls[1].value = "unapproved",
    item => item.controls[2].locator = item.controls[0].locator,
    item => item.target.path = "/private/source.html",
    item => item.controls[0].value = "x".repeat(131073),
  ]) {
    const invalid = structuredClone(report)
    change(invalid)
    assert.throws(() => validateSurveyReport(invalid))
  }
})

test("analysis cannot invent controls, actions, unconsented reads or a non-text identity", () => {
  validateSurveyAnalysis(analysis, report)
  for (const change of [
    item => item.features[0].control_id = "invented",
    item => item.features.push(item.features[0]),
    item => item.read_controls = ["observed.2"],
    item => item.read_controls = ["missing"],
    item => item.identity_control = "observed.2",
    item => item.actions = ["click"],
    item => item.features[0].basis = "verified_hardware",
  ]) {
    const invalid = structuredClone(analysis)
    change(invalid)
    assert.throws(() => validateSurveyAnalysis(invalid, report))
  }
  const ambiguous = structuredClone(report)
  ambiguous.controls[2].locator = null
  assert.throws(() => validateSurveyAnalysis(analysis, ambiguous))
})

test("assembly creates only an editable read definition and observed baseline, never an action plan", async () => {
  const { definition } = await fixture()
  const selected = { ...definition, capture_values: false }
  delete selected.target.identity
  const result = assembleSurveyDefinition(selected, report, analysis, report.preview_digest)
  assert.deepEqual(result.plan.steps, [])
  assert.ok(result.definition.controls.every(item => item.operations.length === 1 && item.operations[0] === "read"))
  assert.equal(result.definition.states[0].id, "observed")
  assert.equal(result.provenance.hardware_qualified, false)
  assert.throws(() => assembleSurveyDefinition(selected, report, analysis, "0".repeat(64)))
  assert.throws(() => assembleSurveyDefinition(selected, report, { ...analysis, identity_control: null }, report.preview_digest))
  selected.target.version = "different"
  assert.throws(() => assembleSurveyDefinition(selected, report, analysis, report.preview_digest))
})
