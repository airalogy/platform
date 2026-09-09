/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { execFile } from "node:child_process"
import { chmod, readdir, readFile, writeFile } from "node:fs/promises"
import { join } from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"
import { promisify } from "node:util"
import { BrowserInterfaceSession, previewInterface } from "../src/browser-session.mjs"
import { previewSurvey, runSurvey } from "../src/survey.mjs"
import { prepareSurvey, runPreparedSurvey } from "../src/survey-workspace.mjs"
import { emptyPlan, fixture, html } from "./fixture.mjs"

function selection(definition, capture = false) {
  const { controls: _controls, states: _states, ...selected } = structuredClone(definition)
  delete selected.target.identity
  return { ...selected, schema: "airalogy.interface-survey-selection.v1", capture_values: capture, limits: { ...selected.limits, max_steps: 1 } }
}

test("survey previews reject drift, extra authority and implicit capture consent", async () => {
  const target = await fixture()
  const chosen = selection(target.definition)
  const preview = await previewSurvey(chosen)
  assert.ok(Object.isFrozen(preview.definition.target))
  await assert.rejects(previewSurvey({ ...chosen, capture_values: undefined }))
  await assert.rejects(previewSurvey({ ...chosen, actions: ["click"] }))
  await assert.rejects(previewSurvey({ ...chosen, limits: { ...chosen.limits, max_steps: 2 } }))
  await assert.rejects(previewSurvey({ ...chosen, target: { ...chosen.target, source: { ...chosen.target.source, sha256: "0".repeat(64) } } }))
  await assert.rejects(runSurvey(chosen, { confirmation: "0".repeat(64), evidenceRoot: target.root }), /Confirm/)
})

const browserTest = (name, fn) => test(name, { skip: process.env.RUN_INTERFACE_BROWSER_TESTS !== "1" }, fn)
const exec = promisify(execFile)
const cli = fileURLToPath(new URL("../src/survey-cli.mjs", import.meta.url))

test("prepared survey denies missing consent, runtime drift and shared credential directories without launching", async () => {
  const target = await fixture()
  const prepared = await prepareSurvey(selection(target.definition), target.root)
  await assert.rejects(runPreparedSurvey(prepared.request_file, "0".repeat(64)))
  assert.ok(!(await readdir(join(prepared.request_file, ".."))).includes("run.started"))
  await chmod(prepared.request_file, 0o644)
  await assert.rejects(runPreparedSurvey(prepared.request_file, prepared.local_preview_digest))
  await chmod(prepared.request_file, 0o600)
  const request = JSON.parse(await readFile(prepared.request_file, "utf8"))
  request.selection.privacy.screenshot = true
  await writeFile(prepared.request_file, JSON.stringify(request))
  await assert.rejects(runPreparedSurvey(prepared.request_file, prepared.local_preview_digest))
})

browserTest("independent survey CLI prepares, captures once and assembles a real runnable read-only definition", async () => {
  const target = await fixture()
  const chosen = selection(target.definition)
  const selectionFile = join(target.root, "selection.json")
  await writeFile(selectionFile, JSON.stringify(chosen), { mode: 0o600 })
  const call = async (...args) => JSON.parse((await exec(process.execPath, [cli, ...args])).stdout)
  const prepared = await call("prepare", "--selection", selectionFile, "--workspace", target.root)
  assert.equal(prepared.browser_opened, false)
  const captured = await call("run", prepared.request_file, "--confirm", prepared.local_preview_digest)
  await assert.rejects(call("run", prepared.request_file, "--confirm", prepared.local_preview_digest))
  const report = JSON.parse(await readFile(captured.report_file, "utf8"))
  const manual = JSON.parse(await readFile(captured.manual_analysis_file, "utf8"))
  manual.analysis.identity_control = report.controls.find(item => item.role === "heading").id
  manual.analysis.read_controls = [report.controls.find(item => item.locator?.name === "status").id]
  await writeFile(captured.manual_analysis_file, JSON.stringify(manual))
  const assembled = await call("assemble", prepared.request_file, "--analysis", captured.manual_analysis_file, "--workspace", target.root)
  assert.equal(assembled.browser_opened, false)
  assert.equal(assembled.actions_approved, false)
  const definition = JSON.parse(await readFile(assembled.definition_file, "utf8"))
  const plan = JSON.parse(await readFile(assembled.plan_file, "utf8"))
  const preview = await previewInterface(definition, plan)
  const session = await BrowserInterfaceSession.open({ definition, plan, confirmation: preview.sha256, evidenceRoot: target.root })
  try {
    assert.equal(session.lastObservation.state, "observed")
  }
  finally { await session.close() }
  manual.capture_digest = "0".repeat(64)
  await writeFile(captured.manual_analysis_file, JSON.stringify(manual))
  await assert.rejects(call("assemble", prepared.request_file, "--analysis", captured.manual_analysis_file, "--workspace", target.root))
})
browserTest("survey discovers browser-verified controls without a handwritten control/state map or any click", async () => {
  const target = await fixture()
  const chosen = selection(target.definition)
  const preview = await previewSurvey(chosen)
  const outcome = await runSurvey(chosen, { confirmation: preview.sha256, evidenceRoot: target.root })
  const report = JSON.parse(await readFile(outcome.report_file, "utf8"))
  assert.equal(outcome.actions_executed, 0)
  assert.equal(outcome.hardware_qualified, false)
  assert.equal(report.controls.find(item => item.locator?.name === "status").value, "Ready")
  const count = report.controls.find(item => item.locator?.name === "count")
  assert.equal(count.label, "Sample count")
  assert.equal(count.read, null)
  assert.equal(count.value, null)
  assert.deepEqual(report.controls.find(item => item.label === "Run simulation").locator, { kind: "role", role: "button", name: "Run simulation" })
  assert.ok(!JSON.stringify(report).includes("PRIVATE-SYNTHETIC"))
  assert.ok(!JSON.stringify(report).includes(target.definition.target.source.path))
  assert.equal((await readdir(outcome.evidence)).filter(name => name.endsWith(".png")).length, 0)
})

