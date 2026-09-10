import { Buffer } from "node:buffer"
import { randomUUID } from "node:crypto"
import { join } from "node:path"
import { performance } from "node:perf_hooks"
import { canonical, checkInteger, checkKey, checkList, checkObject, checkText, digest, validatePlan } from "./contract.mjs"
import { Evidence } from "./evidence.mjs"
import { validatePolicy } from "./exploration-contract.mjs"
import { validateNativeLocator, validateNativeSelection } from "./native-contract.mjs"
import { previewNativeSurvey } from "./native-survey.mjs"
import { nativeCall, nativeFailureCode, validateNativeBuild } from "./native-transport.mjs"

export function validateNativeInterface(value) {
  if (Buffer.byteLength(canonical(value)) > 131072)
    throw new Error("Native interface exceeds its bound")
  checkObject(value, ["schema", "id", "selection", "target", "controls", "states", "limits"])
  if (value.schema !== "airalogy.native-interface.v1")
    throw new Error("Select a separately reviewed native action definition")
  checkKey(value.id)
  validateNativeSelection(value.selection)
  checkObject(value.target, ["application", "version", "title", "locale", "source", "identity"])
  for (const field of ["application", "version", "title", "locale"]) {
    if (value.target[field] !== value.selection.target[field])
      throw new Error("Action target must match the selected native process")
  }
  checkObject(value.target.source, ["kind"])
  if (value.target.source.kind !== "native_macos_simulation")
    throw new Error("Native actions are limited to the owned simulator")
  checkObject(value.target.identity, ["locator", "text"])
  validateNativeLocator(value.target.identity.locator)
  checkText(value.target.identity.text)
  if (value.target.identity.locator.role !== "AXStaticText")
    throw new Error("Select an independent static identity anchor")
  const controls = new Map()
  const locators = new Set()
  for (const control of checkList(value.controls, 32, 1)) {
    checkObject(control, ["id", "locator", "read", "operations"])
    checkKey(control.id)
    validateNativeLocator(control.locator)
    const role = control.locator.role
    const allowed = role === "AXStaticText" ? ["read"] : role === "AXButton" ? ["read", "click"] : ["AXTextField", "AXTextArea"].includes(role) ? ["read", "fill"] : []
    const expectedRead = ["AXTextField", "AXTextArea"].includes(role) ? "value" : "text"
    const ops = checkList(control.operations, 2, 1)
    const key = canonical(control.locator)
    if (controls.has(control.id) || locators.has(key) || !allowed.length || control.read !== expectedRead || ops.some(op => !allowed.includes(op)) || new Set(ops).size !== ops.length || (expectedRead === "value" && !value.selection.capture_values))
      throw new Error("Native controls require unique, consented and role-matched operations")
    controls.set(control.id, control)
    locators.add(key)
  }
  const states = new Set()
  for (const state of checkList(value.states, 16, 1)) {
    checkObject(state, ["id", "checks"])
    checkKey(state.id)
    if (states.has(state.id))
      throw new Error("Native states must be distinct")
    states.add(state.id)
    for (const check of checkList(state.checks, 16, 1)) {
      checkObject(check, ["control_id", "equals"])
      if (!controls.has(check.control_id))
        throw new Error("Native state refers to an undeclared control")
      checkText(check.equals, 4096, true)
    }
  }
  checkObject(value.limits, ["duration_seconds", "max_steps", "step_timeout_ms"])
  checkInteger(value.limits.duration_seconds, 1, 900)
  checkInteger(value.limits.max_steps, 1, 40)
  checkInteger(value.limits.step_timeout_ms, 100, 10000)
  return value
}

function freeze(value) {
  if (value && typeof value === "object") {
    Object.values(value).forEach(freeze)
    Object.freeze(value)
  }
  return value
}

