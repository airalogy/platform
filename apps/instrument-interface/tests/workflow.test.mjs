/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { chmod, readdir, readFile, rename, symlink, writeFile } from "node:fs/promises"
import { join } from "node:path"
import test from "node:test"
import { previewInterface } from "../src/browser-session.mjs"
import { canonical, digest } from "../src/contract.mjs"
import { Evidence } from "../src/evidence.mjs"
import { exportWorkflow, previewWorkflow, previewWorkflowExport, runWorkflow, validateWorkflow, workflowFromEvidence } from "../src/workflow.mjs"
import { emptyPlan, fixture, plan } from "./fixture.mjs"

const policy = { goal: "Read two synthetic samples", actions: plan.steps, success: [{ control_id: "result", equals: "0.84" }] }
const sessionId = "11111111-1111-1111-1111-111111111111"
const seal = ({ sha256: _, ...value }) => ({ ...value, sha256: digest(value) })

// Deliberately independent saved-evidence fixture. Semantic mutations are
// rehashed to test validation beyond mere file/hash consistency.
async function trace({ change = () => {}, native = false } = {}) {
  const selected = await fixture()
  let definition = selected.definition
  if (native) {
    const target = { application: "Synthetic reader", version: "1.0", title: "Synthetic interface", locale: "en-US" }
    definition = {
      schema: "airalogy.native-interface.v1",
      id: "native.fixture",
      selection: {
        schema: "airalogy.native-survey-selection.v1",
        id: "native.fixture",
        build_file: "/private/not-a-real-build.json",
        capture_values: true,
        redact_identifiers: [],
        target: { ...target, source: { kind: "native_macos", pin: {
          bundle: { bundle_path: "/private/Fixture.app", executable_path: "/private/Fixture.app/Contents/MacOS/Fixture", bundle_id: "org.airalogy.fixture", version: "1.0", executable_sha256: "a".repeat(64), info_sha256: "b".repeat(64), code_directory_hash: "c".repeat(40) },
          process: { pid: 123, uid: 501, started_seconds: "123456", started_microseconds: "123" },
        } } },
      },
      target: { ...target, source: { kind: "native_macos_simulation" }, identity: { locator: { kind: "ax_identifier", role: "AXStaticText", name: "identity" }, text: "Synthetic identity" } },
      controls: definition.controls.map(control => ({ ...control, locator: { kind: "ax_identifier", role: control.id === "count" ? "AXTextField" : control.id === "run" ? "AXButton" : "AXStaticText", name: control.id } })),
      states: definition.states,
      limits: { duration_seconds: 30, max_steps: 5, step_timeout_ms: 5000 },
    }
  }
  const preview = native
    ? seal({ schema: "airalogy.interface-preview.v1", engine: { name: "synthetic-native-evidence-only" }, definition, plan: emptyPlan, policy })
    : await previewInterface(definition, emptyPlan, policy)
  const observations = [
    { count: "1", run: "Run simulation", result: "0", status: "Ready" },
    { count: "2", run: "Run simulation", result: "0", status: "Ready" },
    { count: "2", run: "Run simulation", result: "0.84", status: "Complete" },
  ].map((values, index) => {
    const value = { schema: "airalogy.interface-observation.v1", session_id: sessionId, preview: preview.sha256, target: { application: definition.target.application, version: "1.0" }, state: index === 2 ? "complete" : "ready", values, enabled: { count: true, run: true, result: true, status: true } }
    return { ...value, sha256: digest(value), accessibility: "PRIVATE TREE NOT EXPORTED", screenshot: "private.png" }
  })
  const events = [
    native ? ["native_session_intent", { actions_scope: "owned_simulation", hardware_qualified: false }] : ["opening", { session_id: sessionId, confirmation: preview.sha256 }],
    ["observation", observations[0]],
    ["step_intent", { index: 0, step: plan.steps[0], before: observations[0].sha256 }],
    ["observation", observations[1]],
    ["step_result", { index: 0, after: observations[1].sha256, value: "2" }],
    ["observation", observations[1]],
    ["step_intent", { index: 1, step: plan.steps[1], before: observations[1].sha256 }],
    ["observation", observations[2]],
    ["step_result", { index: 1, after: observations[2].sha256, value: "Run simulation" }],
    ["exploration_result", { result: "client_reported_success", proposal: { kind: "finish", action_index: null, summary: "Synthetic complete", missing_information: [] }, hardware_qualified: false }],
    ["closed", { completed_steps: 2, planned_steps: null, hardware_qualified: false }],
  ]
  change(events)
  const evidence = await Evidence.create(selected.root, preview)
  for (const [kind, data] of events)
    await evidence.append(kind, data)
  await evidence.write("request.json", Buffer.from("PRIVATE CREDENTIAL NEVER READ"))
  return { ...selected, directory: evidence.directory }
}

