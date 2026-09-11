import { Buffer } from "node:buffer"
import { lstat, opendir, realpath } from "node:fs/promises"
import { isAbsolute, join } from "node:path"
import { canonical, checkObject, digest, validateDefinition, validatePlan } from "./contract.mjs"
import { Evidence, readPrivateSelection } from "./evidence.mjs"
import { matches, validatePolicy } from "./exploration-contract.mjs"
import { openSelectedInterface, previewSelectedInterface } from "./interface-backend.mjs"
import { validateNativeInterface } from "./native-session.mjs"

const MAX_FILE = 524288
const withoutHash = ({ sha256: _, ...value }) => value
const stateOf = ({ state, values, enabled }) => ({ state, values, enabled })
const same = (left, right) => canonical(left) === canonical(right)

function verifyDigest(value) {
  if (value.sha256 !== digest(withoutHash(value)))
    throw new Error("Saved digest changed")
}

function definitionOf(value) {
  return value.schema === "airalogy.browser-interface.v1" ? validateDefinition(value) : validateNativeInterface(value)
}

export function validateState(value, definition) {
  checkObject(value, ["state", "values", "enabled"])
  const ids = definition.controls.map(control => control.id)
  checkObject(value.values, ids)
  checkObject(value.enabled, ids)
  for (const control of definition.controls) {
    const current = value.values[control.id]
    if ((control.read === "checked" ? typeof current !== "boolean" : typeof current !== "string") || Buffer.byteLength(canonical(current)) > 4096 || typeof value.enabled[control.id] !== "boolean")
      throw new Error("Unexpected workflow control readback")
  }
  const states = definition.states.filter(state => matches(state.checks, value))
  if (states.length !== 1 || states[0].id !== value.state)
    throw new Error("Workflow state is unknown or ambiguous")
  return value
}

export function validateWorkflow(input) {
  // Detach caller-owned data before asynchronous approval/execution checks.
  if (Buffer.byteLength(canonical(input)) > MAX_FILE)
    throw new Error("Workflow exceeds its bound")
  const value = JSON.parse(canonical(input))
  checkObject(value, ["schema", "definition", "plan", "initial", "success", "source", "hardware_qualified", "sha256"])
  if (value.schema !== "airalogy.interface-workflow.v1" || value.hardware_qualified !== false)
    throw new Error("Select a development workflow, not hardware authority")
  verifyDigest(value)
  definitionOf(value.definition)
  validatePlan(value.plan, value.definition)
  if (!value.plan.steps.length)
    throw new Error("A reusable workflow requires completed steps")
  // Reuse policy validation for bounded, declared success checks. Repeated
  // executed actions remain literal plan steps, not duplicated policy entries.
  const actions = [...new Map(value.plan.steps.map(step => [canonical(step), step])).values()]
  validatePolicy({ goal: "Reviewed fixed workflow", actions, success: value.success }, value.definition)
  validateState(value.initial, value.definition)
  if (value.plan.steps[0].before !== value.initial.state)
    throw new Error("Workflow initial state differs from its first step")
  checkObject(value.source, ["preview_digest", "last_event_digest", "event_count", "session_id"], ["kind"])
  if ("kind" in value.source && (value.source.kind !== "human_browser_events" || value.definition.schema !== "airalogy.browser-interface.v1" || value.definition.target.source.kind !== "file" || value.definition.network.length))
    throw new Error("Unknown workflow evidence origin")
  if (![value.source.preview_digest, value.source.last_event_digest].every(hash => typeof hash === "string" && /^[a-f0-9]{64}$/.test(hash)) || !Number.isInteger(value.source.event_count) || value.source.event_count < 1 || value.source.event_count > 256 || typeof value.source.session_id !== "string" || !/^[a-f0-9-]{36}$/.test(value.source.session_id))
    throw new Error("Invalid workflow lineage")
  return value
}

async function privateDirectory(path) {
  if (process.platform === "win32" || !isAbsolute(path))
    throw new Error("Select a private absolute POSIX directory")
  const info = await lstat(path)
  if (!info.isDirectory() || info.isSymbolicLink() || info.uid !== process.getuid() || (info.mode & 0o077))
    throw new Error("Workflow evidence must be owner-only")
  return realpath(path)
}

async function readSaved(path) {
  const info = await lstat(path)
  if (!info.isFile() || info.isSymbolicLink() || info.nlink !== 1 || info.uid !== process.getuid() || (info.mode & 0o077))
    throw new Error("Select an owner-only regular evidence file")
  return readPrivateSelection(path, MAX_FILE)
}

