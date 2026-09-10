import { Buffer } from "node:buffer"
import { createRequire } from "node:module"
import Ajv from "ajv"
import { canonical, digest, validateStep } from "./contract.mjs"

const schema = createRequire(import.meta.url)("./exploration.schema.json")
const ajv = new Ajv({ allErrors: false, strict: true })
ajv.addSchema(schema)
const validators = new Map(Object.keys(schema.definitions).map(name => [name, ajv.compile({ $ref: `${schema.$id}#/definitions/${name}` })]))
export function shape(name, value) {
  if (Buffer.byteLength(canonical(value)) > 131072 || !validators.get(name)?.(value))
    throw new Error(`Invalid bounded exploration ${name}`)
  return value
}
export function validatePolicy(policy, definition) {
  shape("policy", policy)
  const signatures = new Set()
  for (const step of policy.actions) {
    validateStep(step, definition)
    if (definition.target.source.kind === "url" && step.operation !== "read")
      throw new Error("Live URL exploration is observation-only")
    if (signatures.has(canonical(step)))
      throw new Error("Approved actions must be distinct")
    signatures.add(canonical(step))
  }
  for (const check of policy.success) {
    if (!definition.controls.some(control => control.id === check.control_id))
      throw new Error("Success refers to an undeclared control")
  }
  return policy
}
export const fingerprint = request => digest(Object.fromEntries(Object.entries(request).filter(([key]) => key !== "fingerprint")))
export function validateRequest(request) {
  shape("request", request)
  if (fingerprint(request) !== request.fingerprint)
    throw new Error("Exploration request fingerprint changed")
  validateSpec(request.spec)
  return request
}
export function validateSpec(spec) {
  shape("spec", spec)
  const controls = new Map(spec.controls.map(item => [item.id, item]))
  const states = new Set(spec.states.map(item => item.id))
  if (controls.size !== spec.controls.length || states.size !== spec.states.length)
    throw new Error("Exploration controls and states must be unique")
  if (spec.target.kind === "native_macos_simulation" && spec.controls.some(control => !["text", "value"].includes(control.read)))
    throw new Error("Native simulation supports text/value readbacks only")
  for (const check of [...spec.success, ...spec.states.flatMap(item => item.checks)]) {
    const control = controls.get(check.control_id)
    if (!control || (control.read === "checked" ? typeof check.equals !== "boolean" : typeof check.equals !== "string"))
      throw new Error("State checks must match selected control readbacks")
  }
  const signatures = new Set()
  for (const step of spec.actions) {
    const control = controls.get(step.control_id)
    if (!control || !states.has(step.before) || !states.has(step.after) || signatures.has(canonical(step)))
      throw new Error("Unknown or repeated exploration action")
    signatures.add(canonical(step))
    if (step.operation === "fill" ? control.read !== "value" || !Object.hasOwn(step, "value") : Object.hasOwn(step, "value"))
      throw new Error("Only literal parameter fills accept a value")
    if (["read", "fill"].includes(step.operation) && step.before !== step.after)
      throw new Error("Read and fill cannot declare a state transition")
    if (spec.target.kind === "url" && step.operation !== "read")
      throw new Error("Live URL exploration is observation-only")
  }
  return spec
}
export function validateObservation(observation, spec) {
  shape("observation", observation)
  const ids = spec.controls.map(item => item.id).sort().join(",")
  if (observation.local_preview_digest !== spec.local_preview_digest || Object.keys(observation.values).sort().join(",") !== ids || Object.keys(observation.enabled).sort().join(",") !== ids)
    throw new Error("Observation does not match the approved interface")
  for (const control of spec.controls) {
    if (control.read === "checked" ? typeof observation.values[control.id] !== "boolean" : typeof observation.values[control.id] !== "string")
      throw new Error("Unexpected control readback type")
  }
  const states = spec.states.filter(state => matches(state.checks, observation))
  if (states.length !== 1 || states[0].id !== observation.state)
    throw new Error("Unknown or ambiguous observed state")
  return observation
}
export function matches(checks, observation) {
  return checks.every(check => observation.values[check.control_id] === check.equals)
}
export function validateProposal(proposal, spec, observation) {
  shape("proposal", proposal)
  validateObservation(observation, spec)
  if (proposal.kind === "act") {
    const action = spec.actions[proposal.action_index]
    if (proposal.action_index === null || !action || proposal.missing_information.length || action.before !== observation.state || !observation.enabled[action.control_id])
      throw new Error("Proposal exceeds the current approved actions")
  }
  else if (proposal.action_index !== null || (proposal.kind === "finish" ? proposal.missing_information.length || !matches(spec.success, observation) : !proposal.missing_information.length)) {
    throw new Error("Completion or missing-information claim is not supported")
  }
  return proposal
}
