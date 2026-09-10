import { Buffer } from "node:buffer"
import { createRequire } from "node:module"
import Ajv from "ajv"
import { canonical, checkText } from "./contract.mjs"

const schema = createRequire(import.meta.url)("./application-selection.schema.json")
const ajv = new Ajv({ strict: true })
ajv.addSchema(schema)
const validators = new Map(Object.keys(schema.definitions).map(name => [name, ajv.compile({ $ref: `${schema.$id}#/definitions/${name}` })]))
export const metadataFields = ["name", "display_name", "bundle_id", "version", "build_version"]

export function selectionShape(name, value) {
  const text = canonical(value)
  if (Buffer.byteLength(text) > 65536 || /(?:aiinterface|aiauthor|aiinstall|aigw)_[\w-]{43}/.test(text) || !validators.get(name)?.(value))
    throw new Error("Invalid bounded application selection data")
  return value
}

export function validateApplicationCandidates(report) {
  selectionShape("report", report)
  const ids = new Set()
  for (const candidate of report.candidates) {
    if (ids.has(candidate.id))
      throw new Error("Candidate IDs must be unique")
    ids.add(candidate.id)
    for (const field of metadataFields) {
      if (candidate[field] !== null)
        checkText(candidate[field], 512)
    }
    if (candidate.info_sha256 === null && metadataFields.some(field => candidate[field] !== null))
      throw new Error("Unavailable metadata cannot acquire declared fields")
  }
  return report
}

export function validateApplicationAnalysis(analysis, report) {
  selectionShape("analysis", analysis)
  validateApplicationCandidates(report)
  const ids = new Set()
  for (const item of analysis.recommendations) {
    const candidate = report.candidates.find(candidate => candidate.id === item.candidate_id)
    if (!candidate || ids.has(item.candidate_id) || item.evidence_fields.some(field => candidate[field] === null))
      throw new Error("Recommendations must cite distinct supplied candidates and existing metadata")
    ids.add(item.candidate_id)
  }
  if (!analysis.recommendations.length && !analysis.missing_information.length)
    throw new Error("Explain what is missing instead of inventing a software match")
  return analysis
}