export async function previewNativeInterface(input, plan, policy = null) {
  const definition = validateNativeInterface(JSON.parse(canonical(input)))
  plan = validatePlan(JSON.parse(canonical(plan)), definition)
  const { manifest, directory } = await validateNativeBuild(definition.selection.build_file)
  const bundle = definition.selection.target.source.pin.bundle
  if (bundle.bundle_path !== join(directory, "AiralogyNativeReader.app") || bundle.bundle_id !== "org.airalogy.InstrumentInterfaceSimulator" || bundle.executable_sha256 !== manifest.simulator_sha256 || bundle.info_sha256 !== manifest.simulator_info_sha256)
    throw new Error("Native actions require this build's exact owned simulator")
  const survey = await previewNativeSurvey(definition.selection)
  const value = { schema: "airalogy.interface-preview.v1", engine: { ...survey.engine, name: "macos_accessibility_owned_simulation", version: 2 }, definition, plan }
  if (policy !== null) {
    if (plan.steps.length)
      throw new Error("Select a fixed plan or an exploration policy, not both")
    value.policy = validatePolicy(JSON.parse(canonical(policy)), definition)
  }
  return freeze({ ...value, sha256: digest(value) })
}

export class NativeInterfaceSession {
  static async open({ definition, plan, policy = null, confirmation, evidenceRoot }) {
    const preview = await previewNativeInterface(definition, plan, policy)
    if (confirmation !== preview.sha256)
      throw new Error("Confirm the exact native action preview")
    const evidence = await Evidence.create(evidenceRoot, preview)
    const session = new NativeInterfaceSession(preview, evidence)
    await evidence.append("native_session_intent", { actions_scope: "owned_simulation", hardware_qualified: false })
    await session.observe()
    return session
  }

  constructor(preview, evidence) {
    this.preview = preview
    this.definition = preview.definition
    this.plan = preview.plan
    this.policy = preview.policy ?? null
    this.evidence = evidence
    this.sessionId = randomUUID()
    this.deadline = performance.now() + this.definition.limits.duration_seconds * 1000
    this.cursor = 0
    this.observationCount = 0
    this.lastObservation = null
    this.busy = false
    this.closed = false
    this.fault = null
  }

  remaining() {
    const left = Math.floor(this.deadline - performance.now())
    if (this.closed || this.fault || left <= 0)
      throw new Error("Native session is closed, failed or expired")
    return Math.min(left, this.definition.limits.step_timeout_ms)
  }

  snapshotRequest() {
    const selection = this.definition.selection
    return { operation: "snapshot", pin: selection.target.source.pin, window_title: selection.target.title, capture_values: selection.capture_values, redact_identifiers: selection.redact_identifiers }
  }

  interpret(raw) {
    this.remaining()
    const found = locator => raw.controls.filter(item => item.locator && canonical(item.locator) === canonical(locator))
    const identity = found(this.definition.target.identity.locator)
    if (identity.length !== 1 || identity[0].read !== "text" || identity[0].value !== this.definition.target.identity.text)
      throw new Error("Native identity changed")
    const values = {}
    const enabled = {}
    for (const control of this.definition.controls) {
      const selected = found(control.locator)
      if (selected.length !== 1 || typeof selected[0].enabled !== "boolean")
        throw new Error("Native control is missing or ambiguous")
      const current = selected[0]
      const button = control.locator.role === "AXButton"
      if (!button && current.read !== control.read)
        throw new Error("Native readback type changed")
      const value = button ? current.label : current.value
      checkText(value, 4096, true)
      values[control.id] = value
      enabled[control.id] = current.enabled
    }
    const states = this.definition.states.filter(state => state.checks.every(check => values[check.control_id] === check.equals))
    if (states.length !== 1)
      throw new Error("Native state is unknown or ambiguous")
    const observation = { schema: "airalogy.interface-observation.v1", session_id: this.sessionId, preview: this.preview.sha256, target: { application: this.definition.target.application, version: this.definition.target.version }, state: states[0].id, values, enabled }
    return { raw, observation }
  }

