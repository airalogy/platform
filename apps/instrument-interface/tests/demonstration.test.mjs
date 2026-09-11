/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { execFile } from "node:child_process"
import { readdir, readFile, writeFile } from "node:fs/promises"
import { join } from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"
import { promisify } from "node:util"
import { canonical, digest } from "../src/contract.mjs"
import { BrowserDemonstrationSession, previewDemonstration } from "../src/demonstration.mjs"
import { exportWorkflow, previewWorkflow, previewWorkflowExport, runWorkflow, workflowFromEvidence } from "../src/workflow.mjs"
import { fixture, html, plan } from "./fixture.mjs"

const real = process.env.RUN_INTERFACE_BROWSER_TESTS === "1"
const policy = { goal: "Demonstrate two synthetic samples", actions: plan.steps.slice(0, 2), success: [{ control_id: "result", equals: "0.84" }] }

async function open(content = html) {
  const selected = await fixture(content)
  const preview = await previewDemonstration(selected.definition, policy, { visible: false })
  const session = await BrowserDemonstrationSession.open({ definition: selected.definition, policy, visible: false, confirmation: preview.sha256, evidenceRoot: selected.root, acknowledgeOwnedSimulation: true })
  return { ...selected, preview, session }
}

async function acknowledged(session, steps) {
  await session.page.waitForFunction(key => !window[key].busy && !window[key].pending, session.statusKey)
  assert.equal(session.cursor, steps, session.fault ?? "Missing demonstration receipt")
}

async function fill(session, text = "2") {
  const field = session.page.getByRole("spinbutton", { name: "Sample count" })
  await field.click()
  await field.press("ControlOrMeta+A")
  await field.pressSequentially(text)
  await field.press("Tab")
}

test("manual capture preview pins visibility and refuses live URL/native/unconfirmed selection before launch", async () => {
  const selected = await fixture()
  const visible = await previewDemonstration(selected.definition, policy)
  const hidden = await previewDemonstration(selected.definition, policy, { visible: false })
  assert.notEqual(visible.sha256, hidden.sha256)
  assert.deepEqual(visible.capture, { kind: "human_browser_events", visible: true })
  const files = await readdir(selected.root)
  await assert.rejects(BrowserDemonstrationSession.open({ definition: selected.definition, policy, confirmation: hidden.sha256, evidenceRoot: selected.root, acknowledgeOwnedSimulation: true }))
  await assert.rejects(BrowserDemonstrationSession.open({ definition: selected.definition, policy, confirmation: visible.sha256, evidenceRoot: selected.root }))
  assert.deepEqual(await readdir(selected.root), files)
  await assert.rejects(previewDemonstration({ ...selected.definition, target: { ...selected.definition.target, source: { kind: "url", url: "http://127.0.0.1/" } } }, policy))
  await assert.rejects(previewDemonstration(selected.definition, policy, { visible: "yes" }))
  for (const incomplete of [null, undefined, { ...policy, actions: [plan.steps[2]] }])
    await assert.rejects(previewDemonstration(selected.definition, incomplete), /explicit demonstration/)
})

test("actual browser input events export demonstration lineage and replay without a model or recorder", { skip: !real, timeout: 30000 }, async () => {
  const selected = await open()
  const { session } = selected
  try {
    await assert.rejects(session.step(), /manual events/)
    await fill(session)
    await acknowledged(session, 1)
    await session.page.getByRole("button", { name: "Run simulation" }).click()
    await acknowledged(session, 2)
    const result = await session.finish()
    assert.equal(result.model_calls, 0)
    assert.equal(result.hardware_qualified, false)
    const preview = await previewWorkflowExport(result.evidence)
    assert.equal(preview.workflow.source.kind, "human_browser_events")
    assert.deepEqual(preview.workflow.plan.steps, policy.actions)
    assert.ok(!canonical(preview).includes("PRIVATE-SYNTHETIC-CONTENT"))
    assert.equal(preview.workflow.initial.values.count, "1")
    const saved = await exportWorkflow(result.evidence, { confirmation: preview.sha256, workspace: selected.root })
    const workflow = JSON.parse(await readFile(saved.workflow_file))
    const replay = await previewWorkflow(workflow)
    const repeated = await runWorkflow(workflow, { confirmation: replay.sha256, evidenceRoot: selected.root, acknowledgeNewRun: true })
    assert.equal(repeated.hardware_qualified, false)
    const names = (await readdir(result.evidence)).filter(name => /^\d{4}\.json$/.test(name)).sort()
    const events = await Promise.all(names.map(name => readFile(join(result.evidence, name), "utf8").then(JSON.parse)))
    assert.ok(events.some(event => event.kind === "demonstration_action"))
    assert.ok(!events.some(event => event.kind === "step_intent" || event.kind === "exploration_result"))
    const mixed = structuredClone(events)
    mixed.find(event => event.kind === "demonstration_action").kind = "step_intent"
    let previous = null
    for (const [index, event] of mixed.entries()) {
      const { sha256: _, ...value } = { ...event, previous }
      previous = digest(value)
      await writeFile(join(result.evidence, names[index]), canonical({ ...value, sha256: previous }))
    }
    await assert.rejects(workflowFromEvidence(result.evidence), /Step was not approved/)
    // A post-observation record must never be relabelled as a prior agent intent.
    const headerPath = join(result.evidence, "preview.json")
    const { capture: _, sha256: __, ...header } = JSON.parse(await readFile(headerPath))
    await writeFile(headerPath, canonical({ ...header, sha256: digest(header) }))
    await assert.rejects(workflowFromEvidence(result.evidence))
  }
  finally { await session.close() }
})

