/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { execFile, spawn } from "node:child_process"
import { once } from "node:events"
import { chmod, lstat, mkdtemp, readdir, readFile, symlink, writeFile } from "node:fs/promises"
import { join } from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"
import { promisify } from "node:util"
import { canonical, digest } from "../src/contract.mjs"
import { validateNativeDefinition, validateNativeSelection } from "../src/native-contract.mjs"
import { NativeInterfaceSession, previewNativeInterface, validateNativeInterface } from "../src/native-session.mjs"
import { previewNativeRead, runNativeRead, selectNative } from "../src/native-survey.mjs"
import { nativeSimulationTemplate } from "../src/native-template.mjs"
import { buildNative, nativeCall, validateNativeBuild } from "../src/native-transport.mjs"
import { assembleSurveyDefinition, validateSurveyAnalysis, validateSurveyReport } from "../src/survey-contract.mjs"
import { assemblePreparedSurvey, prepareSurvey, runPreparedSurvey } from "../src/survey-workspace.mjs"

function fixture() {
  const selection = {
    schema: "airalogy.native-survey-selection.v1",
    id: "native.fixture",
    build_file: "/private/build/native-build.json",
    target: { application: "org.airalogy.fixture", version: "1.0", title: "Synthetic fixture", locale: "en-US", source: { kind: "native_macos", pin: {
      bundle: { bundle_path: "/private/Fixture.app", executable_path: "/private/Fixture.app/Contents/MacOS/Fixture", bundle_id: "org.airalogy.fixture", version: "1.0", executable_sha256: "a".repeat(64), info_sha256: "b".repeat(64), code_directory_hash: "c".repeat(40) },
      process: { pid: 123, uid: 501, started_seconds: "123456", started_microseconds: "123" },
    } } },
    capture_values: false,
    redact_identifiers: [],
  }
  const report = {
    schema: "airalogy.interface-survey.v1",
    id: "12345678-1234-1234-1234-123456789012",
    preview_digest: "a".repeat(64),
    target: { application: selection.target.application, version: "1.0", title: "Synthetic fixture", locale: "en-US", kind: "native_macos" },
    capture_values: false,
    controls: [{ id: "control_1", label: "app.identity", role: "AXStaticText", locator: { kind: "ax_identifier", role: "AXStaticText", name: "app.identity" }, read: "text", value: "Synthetic fixture 1.0", enabled: false }],
    omitted_private: 1,
    limitations: ["Unqualified synthetic snapshot"],
  }
  const analysis = { summary: "Synthetic fixture", features: [], read_controls: ["control_1"], identity_control: "control_1", route: "native_accessibility", limitations: ["No actions tested"], missing_information: [] }
  return { selection, report, analysis }
}

test("native survey transport, roles, privacy and read-only assembly agree", () => {
  const { selection, report, analysis } = fixture()
  validateNativeSelection(selection)
  validateSurveyReport(report)
  validateSurveyAnalysis(analysis, report)
  const draft = assembleSurveyDefinition(selection, report, analysis, report.preview_digest)
  validateNativeDefinition(draft.definition)
  assert.equal(draft.definition.schema, "airalogy.native-read-definition.v1")
  assert.deepEqual(draft.plan.steps, [])
  assert.equal(draft.provenance.hardware_qualified, false)
  for (const mutate of [
    item => item.controls[0].locator.kind = "role",
    item => item.controls[0].role = "AXButton",
    item => item.target.kind = "file",
    item => item.controls[0].locator.name = " ",
    item => item.controls[0].read = "value",
  ]) {
    const invalid = structuredClone(report)
    mutate(invalid)
    assert.throws(() => validateSurveyReport(invalid))
  }
  draft.definition.controls[0].operations.push("click")
  assert.throws(() => validateNativeDefinition(draft.definition))
})

test("native selection cannot enable screenshots, actions, weak process pins or unbounded masks", () => {
  const { selection } = fixture()
  for (const mutate of [
    item => item.screenshot = true,
    item => item.actions = ["click"],
    item => item.target.source.pin.process.pid = 1.5,
    item => item.target.source.pin.process.started_seconds = 123,
    item => item.target.source.pin.bundle.code_directory_hash = "untrusted",
    item => item.target.version = "different",
    item => item.redact_identifiers = ["same", "same"],
    item => item.redact_identifiers = Array.from({ length: 33 }, (_, index) => `private.${index}`),
    item => item.capture_values = "true",
  ]) {
    const invalid = structuredClone(selection)
    mutate(invalid)
    assert.throws(() => validateNativeSelection(invalid))
  }
})

