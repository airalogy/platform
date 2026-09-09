import { Buffer } from "node:buffer"
import { createRequire } from "node:module"
import Ajv from "ajv"
import { canonical, digest, validateDefinition, validateLocator } from "./contract.mjs"

const schema = createRequire(import.meta.url)("./survey.schema.json")
const ajv = new Ajv({ strict: true })
ajv.addSchema(schema)
const validators = new Map(Object.keys(schema.definitions).map(name => [name, ajv.compile({ $ref: `${schema.$id}#/definitions/${name}` })]))
export function surveyShape(name, value) {
  if (Buffer.byteLength(canonical(value)) > 131072 || !validators.get(name)?.(value))
    throw new Error(`Invalid bounded survey ${name}`)
  return value
}
export function validateSurveyReport(report) {
  surveyShape("report", report)
  const ids = new Set()
  const locators = new Set()
  for (const control of report.controls) {
    if (ids.has(control.id) || (control.read === null ? control.value !== null : control.read === "checked" ? typeof control.value !== "boolean" : typeof control.value !== "string"))
      throw new Error("Survey control IDs and readback types must agree")
    if (!report.capture_values && ["value", "checked"].includes(control.read))
      throw new Error("Survey values require explicit capture consent")
    if (control.locator) {
      validateLocator(control.locator)
      const signature = canonical(control.locator)
      if (locators.has(signature))
        throw new Error("Browser-verified locators must be unique")
      locators.add(signature)
    }
    ids.add(control.id)
  }
  return report
}
export function validateSurveyAnalysis(analysis, report) {
  surveyShape("analysis", analysis)
  validateSurveyReport(report)
  const controls = new Map(report.controls.map(item => [item.id, item]))
  const described = new Set()
  for (const feature of analysis.features) {
    if (!controls.has(feature.control_id) || described.has(feature.control_id))
      throw new Error("Analysis refers to an unknown or repeated observed control")
    described.add(feature.control_id)
  }
  for (const id of analysis.read_controls) {
    const control = controls.get(id)
    if (!control?.locator || !control.read)
      throw new Error("Only browser-addressable, consented readbacks can be selected")
  }
  if (analysis.identity_control !== null) {
    const control = controls.get(analysis.identity_control)
    if (!control?.locator || control.read !== "text" || typeof control.value !== "string" || !control.value.trim() || Buffer.byteLength(control.value) > 512)
      throw new Error("Identity requires a bounded observed text anchor; it is not hardware attestation")
  }
  return analysis
}
export function assembleSurveyDefinition(selection, report, analysis, previewDigest) {
  validateSurveyAnalysis(analysis, report)
  const target = { application: selection.target.application, version: selection.target.version, title: selection.target.title, locale: selection.target.locale, kind: selection.target.source.kind }
  if (report.preview_digest !== previewDigest || canonical(report.target) !== canonical(target) || report.capture_values !== selection.capture_values)
    throw new Error("Survey report no longer matches the reviewed local selection")
  if (analysis.identity_control === null)
    throw new Error("Select a reviewed visible identity anchor before preparing a runnable definition")
  const ids = new Set([analysis.identity_control, ...analysis.read_controls])
  const chosen = report.controls.filter(item => ids.has(item.id))
  const identity = chosen.find(item => item.id === analysis.identity_control)
  const definition = {
    schema: "airalogy.browser-interface.v1",
    id: selection.id,
    target: { ...selection.target, identity: { locator: identity.locator, text: identity.value } },
    network: selection.network,
    blocked: selection.blocked,
    privacy: selection.privacy,
    limits: { ...selection.limits, max_steps: Math.max(chosen.length, 1) },
    controls: chosen.map(item => ({ id: item.id, locator: item.locator, read: item.read, operations: ["read"] })),
    states: [{ id: "observed", checks: [{ control_id: identity.id, equals: identity.value }] }],
  }
  validateDefinition(definition)
  return { definition, plan: { schema: "airalogy.interface-plan.v1", steps: [] }, provenance: { capture_digest: digest(report), analysis_digest: digest(analysis), baseline_only: true, actions_approved: false, hardware_qualified: false } }
}