export async function workflowFromEvidence(directory) {
  directory = await privateDirectory(directory)
  const previewBytes = await readSaved(join(directory, "preview.json"))
  const preview = JSON.parse(previewBytes)
  checkObject(preview, ["schema", "engine", "definition", "plan", "policy", "sha256"], ["capture"])
  verifyDigest(preview)
  if (preview.schema !== "airalogy.interface-preview.v1" || preview.plan.steps?.length !== 0)
    throw new Error("Select a completed exploration evidence directory")
  const definition = definitionOf(preview.definition)
  const demonstration = "capture" in preview
  if (demonstration) {
    checkObject(preview.capture, ["kind", "visible"])
    if (preview.capture.kind !== "human_browser_events" || typeof preview.capture.visible !== "boolean" || definition.schema !== "airalogy.browser-interface.v1" || definition.target.source.kind !== "file" || definition.network.length)
      throw new Error("Demonstration evidence requires the explicitly selected owned browser capture")
  }
  validatePlan(preview.plan, definition)
  validatePolicy(preview.policy, definition)
  // Enumerate bounded names only; never read credentials, model turns, trees or
  // screenshots from neighboring files. A truncated/uncertain trace is refused.
  const names = []
  let entries = 0
  for await (const entry of await opendir(directory)) {
    if (++entries > 1024)
      throw new Error("Evidence directory exceeds its entry bound")
    if (/^\d+\.json$/.test(entry.name)) {
      if (!/^\d{4}\.json$/.test(entry.name))
        throw new Error("Unexpected evidence sequence name")
      names.push(entry.name)
    }
  }
  names.sort()
  if (!names.length || names.length > 256)
    throw new Error("Evidence event count is outside its bound")
  let totalBytes = previewBytes.length
  let previous = null
  let observation = null
  let initial = null
  let pending = null
  let afterSeen = false
  let finished = false
  let sessionId = null
  const steps = []
  for (const [index, name] of names.entries()) {
    if (name !== `${String(index).padStart(4, "0")}.json`)
      throw new Error("Evidence chain has a missing event")
    const raw = await readSaved(join(directory, name))
    totalBytes += raw.length
    if (totalBytes > 16777216)
      throw new Error("Evidence exceeds its byte bound")
    const event = JSON.parse(raw)
    checkObject(event, ["sequence", "previous", "time", "kind", "data", "sha256"])
    verifyDigest(event)
    if (event.sequence !== index || event.previous !== previous || !Number.isFinite(Date.parse(event.time)))
      throw new Error("Evidence chain is inconsistent")
    previous = event.sha256
    const data = event.data
    if (index === 0) {
      if (definition.schema === "airalogy.browser-interface.v1" ? event.kind !== "opening" || data.confirmation !== preview.sha256 : event.kind !== "native_session_intent" || data.actions_scope !== "owned_simulation" || data.hardware_qualified !== false)
        throw new Error("Missing selected interface opening intent")
      sessionId = data.session_id ?? null
      continue
    }
    if (finished && event.kind !== "closed")
      throw new Error("Evidence continues after declared completion")
    if (event.kind === "observation") {
      checkObject(data, ["schema", "session_id", "preview", "target", "state", "values", "enabled", "sha256", "accessibility", "screenshot"])
      const { accessibility: _, screenshot: __, sha256: hash, ...observed } = data
      if (hash !== digest(observed) || observed.schema !== "airalogy.interface-observation.v1" || observed.preview !== preview.sha256 || !same(observed.target, { application: definition.target.application, version: definition.target.version }) || (sessionId !== null && sessionId !== observed.session_id))
        throw new Error("Observation identity or digest changed")
      sessionId = observed.session_id
      const state = validateState(stateOf(observed), definition)
      if (pending ? afterSeen : observation !== null && !same(state, stateOf(observation)))
        throw new Error("Unrecorded interface changes cannot become workflow steps")
      initial ??= state
      afterSeen = pending !== null
      observation = { ...observed, sha256: hash }
    }
    else if (event.kind === "step_intent" || event.kind === "demonstration_action") {
      checkObject(data, ["index", "step", "before"])
      if ((event.kind === "demonstration_action") !== demonstration || pending || !observation || data.index !== steps.length || data.before !== observation.sha256 || data.step.before !== observation.state || !observation.enabled[data.step.control_id] || !preview.policy.actions.some(step => same(step, data.step)))
        throw new Error("Step was not approved against its recorded observation")
      pending = data.step
      afterSeen = false
    }
    else if (event.kind === "step_result" || event.kind === "demonstration_readback") {
      checkObject(data, ["index", "after", "value"], ["hardware_qualified"])
      if ((event.kind === "demonstration_readback") !== demonstration || !pending || !afterSeen || data.index !== steps.length || data.after !== observation.sha256 || observation.state !== pending.after || !same(data.value, observation.values[pending.control_id]) || (pending.operation === "fill" && observation.values[pending.control_id] !== pending.value))
        throw new Error("Step result or parameter readback is incomplete")
      steps.push(pending)
      pending = null
      afterSeen = false
    }
    else if (event.kind === "exploration_result") {
      checkObject(data, ["result", "proposal", "hardware_qualified"])
      if (demonstration || pending || !observation || data.result !== "client_reported_success" || data.proposal?.kind !== "finish" || data.hardware_qualified !== false || !matches(preview.policy.success, observation))
        throw new Error("Exploration did not meet the predeclared success checks")
      finished = true
    }
    else if (event.kind === "demonstration_result") {
      checkObject(data, ["result", "completed_steps", "hardware_qualified"])
      if (!demonstration || pending || !observation || data.result !== "observed_success" || data.completed_steps !== steps.length || data.hardware_qualified !== false || !matches(preview.policy.success, observation))
        throw new Error("Demonstration did not satisfy its recorded steps and original success checks")
      finished = true
    }
    else if (event.kind === "closed") {
      if (!finished || pending || index !== names.length - 1 || data.completed_steps !== steps.length || data.planned_steps !== null)
        throw new Error("Only a fully completed and closed exploration can be saved")
    }
    else {
      throw new Error("Stopped or unsupported evidence cannot become a workflow")
    }
    if (index === names.length - 1 && event.kind !== "closed")
      throw new Error("Exploration is not closed")
  }
  const workflow = { schema: "airalogy.interface-workflow.v1", definition, plan: { schema: "airalogy.interface-plan.v1", steps }, initial, success: preview.policy.success, source: { preview_digest: preview.sha256, last_event_digest: previous, event_count: names.length, session_id: sessionId }, hardware_qualified: false }
  if (demonstration)
    workflow.source.kind = "human_browser_events"
  return validateWorkflow({ ...workflow, sha256: digest(workflow) })
}

