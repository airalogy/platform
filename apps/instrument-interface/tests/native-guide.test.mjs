/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { execFile } from "node:child_process"
import { mkdtemp, readFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"
import { promisify } from "node:util"
import { canonical, digest } from "../src/contract.mjs"
import { Evidence } from "../src/evidence.mjs"
import { guideNative } from "../src/native-guide.mjs"

async function fixture({ stopped = false } = {}) {
  const root = await mkdtemp(join(tmpdir(), "airalogy-native-guide-test-"))
  const bundle = { bundle_path: "/synthetic/Reader.app", executable_path: "/synthetic/Reader.app/Contents/MacOS/Reader", bundle_id: "org.airalogy.fixture", version: "1.0", executable_sha256: "a".repeat(64), info_sha256: "b".repeat(64), code_directory_hash: "c".repeat(40) }
  const pin = { bundle, process: { pid: 123, uid: 501, started_seconds: "123456", started_microseconds: "123" } }
  const inspection = { bundle, running: stopped ? [] : [pin], unresolved_instances: 0 }
  const options = { requestFile: join(root, "discovery.json"), buildFile: join(root, "build.json"), workspace: root, locale: "en-US", redactIdentifiers: ["private.note"] }
  const calls = []
  const record = name => calls.push(name)
  const operations = {
    nativeDiscoveryResult: async () => ({ report: { directory: { path: "/synthetic" }, stopped_reason: null, skipped: {}, applications: [{ bundle_path: bundle.bundle_path, metadata_status: "read", declared: { info_sha256: bundle.info_sha256 } }] } }),
    validateNativeBuild: async () => ({ manifest: { fixture: "trusted test backend; no GUI/hardware" } }),
    prepareApplicationSelection: async () => ({ selection_file: join(root, "selection.json") }),
    resolveApplicationSelection: async () => {
      record("inspect")
      return { inspection }
    },
    prepareNativeLaunch: async ({ workspace }) => {
      record("prepare_launch")
      const preview = { bundle, effects: { initialization_may_control_equipment: true } }
      const evidence = await Evidence.create(workspace, preview)
      return { request_file: join(evidence.directory, "request.json"), preview_file: join(evidence.directory, "preview.json"), preview_digest: digest(preview) }
    },
    runNativeLaunch: async (_path, approval) => {
      record("launch")
      assert.equal(approval.acknowledgeInitialization, true)
      return { pin, application_left_running: true }
    },
    nativeCall: async (_build, request) => {
      assert.equal(request.operation, "inspect_windows")
      assert.deepEqual(request.pin, pin)
      record("windows")
      return { windows: [{ role: "AXWindow", title: "Owned fixture", minimized: false, has_geometry: true }] }
    },
    selectNative: async ({ captureValues, redactIdentifiers }) => {
      assert.equal(captureValues, false)
      assert.deepEqual(redactIdentifiers, ["private.note"])
      record("select")
      return { target: { source: { pin } } }
    },
    prepareSurvey: async (selection, workspace) => {
      record("prepare_survey")
      const payload = { schema: "airalogy.interface-survey-preview.v1", definition: selection, engine: {} }
      const sha256 = digest(payload)
      const saved = await Evidence.create(workspace, { ...payload, sha256 })
      return { request_file: join(saved.directory, "request.json"), local_preview_digest: sha256 }
    },
    runPreparedSurvey: async () => {
      record("capture")
      return { report_file: join(root, "report.json") }
    },
    reviewSurvey: async () => {
      record("review")
      return { definition_file: join(root, "definition.json"), actions_approved: false }
    },
  }
  let output = ""
  let latest = ""
  const terminal = {
    write: (value) => {
      output += value
      latest = value
    },
    question: async (prompt) => {
      if (prompt.startsWith("Choose"))
        return "1"
      if (prompt.startsWith("Software"))
        return "Authorized owned simulation only"
      assert.match(latest, /(?:INITIALIZE )?[a-f0-9]{64}\n$/)
      return latest.trim().split("\n").at(-1)
    },
  }
  return { options, operations, terminal, calls, inspection, pin, output: () => output }
}

test("native guide joins existing gates and retains scope without launching an existing process", async () => {
  const f = await fixture()
  const result = await guideNative(f.options, f.terminal, f.operations)
  assert.equal(result.state, "draft_created")
  assert.equal(result.hardware_qualified, false)
  assert.equal(result.installation_approved, false)
  assert.deepEqual(f.calls, ["inspect", "windows", "select", "prepare_survey", "capture", "review"])
  assert.deepEqual(JSON.parse(await readFile(join(result.guide_directory, "guide-result.json"))), result)
  assert.ok(result.selection_file && result.survey_request && result.report_file)
})

test("startup is a separately acknowledged one-shot operation, never inherited from inspection", async () => {
  const f = await fixture({ stopped: true })
  const result = await guideNative(f.options, f.terminal, f.operations)
  assert.equal(result.state, "draft_created")
  assert.equal(f.calls.filter(call => call === "launch").length, 1)
  assert.ok(result.launch_request)
  assert.match(f.output(), /INITIALIZE [a-f0-9]{64}/)
  const denied = await fixture({ stopped: true })
  const question = denied.terminal.question
  denied.terminal.question = async (prompt) => {
    const answer = await question(prompt)
    return answer.startsWith("INITIALIZE ") ? answer.slice(11) : answer
  }
  const cancelled = await guideNative(denied.options, denied.terminal, denied.operations)
  assert.equal(cancelled.stage, "launch_application")
  assert.equal(cancelled.state, "needs_attention")
  assert.equal(cancelled.reason, "operator_cancelled")
  assert.deepEqual(denied.calls, ["inspect", "prepare_launch"])
})

test("lost launch or survey response preserves recovery, never retries or moves forward", async () => {
  for (const failed of ["runNativeLaunch", "runPreparedSurvey"]) {
    const f = await fixture({ stopped: true })
    let attempts = 0
    f.operations[failed] = async () => {
      attempts++
      throw new Error("synthetic private failure content")
    }
    const result = await guideNative(f.options, f.terminal, f.operations)
    assert.equal(result.state, "needs_attention")
    assert.equal(attempts, 1)
    assert.equal(result.automatic_retry, false)
    assert.equal(result.physical_safe_stop_confirmed, false)
    assert.ok(result.launch_request)
    if (failed === "runPreparedSurvey")
      assert.ok(result.survey_request)
    assert.equal(f.calls.includes("review"), false)
    assert.ok(!canonical(result).includes("synthetic private failure content"))
    assert.deepEqual(JSON.parse(await readFile(join(result.guide_directory, "guide-stopped.json"))), result)
  }
})

test("conflicts, process lifetime drift and unsupported windows stop before capture", async () => {
  for (const mutate of [
    f => f.inspection.unresolved_instances = 1,
    f => f.operations.nativeCall = async () => ({ windows: [] }),
    f => f.operations.nativeCall = async () => ({ windows: [{ role: "AXWindow", title: "one", minimized: false, has_geometry: true }, { role: "AXWindow", title: "two", minimized: false, has_geometry: true }] }),
    f => f.operations.nativeCall = async () => ({ windows: [{ role: "AXWindow", title: "one", minimized: true, has_geometry: true }] }),
    f => f.operations.selectNative = async () => ({ target: { source: { pin: { ...f.pin, process: { ...f.pin.process, started_seconds: "999" } } } } }),
  ]) {
    const f = await fixture()
    mutate(f)
    const result = await guideNative(f.options, f.terminal, f.operations)
    assert.equal(result.state, "needs_attention")
    assert.ok(!f.calls.includes("capture") && !f.calls.includes("launch"))
  }
})

test("cancellation and a changed helper build cannot dispatch the next operation", async () => {
  for (const variant of ["cancel", "build", "abort"]) {
    const f = await fixture()
    const question = f.terminal.question
    const controller = new AbortController()
    f.terminal.signal = controller.signal
    f.terminal.question = async (prompt) => {
      const answer = await question(prompt)
      if (prompt.startsWith("Type")) {
        if (variant === "cancel")
          return ""
        if (variant === "build")
          f.operations.validateNativeBuild = async () => ({ manifest: { changed: true } })
        if (variant === "abort")
          controller.abort()
      }
      return answer
    }
    const result = await guideNative(f.options, f.terminal, f.operations)
    assert.equal(result.state, "needs_attention")
    assert.deepEqual(f.calls, [])
  }
})

test("CLI refuses piped guide confirmations before reading files or starting a helper", async () => {
  const cli = fileURLToPath(new URL("../src/native-cli.mjs", import.meta.url))
  await assert.rejects(promisify(execFile)(process.execPath, [cli, "guide", "--request", "/not-read", "--build", "/not-run", "--workspace", "/not-created"]))
})

test("guide cannot write evidence into the discovered application directory", async () => {
  const f = await fixture()
  const report = (await f.operations.nativeDiscoveryResult()).report
  const { realpath, readdir, mkdir } = await import("node:fs/promises")
  report.directory.path = await realpath(f.options.workspace)
  f.operations.nativeDiscoveryResult = async () => ({ report })
  const before = await readdir(f.options.workspace)
  await assert.rejects(guideNative(f.options, f.terminal, f.operations), /outside/)
  assert.deepEqual(await readdir(f.options.workspace), before)
  assert.deepEqual(f.calls, [])
  report.directory.path = "/synthetic"
  const appDirectory = join(f.options.workspace, "Unrelated.app")
  await mkdir(appDirectory, { mode: 0o700 })
  await assert.rejects(guideNative({ ...f.options, workspace: appDirectory }, f.terminal, f.operations), /outside/)
  assert.deepEqual(await readdir(appDirectory), [])
})
