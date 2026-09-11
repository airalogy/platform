/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { execFile } from "node:child_process"
import { chmod, lstat, readdir, readFile, rename, symlink, writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"
import { promisify } from "node:util"
import { BrowserInterfaceSession, previewInterface } from "../src/browser-session.mjs"
import { canonical, digest } from "../src/contract.mjs"
import { Evidence } from "../src/evidence.mjs"
import { chooseNumbers, confirmManualSurvey, previewManualSurvey, reviewSurvey, surveyChoices, terminalJson } from "../src/survey-review.mjs"
import { inspectPreparedSurvey, prepareSurvey, readPreparedSurvey, runPreparedSurvey } from "../src/survey-workspace.mjs"
import { fixture } from "./fixture.mjs"

const exec = promisify(execFile)
const cli = fileURLToPath(new URL("../src/survey-cli.mjs", import.meta.url))
const reportFixture = JSON.parse(await readFile(new URL("fixtures/survey.json", import.meta.url), "utf8"))
const chosen = { identity_control: "observed.1", read_controls: ["observed.3"] }

function selection(definition) {
  const { controls: _controls, states: _states, ...value } = structuredClone(definition)
  delete value.target.identity
  return { ...value, schema: "airalogy.interface-survey-selection.v1", capture_values: false, limits: { ...value.limits, max_steps: 1 } }
}

// Explicit synthetic historical receipt, not a claim of actual native capture.
async function savedFixture({ native = false } = {}) {
  const target = await fixture()
  let prepared
  const report = structuredClone(reportFixture)
  if (native) {
    const selected = {
      schema: "airalogy.native-survey-selection.v1",
      id: "native.fixture",
      build_file: join(target.root, "missing-build.json"),
      capture_values: false,
      redact_identifiers: [],
      target: { application: "Synthetic reader", version: "1.0", title: "Synthetic interface", locale: "en-US", source: { kind: "native_macos", pin: {
        bundle: { bundle_path: join(target.root, "Missing.app"), executable_path: join(target.root, "Missing.app/Contents/MacOS/Missing"), bundle_id: "org.airalogy.fixture", version: "1.0", executable_sha256: "a".repeat(64), info_sha256: "b".repeat(64), code_directory_hash: "c".repeat(40) },
        process: { pid: 123, uid: 501, started_seconds: "123456", started_microseconds: "123" },
      } } },
    }
    const payload = { schema: "airalogy.interface-survey-preview.v1", engine: { fixture: "historical; no helper installed" }, definition: selected }
    const preview = { ...payload, sha256: digest(payload) }
    const saved = await Evidence.create(target.root, preview)
    await saved.write("request.json", Buffer.from(canonical({ selection: selected, preview_digest: preview.sha256 })))
    prepared = { request_file: join(saved.directory, "request.json"), local_preview_digest: preview.sha256 }
    report.target.kind = "native_macos"
    report.controls = report.controls.filter(control => control.read === "text").map(control => ({ ...control, role: "AXStaticText", locator: { kind: "ax_identifier", role: "AXStaticText", name: control.id } }))
  }
  else { prepared = await prepareSurvey(selection(target.definition), target.root) }
  report.preview_digest = prepared.local_preview_digest
  const root = dirname(prepared.request_file)
  const saved = new Evidence(root)
  await saved.write("run.started", Buffer.from(prepared.local_preview_digest))
  const capture = await Evidence.create(root, { fixture: true })
  await capture.write("survey.json", Buffer.from(canonical(report)))
  const result = { evidence: capture.directory, report_file: join(capture.directory, "survey.json"), report_digest: digest(report), actions_executed: 0, hardware_qualified: false }
  await saved.write("result.json", Buffer.from(canonical(result)))
  return { ...target, ...prepared, report, result }
}

test("status distinguishes prepared, unresolved and completed evidence without revisiting software", async () => {
  const target = await fixture()
  const prepared = await prepareSurvey(selection(target.definition), target.root)
  await rename(target.definition.target.source.path, join(target.root, "removed.html"))
  assert.equal((await inspectPreparedSurvey(prepared.request_file)).state, "prepared")
  const root = dirname(prepared.request_file)
  await new Evidence(root).write("run.started", Buffer.from(prepared.local_preview_digest))
  const unresolved = await inspectPreparedSurvey(prepared.request_file)
  assert.equal(unresolved.state, "observation_unresolved")
  assert.equal(unresolved.retry_allowed, false)
  await assert.rejects(readPreparedSurvey(prepared.request_file))
  await assert.rejects(runPreparedSurvey(prepared.request_file, prepared.local_preview_digest))
  const saved = await savedFixture()
  await rename(saved.definition.target.source.path, join(saved.root, "removed.html"))
  const status = JSON.parse((await exec(process.execPath, [cli, "status", saved.request_file])).stdout)
  assert.equal(status.state, "snapshot_saved")
  assert.equal(status.application_opened, false)
  const preview = await previewManualSurvey(saved.request_file, chosen, saved.root)
  const draft = await confirmManualSurvey(saved.request_file, chosen, saved.root, preview.sha256)
  // Historical assembly may succeed, but reopening still checks source bytes.
  await assert.rejects(previewInterface(JSON.parse(await readFile(draft.definition_file)), { schema: "airalogy.interface-plan.v1", steps: [] }))
})

test("manual selection is explicit, bounded and preserves value/locator privacy", () => {
  const { reads, identities } = surveyChoices(reportFixture)
  assert.deepEqual(reads.map(control => control.id), ["observed.1", "observed.3"])
  assert.equal(identities.length, 2)
  assert.deepEqual(chooseNumbers("2,1", reads, { multiple: true }), ["observed.3", "observed.1"])
  for (const invalid of ["", "0", "-1", "3", "1,1", "1, 2", "1-2", "1e0", "NaN", "9".repeat(200)])
    assert.throws(() => chooseNumbers(invalid, reads, { multiple: true }))
  assert.throws(() => chooseNumbers("1,2", reads))
  const privateReport = structuredClone(reportFixture)
  privateReport.controls[0].locator = null
  privateReport.controls[2].value = "x".repeat(513)
  assert.equal(surveyChoices(privateReport).identities.length, 0)
  assert.equal(terminalJson("\x1B]52;c;secret\x07\u009B\u202E\n").includes("\x1B"), false)
  assert.match(terminalJson("\u202E\u009B"), /\\u202e\\u009b/)
})

test("review confirmation pins fields, saved evidence and destination, writes only a new private draft", async () => {
  const saved = await savedFixture()
  const before = await readdir(saved.root)
  const preview = await previewManualSurvey(saved.request_file, chosen, saved.root)
  assert.deepEqual(await readdir(saved.root), before)
  await assert.rejects(confirmManualSurvey(saved.request_file, chosen, saved.root, "yes"))
  await assert.rejects(confirmManualSurvey(saved.request_file, { ...chosen, read_controls: [] }, saved.root, preview.sha256))
  const other = await fixture()
  await assert.rejects(confirmManualSurvey(saved.request_file, chosen, other.root, preview.sha256))
  await assert.rejects(previewManualSurvey(saved.request_file, { ...chosen, read_controls: ["observed.2"] }, saved.root))
  await assert.rejects(previewManualSurvey(saved.request_file, { ...chosen, actions: ["click"] }, saved.root))
  const draft = await confirmManualSurvey(saved.request_file, chosen, saved.root, preview.sha256)
  assert.equal((await lstat(dirname(draft.definition_file))).mode & 0o777, 0o700)
  assert.equal((await lstat(draft.review_file)).mode & 0o777, 0o600)
  assert.deepEqual(JSON.parse(await readFile(draft.review_file)), preview)
  assert.equal(draft.actions_approved, false)
  assert.equal(draft.hardware_qualified, false)
  assert.deepEqual(JSON.parse(await readFile(draft.plan_file)).steps, [])
  assert.ok(JSON.parse(await readFile(draft.definition_file)).controls.every(control => canonical(control.operations) === '["read"]'))
})

test("interactive review has no inferred default; cancellation never creates a draft", async () => {
  const saved = await savedFixture()
  const before = await readdir(saved.root)
  let output = ""
  let prompts = 0
  const result = await reviewSurvey(saved.request_file, saved.root, {
    write: value => output += value,
    question: async () => {
      assert.deepEqual(await readdir(saved.root), before)
      prompts++
      if (prompts < 3)
        return prompts === 1 ? "1" : "2"
      return (await previewManualSurvey(saved.request_file, chosen, saved.root)).sha256
    },
  })
  assert.equal(prompts, 3)
  assert.ok(result.review_file)
  assert.match(output, /历史观察/)
  assert.match(output, /保存范围/)
  const current = await readdir(saved.root)
  for (const answer of ["", "cancel"]) {
    await assert.rejects(reviewSurvey(saved.request_file, saved.root, { write: () => {}, question: async () => answer }))
    assert.deepEqual(await readdir(saved.root), current)
  }
  let cancelledPrompt = 0
  await assert.rejects(reviewSurvey(saved.request_file, saved.root, { write: () => {}, question: async () => {
    cancelledPrompt++
    return cancelledPrompt === 1 ? "1" : cancelledPrompt === 2 ? "2" : "cancel"
  } }))
  assert.equal(cancelledPrompt, 3)
  assert.deepEqual(await readdir(saved.root), current)
  await assert.rejects(exec(process.execPath, [cli, "review", saved.request_file, "--workspace", saved.root]))
  await assert.rejects(exec(process.execPath, [cli, "status", saved.request_file, "--confirm", "any"]))
  assert.deepEqual(await readdir(saved.root), current)
})

test("a changed capture cannot be saved using the earlier manual confirmation", async () => {
  const saved = await savedFixture()
  const preview = await previewManualSurvey(saved.request_file, chosen, saved.root)
  const before = await readdir(saved.root)
  const changed = structuredClone(saved.report)
  changed.controls[2].value = "Different historical value"
  await writeFile(saved.result.report_file, canonical(changed))
  await writeFile(join(dirname(saved.request_file), "result.json"), canonical({ ...saved.result, report_digest: digest(changed) }))
  // A coherent owner-edited report still requires a new, visible confirmation.
  assert.equal((await inspectPreparedSurvey(saved.request_file)).state, "snapshot_saved")
  await assert.rejects(confirmManualSurvey(saved.request_file, chosen, saved.root, preview.sha256))
  assert.deepEqual(await readdir(saved.root), before)
})

test("native saved review works without a helper, application or live process and retains pins", async () => {
  const saved = await savedFixture({ native: true })
  const preview = await previewManualSurvey(saved.request_file, chosen, saved.root)
  assert.equal(preview.draft.definition.schema, "airalogy.native-read-definition.v1")
  const draft = await confirmManualSurvey(saved.request_file, chosen, saved.root, preview.sha256)
  const definition = JSON.parse(await readFile(draft.definition_file))
  assert.equal(definition.selection.target.source.pin.process.pid, 123)
  assert.equal(definition.selection.build_file, join(saved.root, "missing-build.json"))
  assert.equal(definition.selection.capture_values, false)
  assert.ok(definition.controls.every(control => canonical(control.operations) === '["read"]'))
})

test("unreadable, changed, foreign or incomplete retained receipts fail closed", async () => {
  for (const change of [
    saved => chmod(saved.request_file, 0o644),
    saved => writeFile(join(dirname(saved.request_file), "run.started"), "wrong"),
    saved => writeFile(join(dirname(saved.request_file), "result.json"), "{"),
    saved => writeFile(saved.result.report_file, canonical({ ...saved.report, omitted_private: 2 })),
    saved => writeFile(join(dirname(saved.request_file), "result.json"), canonical({ ...saved.result, report_file: join(saved.root, "foreign.json") })),
    async (saved) => {
      const changed = { ...saved.report, capture_values: true }
      await writeFile(saved.result.report_file, canonical(changed))
      await writeFile(join(dirname(saved.request_file), "result.json"), canonical({ ...saved.result, report_digest: digest(changed) }))
    },
    async (saved) => {
      await rename(saved.result.report_file, join(dirname(saved.result.report_file), "original.json"))
      await symlink(join(dirname(saved.result.report_file), "original.json"), saved.result.report_file)
    },
  ]) {
    const saved = await savedFixture()
    await change(saved)
    await assert.rejects(inspectPreparedSurvey(saved.request_file))
    await assert.rejects(previewManualSurvey(saved.request_file, chosen, saved.root))
  }
})

test("actual headless capture feeds guided review and a separately confirmed read-only session", { skip: process.env.RUN_INTERFACE_BROWSER_TESTS !== "1" }, async () => {
  const target = await fixture()
  const prepared = await prepareSurvey(selection(target.definition), target.root)
  await runPreparedSurvey(prepared.request_file, prepared.local_preview_digest)
  const { report } = await readPreparedSurvey(prepared.request_file)
  const options = surveyChoices(report)
  const identity = options.identities.findIndex(control => control.role === "heading")
  const status = options.reads.findIndex(control => control.locator?.name === "status")
  const choices = { identity_control: options.identities[identity].id, read_controls: [options.reads[status].id] }
  let prompt = 0
  const draft = await reviewSurvey(prepared.request_file, target.root, { write: () => {}, question: async () => {
    prompt++
    return prompt === 1 ? String(identity + 1) : prompt === 2 ? String(status + 1) : (await previewManualSurvey(prepared.request_file, choices, target.root)).sha256
  } })
  const definition = JSON.parse(await readFile(draft.definition_file))
  const plan = JSON.parse(await readFile(draft.plan_file))
  const preview = await previewInterface(definition, plan)
  const session = await BrowserInterfaceSession.open({ definition, plan, confirmation: preview.sha256, evidenceRoot: target.root })
  try {
    assert.equal(session.lastObservation.state, "observed")
  }
  finally { await session.close() }
  await assert.rejects(runPreparedSurvey(prepared.request_file, prepared.local_preview_digest))
})