  async snapshot() {
    const raw = await nativeCall(this.definition.selection.build_file, this.snapshotRequest(), { timeout: this.remaining() })
    return this.interpret(raw)
  }

  async saveObservation({ observation }) {
    this.remaining()
    if (this.observationCount >= this.definition.limits.max_steps * 2 + 1)
      throw new Error("Native observation budget exhausted")
    await this.evidence.append("observation", { ...observation, sha256: digest(observation), accessibility: null, screenshot: null })
    this.lastObservation = observation
    this.observationCount += 1
    return { ...observation, sha256: digest(observation) }
  }

  async fail(error, attempted = false) {
    this.fault = nativeFailureCode(error)
    await this.evidence.append("stopped", { reason: this.fault, operation_attempted: attempted, result_uncertain: attempted, retry_allowed: false, hardware_qualified: false })
  }

  async observe() {
    if (this.busy)
      throw new Error("Concurrent native operations are not allowed")
    this.busy = true
    try {
      return await this.saveObservation(await this.snapshot())
    }
    catch (error) {
      await this.fail(error)
      throw new Error(`Native observation stopped; inspect private evidence: ${this.evidence.directory}`)
    }
    finally { this.busy = false }
  }

  async step(expectedObservation, actionIndex) {
    if (this.busy)
      throw new Error("Concurrent native operations are not allowed")
    this.busy = true
    let attempted = false
    try {
      if (this.cursor >= this.definition.limits.max_steps || (this.policy ? !Number.isInteger(actionIndex) || actionIndex < 0 : actionIndex !== undefined))
        throw new Error("Native action exceeds the reviewed policy")
      const step = this.policy ? this.policy.actions[actionIndex] : this.plan.steps[this.cursor]
      if (!step)
        throw new Error("No further native action was confirmed")
      const before = await this.snapshot()
      if (expectedObservation !== digest(before.observation) || expectedObservation !== digest(this.lastObservation) || before.observation.state !== step.before || !before.observation.enabled[step.control_id])
        throw new Error("Native observation changed since approval")
      await this.evidence.append("step_intent", { index: this.cursor, step, before: expectedObservation })
      const control = this.definition.controls.find(item => item.id === step.control_id)
      const operation = { operation: step.operation, locator: control.locator, ...(step.operation === "fill" ? { value: step.value } : {}) }
      const timeout = this.remaining()
      // Once handed to the helper, a timeout is uncertain. Never retry a write.
      attempted = step.operation !== "read"
      const result = await nativeCall(this.definition.selection.build_file, { operation: "simulation_step", snapshot: this.snapshotRequest(), expected: before.raw, step: operation }, { timeout })
      checkObject(result, ["snapshot", "operation_attempted", "hardware_qualified"])
      if (result.operation_attempted !== attempted || result.hardware_qualified !== false)
        throw new Error("Native helper result is inconsistent")
      const after = this.interpret(result.snapshot)
      if (after.observation.state !== step.after || (step.operation === "fill" && after.observation.values[step.control_id] !== step.value))
        throw new Error("Native result or parameter readback failed")
      const saved = await this.saveObservation(after)
      await this.evidence.append("step_result", { index: this.cursor, after: saved.sha256, value: saved.values[step.control_id], hardware_qualified: false })
      this.cursor += 1
      return saved
    }
    catch (error) {
      await this.fail(error, attempted)
      throw new Error("Native step stopped; no automatic retry or physical safe-stop claim")
    }
    finally { this.busy = false }
  }

  async close() {
    if (this.busy)
      throw new Error("Wait for the in-flight native operation before closing")
    if (this.closed)
      return
    this.closed = true
    // The selected app belongs to the operator, not this session. Do not quit it.
    await this.evidence.append("closed", { completed_steps: this.cursor, planned_steps: this.policy ? null : this.plan.steps.length, application_closed: false, hardware_qualified: false })
  }
}