test("completed exploration exports only observed literal steps, fixed success and local lineage", async () => {
  const selected = await trace()
  // Export is historical/offline; it must not inspect or open source software.
  await rename(selected.definition.target.source.path, join(selected.root, "moved.html"))
  const preview = await previewWorkflowExport(selected.directory)
  assert.deepEqual(preview.workflow.plan.steps, plan.steps.slice(0, 2))
  assert.deepEqual(preview.workflow.success, policy.success)
  assert.equal(preview.workflow.initial.values.count, "1")
  assert.equal(preview.workflow.source.event_count, 11)
  assert.equal(preview.workflow.source.session_id, sessionId)
  assert.equal(preview.workflow.hardware_qualified, false)
  assert.ok(!canonical(preview).includes("PRIVATE"))
  const saved = await exportWorkflow(selected.directory, { confirmation: preview.sha256, workspace: selected.root })
  assert.equal(saved.application_opened, false)
  assert.deepEqual(JSON.parse(await readFile(saved.workflow_file)), preview.workflow)
  await assert.rejects(previewWorkflow(preview.workflow)) // Current target is still required to run.
  const before = await readdir(selected.root)
  await assert.rejects(exportWorkflow(selected.directory, { confirmation: "a".repeat(64), workspace: selected.root }))
  assert.deepEqual(await readdir(selected.root), before)
  const closedPath = join(selected.directory, "0010.json")
  const closed = JSON.parse(await readFile(closedPath))
  await writeFile(closedPath, canonical(seal({ ...closed, time: "2020-01-01T00:00:00.000Z" })))
  await assert.rejects(exportWorkflow(selected.directory, { confirmation: preview.sha256, workspace: selected.root }), /current workflow export/)
  assert.deepEqual(await readdir(selected.root), before)
})

test("offline native export retains process/code pins and cannot grant vendor actions", async () => {
  const selected = await trace({ native: true })
  const value = await workflowFromEvidence(selected.directory)
  assert.equal(value.definition.selection.target.source.pin.process.pid, 123)
  assert.equal(value.definition.target.source.kind, "native_macos_simulation")
  await assert.rejects(previewWorkflow(value)) // No helper/build exists; cannot run.
  value.definition.target.source.kind = "native_macos"
  assert.throws(() => validateWorkflow(seal(value)))
})

test("partial, failed, discontinuous, out-of-policy and falsely successful traces are refused even when rehashed", async () => {
  const mutations = [
    events => events.pop(),
    events => events.splice(8, 1),
    events => events.splice(5, 0, ["stopped", { reason: "uncertain" }]),
    (events) => { events[6][1].before = "0".repeat(64) },
    (events) => { events[2][1].step = { ...plan.steps[0], value: "99" } },
    (events) => { events[8][1].value = "wrong" },
    (events) => { events[10][1].completed_steps = 3 },
    (events) => { events[9][1].result = "needs_information" },
    events => events.splice(2, 0, ["observation", events[3][1]]), // Unrecorded fill.
    events => events.splice(6, 3), // Final success claimed with result still zero.
    events => events.splice(10, 0, ["observation", events[7][1]]),
    (events) => { events[7][1].session_id = "22222222-2222-2222-2222-222222222222" },
  ]
  for (const change of mutations) {
    const selected = await trace({ change })
    await assert.rejects(workflowFromEvidence(selected.directory))
  }
})