browserTest("value capture is explicit; duplicate names remain advisory instead of generating fragile locators", async () => {
  const target = await fixture(html.replace("</main>", "<button>Run simulation</button></main>"))
  const chosen = selection(target.definition, true)
  const preview = await previewSurvey(chosen)
  const outcome = await runSurvey(chosen, { confirmation: preview.sha256, evidenceRoot: target.root })
  const report = JSON.parse(await readFile(outcome.report_file, "utf8"))
  assert.equal(report.controls.find(item => item.locator?.name === "count").value, "1")
  const buttons = report.controls.filter(item => item.label === "Run simulation")
  assert.equal(buttons.length, 2)
  assert.ok(buttons.every(item => item.locator === null))
})

browserTest("private masks cover shadow descendants and indirect labels; disguised/contenteditable inputs do not leak values", async () => {
  const content = html.replace("</main>", `<div data-testid="masked-host"></div>
    <p data-testid="secret-label" id="secret-label">MASKED-LABEL</p>
    <input aria-labelledby="secret-label" data-testid="safe-input" value="UNAPPROVED-VALUE">
    <input role="button" data-testid="disguised" value="DISGUISED-VALUE">
    <div role="textbox" contenteditable data-testid="editable">EDITABLE-VALUE</div>
    <div data-testid="field-wrapper"><textarea aria-label="Notes">NESTED-VALUE</textarea></div>
    <input type="password" value="PASSWORD-VALUE">
    <script>document.querySelector('[data-testid=masked-host]').attachShadow({mode:'open'}).innerHTML='<button data-testid="shadow-secret">SHADOW-SECRET</button>'</script></main>`)
  const target = await fixture(content)
  const chosen = selection(target.definition)
  chosen.privacy.redact.push({ kind: "test_id", name: "masked-host" }, { kind: "test_id", name: "secret-label" })
  const preview = await previewSurvey(chosen)
  const outcome = await runSurvey(chosen, { confirmation: preview.sha256, evidenceRoot: target.root })
  const report = await readFile(outcome.report_file, "utf8")
  for (const secret of ["MASKED-LABEL", "UNAPPROVED-VALUE", "DISGUISED-VALUE", "EDITABLE-VALUE", "NESTED-VALUE", "PASSWORD-VALUE", "SHADOW-SECRET"])
    assert.ok(!report.includes(secret), secret)
  const definition = structuredClone(target.definition)
  definition.privacy.redact.push({ kind: "test_id", name: "masked-host" })
  definition.controls.push({ id: "private.shadow", locator: { kind: "test_id", name: "shadow-secret" }, read: "text", operations: ["read"] })
  const fixedPreview = await previewInterface(definition, emptyPlan)
  await assert.rejects(BrowserInterfaceSession.open({ definition, plan: emptyPlan, confirmation: fixedPreview.sha256, evidenceRoot: target.root }))
})

browserTest("survey uses the same network and target-change stopping boundary", async () => {
  const target = await fixture(html.replace("</main>", "<script>fetch(\"https://example.invalid/unapproved\")</script></main>"))
  const chosen = selection(target.definition)
  const preview = await previewSurvey(chosen)
  await assert.rejects(runSurvey(chosen, { confirmation: preview.sha256, evidenceRoot: target.root }), /Survey refused/)
  const directories = (await readdir(target.root)).filter(name => name.startsWith("interface-"))
  const events = await Promise.all((await readdir(join(target.root, directories[0]))).filter(name => /^\d+\.json$/.test(name)).map(name => readFile(join(target.root, directories[0], name), "utf8")))
  assert.ok(events.join("\n").includes("\"physical_stop_confirmed\":false"))
})