test("native write contracts cannot promote read-only surveys or arbitrary UI capabilities", () => {
  const { selection } = fixture()
  selection.capture_values = true
  const { definition } = nativeSimulationTemplate(selection)
  for (const mutate of [
    item => item.schema = "airalogy.native-read-definition.v1",
    item => item.target.source.kind = "native_macos",
    item => item.target.source.simulation = true,
    item => item.target.version = "changed",
    item => item.selection.capture_values = false,
    item => item.controls[0].operations.push("click"),
    item => item.controls[1].operations = ["fill"],
    item => item.controls[0].locator.kind = "coordinates",
    item => item.controls[0].locator.role = "AXComboBox",
    item => item.controls.push(item.controls[0]),
    item => item.limits.max_steps = 999,
    item => item.states[0].checks[0].equals = true,
    item => item.target.identity.locator.role = "AXTextField",
  ]) {
    const invalid = structuredClone(definition)
    mutate(invalid)
    assert.throws(() => validateNativeInterface(invalid))
  }
})

const real = process.env.RUN_INTERFACE_NATIVE_TESTS === "1"
const compile = real || process.env.RUN_INTERFACE_NATIVE_BUILD_TESTS === "1"
test("actual macOS build, integrity and permission diagnostic without app launch", { skip: !compile, timeout: 240000 }, async (t) => {
  assert.equal(process.platform, "darwin", "Native tests must run on macOS, not silently skip an unsupported host")
  const root = await mkdtemp("/private/tmp/platform-native-test-")
  const built = await buildNative(root)
  assert.equal(built.applications_opened, false)
  assert.equal((await lstat(built.build_file)).mode & 0o777, 0o600)
  const doctor = await nativeCall(built.build_file, { operation: "doctor" })
  assert.equal(typeof doctor.accessibility_trusted, "boolean")
  assert.equal(doctor.permissions_changed, false)
  assert.equal((await nativeCall(built.build_file, { operation: "inspect_bundle", bundle_path: built.simulator_app })).bundle_id, "org.airalogy.InstrumentInterfaceSimulator")
  await assert.rejects(nativeCall(built.build_file, { operation: "click", target: "arbitrary" }), /invalid_request/)
  await assert.rejects(nativeCall(built.build_file, { operation: "doctor", prompt: true }), /invalid_request/)

  await t.test("actual owned AppKit survey, private evidence, assembly and independent readback", { skip: !real, timeout: 120000 }, async () => {
    assert.equal(doctor.accessibility_trusted, true, "An operator must explicitly enable Accessibility for the test host; tests never change TCC")
    const child = spawn(join(built.simulator_app, "Contents/MacOS/Simulator"), [], { stdio: ["ignore", "pipe", "ignore"] })
    const exited = once(child, "exit")
    let closed = false
    try {
      await new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error("Owned simulator did not become ready")), 10000)
        child.stdout.once("data", () => {
          clearTimeout(timer)
          resolve()
        })
        child.once("error", reject)
      })
      const selection = await selectNative({ buildFile: built.build_file, bundlePath: built.simulator_app, pid: child.pid, title: "Airalogy Native Reader — Simulation", redactIdentifiers: ["private.note"] })
      const prepared = await prepareSurvey(selection, root)
      await assert.rejects(runPreparedSurvey(prepared.request_file, "0".repeat(64)), /Confirm/)
      const result = await runPreparedSurvey(prepared.request_file, prepared.local_preview_digest)
      const report = validateSurveyReport(JSON.parse(await readFile(result.report_file, "utf8")))
      const text = canonical(report)
      assert.ok(!text.includes("SYNTHETIC_PRIVATE") && !text.includes("SYNTHETIC_PASSWORD"))
      assert.ok(!text.includes(built.simulator_app) && !text.includes("started_seconds"))
      assert.ok(report.omitted_private >= 2)
      const identity = report.controls.find(item => item.locator?.name === "app.identity")
      const input = report.controls.find(item => item.locator?.name === "sample.count")
      assert.equal(identity?.value, "Airalogy Native Reader 1.0 — simulation only")
      assert.equal(input?.read, null)
      assert.equal(input?.value, null)
      const status = report.controls.find(item => item.locator?.name === "reader.status")
      assert.equal(status?.value, "Ready")
      await assert.rejects(runPreparedSurvey(prepared.request_file, prepared.local_preview_digest), /EEXIST/)
      const analysis = { capture_digest: result.report_digest, analysis: { summary: "Owned fixture", features: [], read_controls: [status.id], identity_control: identity.id, route: "native_accessibility", limitations: ["No hardware tested"], missing_information: [] } }
      const analysisFile = join(root, "reviewed-analysis.json")
      await writeFile(analysisFile, canonical(analysis), { mode: 0o600, flag: "wx" })
      const assembled = await assemblePreparedSurvey(prepared.request_file, analysisFile, root)
      const definition = JSON.parse(await readFile(assembled.definition_file, "utf8"))
      const preview = await previewNativeRead(definition)
      const read = await runNativeRead(definition, { confirmation: preview.sha256, evidenceRoot: root })
      assert.equal(JSON.parse(await readFile(read.readback_file, "utf8"))[status.id], "Ready")
      assert.equal(read.actions_executed, 0)
      const cli = fileURLToPath(new URL("../src/native-cli.mjs", import.meta.url))
      const cliPreview = JSON.parse((await promisify(execFile)(process.execPath, [cli, "preview", "--definition", assembled.definition_file], { timeout: 15000 })).stdout)
      assert.equal(cliPreview.sha256, preview.sha256)
      const cliRead = JSON.parse((await promisify(execFile)(process.execPath, [cli, "read", "--definition", assembled.definition_file, "--confirm", preview.sha256, "--evidence", root, "--ack-new-read"], { timeout: 45000 })).stdout)
      assert.equal(JSON.parse(await readFile(cliRead.readback_file, "utf8"))[status.id], "Ready")
      const valueSelection = { ...selection, capture_values: true }
      const capture = await prepareSurvey(valueSelection, root)
      const values = await runPreparedSurvey(capture.request_file, capture.local_preview_digest)
      const valued = JSON.parse(await readFile(values.report_file, "utf8"))
      assert.equal(valued.controls.find(item => item.locator?.name === "sample.count").value, "1")
      assert.ok(!canonical(valued).includes("SYNTHETIC_PASSWORD"))
      const invalid = structuredClone(selection.target.source.pin)
      invalid.process.started_microseconds = "0"
      const snapshot = { operation: "snapshot", pin: selection.target.source.pin, window_title: selection.target.title, capture_values: false, redact_identifiers: ["private.note"] }
      await assert.rejects(nativeCall(built.build_file, { ...snapshot, pin: invalid }), /target_changed/)
      await assert.rejects(nativeCall(built.build_file, { ...snapshot, window_title: "Wrong window" }), /window_title_changed/)
      await assert.rejects(nativeCall(built.build_file, { ...snapshot, redact_identifiers: ["missing"] }), /private_region_missing/)
      const changed = { ...definition, identity: { ...definition.identity, text: "Invented identity" } }
      await assert.rejects(runNativeRead(changed, { confirmation: (await previewNativeRead(changed)).sha256, evidenceRoot: root }), /refused/)
      assert.equal(result.report_digest, digest(report))

      // Real AXValue/AXPress operations on the owned fixture only. The hand-written
      // expected result is independent of the simulator's implementation/readback.
      const actionTemplate = nativeSimulationTemplate(valueSelection)
      const actionPreview = await previewNativeInterface(actionTemplate.definition, actionTemplate.plan)
      await assert.rejects(NativeInterfaceSession.open({ definition: actionTemplate.definition, plan: actionTemplate.plan, confirmation: "0".repeat(64), evidenceRoot: root }), /Confirm/)
      const actionSession = await NativeInterfaceSession.open({ definition: actionTemplate.definition, plan: actionTemplate.plan, confirmation: actionPreview.sha256, evidenceRoot: root })
      assert.equal(actionSession.lastObservation.values.sample_count, "1")
      await assert.rejects(actionSession.step("0".repeat(64)), /stopped/)
      await assert.rejects(actionSession.step(digest(actionSession.lastObservation)), /stopped/)
      assert.equal(actionSession.cursor, 0)
      await actionSession.close()
      const rawBefore = await nativeCall(built.build_file, { ...snapshot, capture_values: true })
      const wrongOwner = structuredClone(selection.target.source.pin)
      wrongOwner.bundle.bundle_id = "org.other.vendor"
      await assert.rejects(nativeCall(built.build_file, { operation: "simulation_step", snapshot: { ...snapshot, pin: wrongOwner }, expected: rawBefore, step: { operation: "click", locator: actionTemplate.definition.controls[1].locator } }), /owned_simulation_required/)
      const templateFiles = JSON.parse((await promisify(execFile)(process.execPath, [cli, "simulation-template", "--build", built.build_file, "--pid", String(child.pid), "--workspace", root], { timeout: 20000 })).stdout)
      assert.equal(templateFiles.actions_executed, 0)
      const runArgs = [cli, "run", "--definition", templateFiles.definition_file, "--plan", templateFiles.plan_file, "--confirm", templateFiles.preview_digest, "--evidence", root]
      await assert.rejects(promisify(execFile)(process.execPath, runArgs, { timeout: 20000 }))
      const cliRun = JSON.parse((await promisify(execFile)(process.execPath, [...runArgs, "--ack-new-run"], { timeout: 45000 })).stdout)
      assert.equal(cliRun.completed_steps, 2)
      assert.equal(cliRun.values.sample_count, "2")
      assert.equal(cliRun.values.result, "0.84")
      assert.equal(cliRun.values.status, "Complete")
      assert.equal(cliRun.hardware_qualified, false)
      const independentlyRead = await nativeCall(built.build_file, { ...snapshot, capture_values: true })
      assert.equal(independentlyRead.controls.find(item => item.locator?.name === "reader.result").value, "0.84")
      await assert.rejects(nativeCall(built.build_file, { operation: "simulation_step", snapshot: { ...snapshot, capture_values: true }, expected: rawBefore, step: { operation: "click", locator: actionTemplate.definition.controls[1].locator } }), /stale_observation/)
      // A fresh replay cannot silently ignore the changed Ready precondition.
      await assert.rejects(promisify(execFile)(process.execPath, [...runArgs, "--ack-new-run"], { timeout: 45000 }))
      const badPlan = { schema: "airalogy.interface-plan.v1", steps: [{ operation: "click", control_id: "run", before: "complete", after: "ready" }] }
      const badPreview = await previewNativeInterface(actionTemplate.definition, badPlan)
      const uncertain = await NativeInterfaceSession.open({ definition: actionTemplate.definition, plan: badPlan, confirmation: badPreview.sha256, evidenceRoot: root })
      await assert.rejects(uncertain.step(digest(uncertain.lastObservation)), /stopped/)
      assert.equal(uncertain.cursor, 0)
      await uncertain.close()
      const events = await Promise.all((await readdir(uncertain.evidence.directory)).filter(name => /^\d+\.json$/.test(name)).map(async name => JSON.parse(await readFile(join(uncertain.evidence.directory, name), "utf8"))))
      const stopped = events.find(event => event.kind === "stopped")
      assert.equal(stopped.data.operation_attempted, true)
      assert.equal(stopped.data.result_uncertain, true)
      assert.equal(stopped.data.retry_allowed, false)
      assert.ok(events.some(event => event.kind === "step_intent"))
      assert.ok(!events.some(event => event.kind === "step_result"))
      assert.ok(!canonical(events).includes("SYNTHETIC_PRIVATE") && !canonical(events).includes("SYNTHETIC_PASSWORD"))
      assert.equal((await nativeCall(built.build_file, { operation: "pin_process", bundle_path: built.simulator_app, pid: child.pid })).process.pid, child.pid)
      child.kill("SIGTERM")
      await exited
      closed = true
      await assert.rejects(previewNativeRead(definition), /target_changed/)
      const offline = await assemblePreparedSurvey(prepared.request_file, analysisFile, root)
      assert.equal(JSON.parse(await readFile(offline.definition_file, "utf8")).schema, "airalogy.native-read-definition.v1")
      await assert.rejects(runPreparedSurvey(prepared.request_file, prepared.local_preview_digest), /target_changed/)
      t.diagnostic(`Private native evidence: ${root}`)
    }
    finally {
      if (!closed) {
        child.kill("SIGTERM")
        await exited
      }
    }
  })
  // These are owned synthetic build files only; retain every artifact for inspection.
  await chmod(built.helper, 0o744)
  await assert.rejects(validateNativeBuild(built.build_file), /private/)
  await chmod(built.helper, 0o700)
  const link = join(root, "build-link")
  await symlink(built.build_file, link)
  await assert.rejects(validateNativeBuild(link))
  const infoFile = join(built.simulator_app, "Contents/Info.plist")
  await writeFile(infoFile, (await readFile(infoFile, "utf8")).replace("<string>1.0</string>", "<string>2.0</string>"))
  await assert.rejects(nativeCall(built.build_file, { operation: "inspect_bundle", bundle_path: built.simulator_app }), /unsupported_target/)
  await writeFile(built.helper, Buffer.concat([await readFile(built.helper), Buffer.from([0])]))
  await assert.rejects(nativeCall(built.build_file, { operation: "doctor" }), /binary changed/)
})