test("digest drift, missing sequences, symlinks, permissive files and oversize files are rejected", async () => {
  for (const change of [
    async directory => writeFile(join(directory, "0001.json"), "{}"),
    async directory => rename(join(directory, "0001.json"), join(directory, "missing.json")),
    async (directory) => {
      await rename(join(directory, "0001.json"), join(directory, "target.json"))
      await symlink(join(directory, "target.json"), join(directory, "0001.json"))
    },
    async directory => chmod(join(directory, "0001.json"), 0o644),
    async directory => writeFile(join(directory, "0001.json"), " ".repeat(524289)),
  ]) {
    const selected = await trace()
    await change(selected.directory)
    await assert.rejects(workflowFromEvidence(selected.directory))
  }
})

test("workflow digest and contract reject edited authority, checks, URL actions and unknown fields", async () => {
  const selected = await trace()
  const original = await workflowFromEvidence(selected.directory)
  for (const mutate of [
    (value) => { value.hardware_qualified = true },
    (value) => { value.shell = "unapproved" },
    (value) => { value.success = [{ control_id: "unknown", equals: "done" }] },
    (value) => { value.plan.steps[0].value = "3" },
    (value) => { value.initial.enabled.count = "true" },
  ]) {
    const value = structuredClone(original)
    mutate(value)
    assert.throws(() => validateWorkflow(value))
  }
  const invalid = structuredClone(original)
  invalid.definition.target.source = { kind: "url", url: "https://example.invalid/" }
  invalid.definition.network = [{ url: "https://example.invalid/", method: "GET", max_requests: 1 }]
  assert.throws(() => validateWorkflow(seal(invalid)), /observation-only/)
  const preview = await previewWorkflow(original)
  const before = await readdir(selected.root)
  await assert.rejects(runWorkflow(original, { confirmation: preview.sha256, evidenceRoot: selected.root }))
  await assert.rejects(runWorkflow(original, { confirmation: "a".repeat(64), acknowledgeNewRun: true, evidenceRoot: selected.root }))
  assert.deepEqual(await readdir(selected.root), before) // No launch/receipt before consent.
})

const browserTest = (name, fn) => test(name, { skip: process.env.RUN_INTERFACE_BROWSER_TESTS !== "1" }, fn)
browserTest("fixed workflow uses actual browser readback; changed initial values stop before any step", async () => {
  const selected = await trace()
  const workflow = await workflowFromEvidence(selected.directory)
  const preview = await previewWorkflow(workflow)
  const result = await runWorkflow(workflow, { confirmation: preview.sha256, evidenceRoot: selected.root, acknowledgeNewRun: true })
  assert.deepEqual(result.values, { result: "0.84" })
  assert.equal(result.state, "workflow_completed")
  assert.notEqual(result.session_id, sessionId)
  const changed = seal({ ...workflow, initial: { ...workflow.initial, values: { ...workflow.initial.values, count: "7" } } })
  const changedPreview = await previewWorkflow(changed)
  await assert.rejects(runWorkflow(changed, { confirmation: changedPreview.sha256, evidenceRoot: selected.root, acknowledgeNewRun: true }), /stopped/)
  const runs = (await readdir(selected.root)).filter(name => name.startsWith("interface-"))
  let found = false
  for (const name of runs) {
    const directory = join(selected.root, name)
    const events = await Promise.all((await readdir(directory)).filter(file => /^\d{4}\.json$/.test(file)).sort().map(async file => JSON.parse(await readFile(join(directory, file)))))
    if (events.some(event => event.kind === "workflow_stopped")) {
      found = true
      assert.ok(!events.some(event => event.kind === "step_intent"))
    }
  }
  assert.ok(found)
})

browserTest("fixed workflow must satisfy saved success checks, not only the final state label", async () => {
  const selected = await trace()
  const workflow = seal({ ...await workflowFromEvidence(selected.directory), success: [{ control_id: "result", equals: "99" }] })
  const preview = await previewWorkflow(workflow)
  await assert.rejects(runWorkflow(workflow, { confirmation: preview.sha256, evidenceRoot: selected.root, acknowledgeNewRun: true }), /stopped/)
})