export async function previewWorkflowExport(directory) {
  const workflow = await workflowFromEvidence(directory)
  const value = { schema: "airalogy.workflow-export-preview.v1", evidence_directory: await realpath(directory), workflow, application_opened: false }
  return { ...value, sha256: digest(value) }
}

export async function exportWorkflow(directory, { confirmation, workspace }) {
  const preview = await previewWorkflowExport(directory)
  if (confirmation !== preview.sha256)
    throw new Error("Confirm the exact current workflow export preview")
  const evidence = await Evidence.create(workspace, preview)
  await evidence.write("workflow.json", Buffer.from(canonical(preview.workflow)))
  return { workflow_file: join(evidence.directory, "workflow.json"), workflow_digest: preview.workflow.sha256, application_opened: false, hardware_qualified: false }
}

export async function previewWorkflow(input) {
  const workflow = validateWorkflow(input)
  const selected = await previewSelectedInterface(workflow.definition, workflow.plan)
  const value = { schema: "airalogy.workflow-run-preview.v1", workflow, interface_preview_digest: selected.sha256, engine: selected.engine, new_operation: true, hardware_qualified: false }
  return { ...value, sha256: digest(value) }
}

export async function runWorkflow(input, { confirmation, evidenceRoot, acknowledgeNewRun = false, browserExecutable = null }) {
  const preview = await previewWorkflow(input)
  if (!acknowledgeNewRun || confirmation !== preview.sha256)
    throw new Error("A new workflow run requires exact preview confirmation and acknowledgement")
  const { workflow } = preview
  // Reuse the existing fixed backend and its safety gates. No model, remote
  // grant, dynamic code, new transport or authority is introduced here.
  const session = await openSelectedInterface({ definition: workflow.definition, plan: workflow.plan, confirmation: preview.interface_preview_digest, evidenceRoot, browserExecutable })
  try {
    await session.evidence.append("workflow_intent", { workflow_digest: workflow.sha256, source: workflow.source, run_preview_digest: preview.sha256 })
    if (!same(stateOf(session.lastObservation), workflow.initial))
      throw new Error("Initial interface values or state differ from the reviewed workflow")
    for (let index = 0; index < workflow.plan.steps.length; index++)
      await session.step(digest(session.lastObservation))
    await session.observe()
    if (!matches(workflow.success, session.lastObservation))
      throw new Error("Workflow did not meet its independently selected success checks")
    const result = { state: "workflow_completed", workflow_digest: workflow.sha256, evidence: session.evidence.directory, session_id: session.sessionId, values: Object.fromEntries(workflow.success.map(check => [check.control_id, session.lastObservation.values[check.control_id]])), hardware_qualified: false }
    await session.evidence.append("workflow_result", result)
    return result
  }
  catch {
    await session.evidence.append("workflow_stopped", { retry_allowed: false, physical_stop_confirmed: false })
    throw new Error(`Workflow stopped; retain private evidence and reconcile before another run: ${session.evidence.directory}`)
  }
  finally {
    await session.close()
  }
}