test("CLI preview is passive and piped recording cannot open a visible application", async () => {
  const selected = await fixture()
  const definitionFile = join(selected.root, "definition.json")
  const policyFile = join(selected.root, "policy.json")
  await writeFile(definitionFile, canonical(selected.definition), { mode: 0o600 })
  await writeFile(policyFile, canonical(policy), { mode: 0o600 })
  const cli = fileURLToPath(new URL("../src/demonstration-cli.mjs", import.meta.url))
  const args = ["--definition", definitionFile, "--policy", policyFile]
  const { stdout } = await promisify(execFile)(process.execPath, [cli, "preview", ...args], { timeout: 10000 })
  const preview = JSON.parse(stdout)
  assert.equal(preview.capture.visible, true)
  const before = await readdir(selected.root)
  await assert.rejects(promisify(execFile)(process.execPath, [cli, "record", ...args, "--confirm", preview.sha256, "--evidence", selected.root, "--ack-visible-owned-simulation"], { timeout: 10000 }))
  assert.deepEqual(await readdir(selected.root), before)
})

test("input during a pending receipt is not queued and later explicit keyboard activation is recorded", { skip: !real, timeout: 30000 }, async () => {
  const { session } = await open()
  const append = session.evidence.append.bind(session.evidence)
  let release
  const gate = new Promise((resolve) => {
    release = resolve
  })
  session.evidence.append = async (kind, data) => {
    if (kind === "demonstration_action" && data.index === 0)
      await gate
    return append(kind, data)
  }
  try {
    await fill(session)
    await session.page.waitForFunction(key => window[key].busy, session.statusKey)
    await session.page.getByRole("button").click()
    assert.equal(await session.page.getByTestId("result").textContent(), "0")
    assert.ok(await session.page.evaluate(key => window[key].ignored > 0, session.statusKey))
    release()
    await acknowledged(session, 1)
    assert.equal(await session.page.getByTestId("result").textContent(), "0")
    await session.page.getByRole("button").press("Enter")
    await acknowledged(session, 2)
    assert.equal((await session.finish()).completed_steps, 2)
  }
  finally {
    release()
    await session.close()
  }
})

test("finishing freezes new browser actions before the final readback and completion receipt", { skip: !real, timeout: 30000 }, async () => {
  const source = html.replace("document.querySelector('#run').onclick = () => {", "window.starts = 0; document.querySelector('#run').onclick = () => { window.starts += 1;")
  const { session } = await open(source)
  let release
  try {
    await fill(session)
    await acknowledged(session, 1)
    await session.page.getByRole("button").click()
    await acknowledged(session, 2)
    const gate = new Promise((resolve) => {
      release = resolve
    })
    const snapshot = session.snapshot.bind(session)
    session.snapshot = async () => {
      await gate
      return snapshot()
    }
    const completion = session.finish()
    await session.page.waitForFunction(key => window[key].active === false, session.statusKey)
    await session.page.getByRole("button").click()
    assert.equal(await session.page.evaluate(() => window.starts), 1)
    release()
    assert.equal((await completion).completed_steps, 2)
  }
  finally {
    release?.()
    await session.close()
  }
})

test("unfinished, unapproved, programmatic, drifted and falsely completed demonstrations cannot be promoted", { skip: !real, timeout: 60000 }, async () => {
  for (const mode of ["pending", "out_of_policy", "script_click", "early_finish", "late_change", "bad_result"]) {
    const selected = await open(mode === "bad_result" ? html.replace("* 0.42", "* 0.43") : html)
    const { session } = selected
    try {
      if (mode === "pending") {
        await session.page.getByRole("spinbutton").press("2")
        await assert.rejects(session.finish())
      }
      else if (mode === "script_click") {
        await session.page.getByRole("button").evaluate(element => element.click()).catch(() => {})
        await assert.rejects(session.finish())
      }
      else {
        await fill(session, mode === "out_of_policy" ? "3" : "2").catch(() => {})
        if (mode === "out_of_policy") {
          await assert.rejects(acknowledged(session, 1))
        }
        else {
          await acknowledged(session, 1)
          if (mode !== "early_finish") {
            await session.page.getByRole("button").click()
            await acknowledged(session, 2)
          }
          if (mode === "late_change")
            await session.page.getByTestId("result").evaluate((element) => { element.textContent = "9.99" })
          await assert.rejects(session.finish())
        }
      }
      await session.close()
      await assert.rejects(workflowFromEvidence(session.evidence.directory), mode)
    }
    finally { await session.close() }
  }
})
