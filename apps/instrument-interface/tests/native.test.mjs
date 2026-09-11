/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { execFile, spawn } from "node:child_process"
import { once } from "node:events"
import { chmod, lstat, mkdtemp, readdir, readFile, symlink, writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"
import { promisify } from "node:util"
import { canonical, digest } from "../src/contract.mjs"
import { Evidence } from "../src/evidence.mjs"
import { prepareExploration, runExploration, syncExploration } from "../src/exploration.mjs"
import { validateNativeDefinition, validateNativeSelection } from "../src/native-contract.mjs"
import { nativeDiscoveryResult, prepareNativeDiscovery, runNativeDiscovery } from "../src/native-discovery.mjs"
import { guideNative } from "../src/native-guide.mjs"
import { nativeLaunchStatus, prepareNativeLaunch, runNativeLaunch, validateLaunchPreview } from "../src/native-launch.mjs"
import { prepareNativeReadRuntime, previewNativeReadRuntime } from "../src/native-read-worker-runtime.mjs"
import { NativeInterfaceSession, previewNativeInterface, validateNativeInterface } from "../src/native-session.mjs"
import { previewNativeRead, runNativeRead, selectNative } from "../src/native-survey.mjs"
import { nativeSimulationTemplate } from "../src/native-template.mjs"
import { buildNative, nativeCall, validateNativeBuild } from "../src/native-transport.mjs"
import { assembleSurveyDefinition, validateSurveyAnalysis, validateSurveyReport } from "../src/survey-contract.mjs"
import { assemblePreparedSurvey, prepareSurvey, runPreparedSurvey } from "../src/survey-workspace.mjs"
import { focusOwnedFixture } from "./native-fixture.mjs"
import { ownedReadDefinition, prepareOwnedReadRuntime, verifyIndependentNativeInstalls } from "./native-worker-fixture.mjs"

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

async function closeOwnedLaunch(built) {
  const inspection = await nativeCall(built.build_file, { operation: "inspect_application", bundle_path: built.simulator_app })
  for (const pin of inspection.running) {
    assert.equal(pin.bundle.bundle_path, built.simulator_app)
    assert.equal(pin.bundle.bundle_id, "org.airalogy.InstrumentInterfaceSimulator")
    process.kill(pin.process.pid, "SIGTERM")
  }
  for (let index = 0; index < 50; index++) {
    try {
      await nativeCall(built.build_file, { operation: "launch_probe", bundle_path: built.simulator_app })
      return
    }
    catch (error) {
      if (error.message !== "application_already_running")
        throw error
      await new Promise(resolve => setTimeout(resolve, 100))
    }
  }
  throw new Error("Owned simulator did not exit; retain its selected identity for cleanup")
}

async function waitForOwnedWindow(built, pin) {
  let observed
  // Fixture setup waits for actual OS-reported UI metadata before preparing a
  // new capture. It never retries a survey request, action or launch.
  for (let index = 0; index < 30; index++) {
    observed = await nativeCall(built.build_file, { operation: "inspect_windows", pin })
    if (observed.windows.length === 1 && observed.windows[0].role === "AXWindow" && observed.windows[0].title === "Airalogy Native Reader — Simulation" && observed.windows[0].has_geometry && observed.windows[0].minimized === false)
      return observed
    await new Promise(resolve => setTimeout(resolve, 100))
  }
  // All output is from the owned synthetic fixture only, never vendor metadata.
  assert.fail(`Owned fixture UI did not become ready: ${canonical(observed)}`)
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
  assert.equal(typeof doctor.interactive_session.ready, "boolean")
  assert.equal(doctor.permissions_changed, false)
  await assert.rejects(focusOwnedFixture(built.build_file, process.pid), /target_changed/)
  assert.equal((await nativeCall(built.build_file, { operation: "inspect_bundle", bundle_path: built.simulator_app })).bundle_id, "org.airalogy.InstrumentInterfaceSimulator")
  // Connect private discovery to the existing full identity check, without
  // launching the signed owned fixture or observing its windows.
  const discovery = await prepareNativeDiscovery({ directory: dirname(built.simulator_app), workspace: root })
  await runNativeDiscovery(discovery.request_file, discovery.preview_digest)
  const inventory = (await nativeDiscoveryResult(discovery.request_file)).report
  assert.equal(inventory.applications.length, 1)
  assert.equal(inventory.applications[0].bundle_path, built.simulator_app)
  const inspected = await nativeCall(built.build_file, { operation: "inspect_application", bundle_path: inventory.applications[0].bundle_path })
  assert.equal(inspected.bundle.info_sha256, inventory.applications[0].declared.info_sha256)
  assert.equal(inspected.bundle.bundle_id, inventory.applications[0].declared.bundle_id)
  assert.deepEqual(inspected.running, [])
  assert.equal(inventory.signature_verified, false)
  await t.test("guided native selection uses actual saved discovery/identity and stops before unauthorized startup", async () => {
    let output = ""
    const guided = await guideNative({ requestFile: discovery.request_file, buildFile: built.build_file, workspace: root, locale: "en-US", redactIdentifiers: ["private.note"] }, {
      write: value => output = value,
      question: async (prompt) => {
        if (prompt.startsWith("Choose"))
          return "1"
        if (prompt.startsWith("Software"))
          return ""
        return output.trim().split("\n").at(-1)
      },
    })
    assert.equal(guided.state, "needs_attention")
    assert.equal(guided.stage, "prepare_launch")
    assert.equal(guided.reason, "operator_cancelled")
    assert.ok(guided.selection_file)
    assert.ok(!guided.launch_request && !guided.survey_request)
    assert.deepEqual((await nativeCall(built.build_file, { operation: "inspect_application", bundle_path: built.simulator_app })).running, [])
  })
  // Runtime preparation checks real compiled bytes without starting an app or
  // touching AX. A fabricated process selection must fail when probed.
  const fakeSelection = fixture().selection
  fakeSelection.build_file = built.build_file
  fakeSelection.target.source.pin.bundle = inspected.bundle
  fakeSelection.target.version = inspected.bundle.version
  fakeSelection.target.application = inspected.bundle.bundle_id
  const readInput = await Evidence.create(root, { owned_metadata_only: true })
  const readFilePath = join(readInput.directory, "definition.json")
  await readInput.write("definition.json", Buffer.from(canonical(ownedReadDefinition(fakeSelection))))
  const workerPreview = await previewNativeReadRuntime(readFilePath, root)
  assert.equal(workerPreview.application_opened, false)
  assert.equal(workerPreview.interface_read, false)
  assert.equal(workerPreview.actions_authorized, false)
  assert.ok(!Object.hasOwn(workerPreview.runtime, "browser"))
  await assert.rejects(prepareNativeReadRuntime(readFilePath, { evidenceRoot: root, workspace: root, confirmation: "0".repeat(64) }), /confirm/)
  const workerConfig = await prepareNativeReadRuntime(readFilePath, { evidenceRoot: root, workspace: root, confirmation: workerPreview.sha256 })
  assert.equal((await lstat(workerConfig.config_file)).mode & 0o777, 0o600)
  const sdk = fileURLToPath(new URL("../../instrument-gateway", import.meta.url))
  const metadataCheck = "import sys;from pathlib import Path;from airalogy_instrument_gateway.interface_process import NativeReadProcessClient,verify_native_read_runtime,InterfaceProcessError;c=NativeReadProcessClient.from_file(Path(sys.argv[1]));assert verify_native_read_runtime(c.config)['schema']=='airalogy.native-read-worker-runtime.v1';\ntry:c.call('probe')\nexcept InterfaceProcessError:pass\nelse:raise AssertionError('Fabricated process must never attach')"
  await promisify(execFile)("python3", ["-c", metadataCheck, workerConfig.config_file], { env: { ...process.env, PYTHONPATH: join(sdk, "src") }, timeout: 15000 })
  assert.deepEqual((await nativeCall(built.build_file, { operation: "inspect_application", bundle_path: built.simulator_app })).running, [])
  await assert.rejects(nativeCall(built.build_file, { operation: "click", target: "arbitrary" }), /invalid_request/)
  await assert.rejects(nativeCall(built.build_file, { operation: "doctor", prompt: true }), /invalid_request/)
  if (!doctor.interactive_session.ready) {
    const bundle = await nativeCall(built.build_file, { operation: "inspect_bundle", bundle_path: built.simulator_app })
    await assert.rejects(nativeCall(built.build_file, { operation: "launch_application", bundle }), /interactive_session_required/)
    const request = await prepareNativeLaunch({ buildFile: built.build_file, bundlePath: built.simulator_app, reason: "Verify inactive-session refusal on the owned fixture", workspace: root })
    await assert.rejects(runNativeLaunch(request.request_file, { confirmation: request.preview_digest, acknowledgeInitialization: true }), /interactive_session_required/)
    assert.equal((await nativeLaunchStatus(request.request_file)).state, "not_started")
    const cli = fileURLToPath(new URL("../src/native-cli.mjs", import.meta.url))
    await assert.rejects(promisify(execFile)(process.execPath, [cli, "launch", "--request", request.request_file, "--confirm", request.preview_digest, "--ack-initialization"], { timeout: 15000 }), (error) => {
      assert.match(error.stderr, /interactive_session_required/)
      assert.ok(!error.stderr.includes(root))
      return true
    })
    assert.equal((await nativeLaunchStatus(request.request_file)).state, "not_started")
    const inspection = await nativeCall(built.build_file, { operation: "inspect_application", bundle_path: built.simulator_app })
    assert.deepEqual(inspection.running, [])
  }
  if (real)
    assert.equal(doctor.interactive_session.ready, true, "Unlock and keep the operator graphical session active before GUI acceptance; tests never unlock or wake it")

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
      await focusOwnedFixture(built.build_file, child.pid)
      const selection = await selectNative({ buildFile: built.build_file, bundlePath: built.simulator_app, pid: child.pid, title: "Airalogy Native Reader — Simulation", redactIdentifiers: ["private.note"] })
      await waitForOwnedWindow(built, selection.target.source.pin)
      let guidedOutput = ""
      const guided = await guideNative({ requestFile: discovery.request_file, buildFile: built.build_file, workspace: root, locale: "en-US", redactIdentifiers: ["private.note"] }, {
        write: value => guidedOutput += value,
        question: async (prompt) => {
          let answer
          if (prompt.startsWith("Choose"))
            answer = "1"
          else if (prompt.startsWith("Identity number"))
            answer = guidedOutput.match(/^(\d+)\. "app\.identity"/m)?.[1]
          else if (prompt.startsWith("Readback numbers"))
            answer = guidedOutput.match(/^(\d+)\. "reader\.status"/m)?.[1]
          else
            answer = guidedOutput.match(/确认摘要：([a-f0-9]{64})/)?.[1] || guidedOutput.trim().split("\n").at(-1)
          guidedOutput = ""
          assert.ok(answer, "Expected an explicitly observed owned-fixture control/confirmation")
          return answer
        },
      })
      assert.equal(guided.state, "draft_created")
      assert.equal(guided.hardware_qualified, false)
      assert.equal(JSON.parse(await readFile(guided.draft.definition_file)).schema, "airalogy.native-read-definition.v1")
      assert.ok(!guided.launch_request)
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
      const installedRead = await prepareOwnedReadRuntime(built, child.pid, root)
      await verifyIndependentNativeInstalls(installedRead.config_file)
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
      for (const mode of ["ai_off", "cancel", "invalid", "lost_receipt"]) {
        const policy = { goal: "Verify governed synthetic parameter re-entry", actions: [{ operation: "fill", control_id: "sample_count", value: "2", before: "complete", after: "complete" }], success: [{ control_id: "result", equals: "0.84" }] }
        const files = await prepareExploration({ definition: actionTemplate.definition, policy, workspace: root, platformUrl: "http://127.0.0.1/", gatewayId: "11111111-1111-1111-1111-111111111111", resourceId: "22222222-2222-2222-2222-222222222222" })
        const request = JSON.parse(await readFile(files.authorization_file))
        assert.equal(request.spec.target.kind, "native_macos_simulation")
        assert.ok(!canonical(request).includes(built.build_file) && !canonical(request).includes("started_seconds"))
        let allowed = mode !== "ai_off"
        let proposals = 0
        let savedReport = null
        let calls = 0
        const client = { async call(operation, payload = {}) {
          if (operation === "status")
            return { can_proceed: allowed, effective_state: allowed ? "open" : "cancelled", request, turns: [], expires_at: new Date(Date.now() + 600000).toISOString() }
          if (operation === "turns") {
            proposals += 1
            if (mode === "cancel")
              allowed = false
            const proposal = { kind: "act", action_index: mode === "invalid" ? 63 : 0, summary: "Synthetic action choice", missing_information: [] }
            return { id: payload.id, previous_id: payload.previous_id, input: { observation: payload.observation, evidence_digest: payload.evidence_digest }, state: "generated", proposal, candidate_digest: digest(proposal) }
          }
          if (operation === "report") {
            calls += 1
            if (savedReport)
              assert.deepEqual(payload.report, savedReport)
            savedReport = payload.report
            if (calls === 1)
              throw new Error("Synthetic lost action receipt")
            return {}
          }
          throw new Error("Unexpected model operation")
        } }
        await assert.rejects(runExploration(files.request_file, { confirmation: files.local_preview_digest, client }))
        assert.equal(proposals, mode === "ai_off" ? 0 : 1)
        if (mode === "lost_receipt") {
          assert.equal(savedReport.outcome, "executed")
          assert.equal(savedReport.after.values.sample_count, "2")
          allowed = false
          const synced = await syncExploration(files.request_file, { client })
          assert.equal(synced.synced_reports, 1)
          assert.equal(synced.native_actions_executed, false)
          assert.equal(proposals, 1)
        }
        else { assert.equal(savedReport, null) }
        // Even a server claiming a fresh empty history cannot bypass the local marker.
        if (mode !== "ai_off") {
          allowed = true
          await assert.rejects(runExploration(files.request_file, { confirmation: files.local_preview_digest, client }), /EEXIST/)
          assert.equal(proposals, 1)
        }
      }
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
  await t.test("confirmed LaunchServices startup, immutable receipt and separate read-only survey", { skip: !real, timeout: 120000 }, async () => {
    const prepared = await prepareNativeLaunch({ buildFile: built.build_file, bundlePath: built.simulator_app, reason: "Only launch this owned synthetic test fixture", workspace: root })
    const request = JSON.parse(await readFile(prepared.request_file))
    const preview = validateLaunchPreview(request.preview)
    assert.equal(prepared.applications_opened, false)
    assert.equal((await nativeLaunchStatus(prepared.request_file)).state, "not_started")
    for (const mutate of [
      value => value.effects.activates = true,
      value => value.effects.ui_actions_approved = true,
      value => value.effects.arguments = ["--arbitrary"],
      value => value.arguments = ["--arbitrary"],
      value => value.bundle.executable_sha256 = "changed",
      value => value.expires_at = "tomorrow",
    ]) {
      const invalid = structuredClone(preview)
      mutate(invalid)
      assert.throws(() => validateLaunchPreview(invalid))
    }
    await assert.rejects(runNativeLaunch(prepared.request_file, { confirmation: prepared.preview_digest }), /acknowledge/)
    await assert.rejects(runNativeLaunch(prepared.request_file, { confirmation: "0".repeat(64), acknowledgeInitialization: true }), /Confirm/)
    assert.ok(!(await readdir(dirname(prepared.request_file))).includes("launch.started"))
    const expired = { ...preview, expires_at: new Date(Date.now() - 1000).toISOString() }
    const expiredDirectory = await Evidence.create(root, expired)
    await expiredDirectory.write("request.json", Buffer.from(canonical({ preview: expired, preview_digest: digest(expired) })))
    await assert.rejects(runNativeLaunch(join(expiredDirectory.directory, "request.json"), { confirmation: digest(expired), acknowledgeInitialization: true }), /expired/)
    for (const changed of [
      { ...preview, bundle: { ...preview.bundle, version: "unreviewed" } },
      { ...preview, engine: { ...preview.engine, os_version: "changed runtime" } },
    ]) {
      const files = await Evidence.create(root, changed)
      await files.write("request.json", Buffer.from(canonical({ preview: changed, preview_digest: digest(changed) })))
      await assert.rejects(runNativeLaunch(join(files.directory, "request.json"), { confirmation: digest(changed), acknowledgeInitialization: true }), /changed/)
      assert.ok(!(await readdir(files.directory)).includes("launch.started"))
    }
    await chmod(prepared.request_file, 0o644)
    await assert.rejects(runNativeLaunch(prepared.request_file, { confirmation: prepared.preview_digest, acknowledgeInitialization: true }), /owner-only/)
    await chmod(prepared.request_file, 0o600)
    const cli = fileURLToPath(new URL("../src/native-cli.mjs", import.meta.url))
    let launched = null
    try {
      launched = JSON.parse((await promisify(execFile)(process.execPath, [cli, "launch", "--request", prepared.request_file, "--confirm", prepared.preview_digest, "--ack-initialization"], { timeout: 45000 })).stdout)
      assert.equal(launched.pin.bundle.bundle_path, built.simulator_app)
      assert.equal(launched.identity_verified, true)
      assert.equal(launched.ui_actions_approved, false)
      assert.equal(launched.hardware_qualified, false)
      assert.equal(launched.application_left_running, true)
      await assert.rejects(prepareNativeLaunch({ buildFile: built.build_file, bundlePath: built.simulator_app, reason: "Duplicate", workspace: root }), /already_running/)
      const status = JSON.parse((await promisify(execFile)(process.execPath, [cli, "launch-status", "--request", prepared.request_file], { timeout: 5000 })).stdout)
      assert.equal(status.state, "reported_identity_verified")
      assert.equal(status.current_process_state, "not_checked")
      assert.equal(status.applications_opened, false)
      const inspection = JSON.parse((await promisify(execFile)(process.execPath, [cli, "inspect", "--build", built.build_file, "--bundle", built.simulator_app], { timeout: 15000 })).stdout)
      assert.deepEqual(inspection.running, [launched.pin])
      assert.equal(inspection.unresolved_instances, 0)
      assert.equal(inspection.ui_observed, false)
      const selected = await selectNative({ buildFile: built.build_file, bundlePath: built.simulator_app, pid: launched.pin.process.pid, title: "Airalogy Native Reader — Simulation", redactIdentifiers: ["private.note"] })
      await waitForOwnedWindow(built, selected.target.source.pin)
      const survey = await prepareSurvey(selected, root)
      const captured = await runPreparedSurvey(survey.request_file, survey.local_preview_digest)
      const report = JSON.parse(await readFile(captured.report_file))
      assert.equal(report.controls.find(control => control.locator?.name === "reader.status").value, "Ready")
      assert.equal(captured.actions_executed, 0)
      assert.ok(!canonical(report).includes("SYNTHETIC_PRIVATE") && !canonical(report).includes("SYNTHETIC_PASSWORD"))
    }
    finally {
      // Only this newly built owned fixture. Never use a generic app-name kill.
      await closeOwnedLaunch(built)
    }
    assert.equal((await nativeLaunchStatus(prepared.request_file)).state, "reported_identity_verified")
    await assert.rejects(runNativeLaunch(prepared.request_file, { confirmation: prepared.preview_digest, acknowledgeInitialization: true }), /EEXIST/)
    const uncertain = await Evidence.create(root, preview)
    await uncertain.write("request.json", Buffer.from(canonical(request)))
    await uncertain.write("launch.started", Buffer.from(prepared.preview_digest))
    assert.equal((await nativeLaunchStatus(join(uncertain.directory, "request.json"))).state, "uncertain")
    await assert.rejects(runNativeLaunch(join(uncertain.directory, "request.json"), { confirmation: prepared.preview_digest, acknowledgeInitialization: true }), /EEXIST/)
    // Receipt inspection works without executing the now-inapplicable old helper.
    await chmod(built.helper, 0o744)
    assert.equal((await nativeLaunchStatus(prepared.request_file)).state, "reported_identity_verified")
    await chmod(built.helper, 0o700)
    t.diagnostic(`Private launch receipt: ${launched.receipt_file}`)
  })
  await t.test("separate concurrently approved requests cannot start duplicate owned instances", { skip: !real, timeout: 60000 }, async () => {
    const requests = await Promise.all(["first", "second"].map(reason => prepareNativeLaunch({ buildFile: built.build_file, bundlePath: built.simulator_app, reason: `Synthetic concurrency ${reason}`, workspace: root })))
    try {
      const outcomes = await Promise.allSettled(requests.map(request => runNativeLaunch(request.request_file, { confirmation: request.preview_digest, acknowledgeInitialization: true })))
      assert.equal(outcomes.filter(item => item.status === "fulfilled").length, 1)
      assert.equal(outcomes.filter(item => item.status === "rejected").length, 1)
      const inspection = await nativeCall(built.build_file, { operation: "inspect_application", bundle_path: built.simulator_app })
      assert.equal(inspection.running.length, 1)
      assert.equal(inspection.unresolved_instances, 0)
    }
    finally { await closeOwnedLaunch(built) }
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
