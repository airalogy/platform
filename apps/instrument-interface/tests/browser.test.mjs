/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { execFile } from "node:child_process"
import { readdir, readFile, writeFile } from "node:fs/promises"
import { createServer } from "node:http"
import { join } from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"
import { promisify } from "node:util"
import { BrowserInterfaceSession, previewInterface } from "../src/browser-session.mjs"
import { digest } from "../src/contract.mjs"
import { definition, emptyPlan, fixture, html, plan } from "./fixture.mjs"

const browserTest = (name, fn) => test(name, { skip: process.env.RUN_INTERFACE_BROWSER_TESTS !== "1" }, fn)
async function open(selected, replay = plan) {
  const preview = await previewInterface(selected.definition, replay)
  return BrowserInterfaceSession.open({ definition: selected.definition, plan: replay, confirmation: preview.sha256, evidenceRoot: selected.root })
}
async function events(session) {
  const names = (await readdir(session.evidence.directory)).filter(name => /^\d+\.json$/.test(name)).sort()
  return Promise.all(names.map(async name => JSON.parse(await readFile(join(session.evidence.directory, name)))))
}

browserTest("actual browser fills, invokes, reads back and saves private evidence", async (t) => {
  const selected = await fixture()
  selected.definition.privacy.screenshot = true
  const session = await open(selected)
  t.after(() => session.close())
  for (let i = 0; i < plan.steps.length; i++)
    await session.step(digest(session.lastObservation))
  assert.equal(session.lastObservation.values.result, "0.84")
  assert.equal(session.lastObservation.state, "complete")
  const history = await events(session)
  assert.equal(history.filter(event => event.kind === "step_intent").length, 3)
  assert.equal(history.filter(event => event.kind === "step_result").length, 3)
  assert.ok(!JSON.stringify(history).includes("PRIVATE-SYNTHETIC-CONTENT"))
  const observation = history.find(event => event.kind === "observation").data
  assert.equal(observation.accessibility, null)
  const png = await readFile(join(session.evidence.directory, observation.screenshot.file))
  assert.equal(png.subarray(1, 4).toString(), "PNG")
  await assert.rejects(session.step(digest(session.lastObservation)), /stopped/)
})

browserTest("read-only opening can capture scoped accessibility without masks", async (t) => {
  const selected = await fixture(html.replace("<div data-testid=\"private\">PRIVATE-SYNTHETIC-CONTENT</div>", ""))
  selected.definition.privacy.redact = []
  const session = await open(selected, emptyPlan)
  t.after(() => session.close())
  const history = await events(session)
  assert.match(history.find(event => event.kind === "observation").data.accessibility, /Run simulation/)
  assert.equal(session.cursor, 0)
})

browserTest("incorrect consent never launches; duplicate identity and dialogs refuse initial observation", async () => {
  const selected = await fixture()
  await assert.rejects(BrowserInterfaceSession.open({ definition: selected.definition, plan, confirmation: "not-approved", evidenceRoot: selected.root }), /Confirm/)
  for (const body of [
    html.replace("</main>", "<button>Run simulation</button></main>"),
    html.replace("</main>", "<div role=\"alertdialog\">Review required</div></main>"),
    html.replace("Simulated Reader 1.0 — no hardware</h1>", "Simulated Reader 2.0 — no hardware</h1>"),
    html.replace("</main>", "<iframe srcdoc=\"synthetic\"></iframe></main>"),
  ]) {
    await assert.rejects(open(await fixture(body)), /opening refused/)
  }
})

browserTest("stale observations and mismatched postconditions stop without replay", async (t) => {
  const session = await open(await fixture())
  t.after(() => session.close())
  const prior = digest(session.lastObservation)
  await session.page.getByRole("spinbutton").fill("3") // Simulate an independent change, not a supported backend operation.
  await assert.rejects(session.step(prior), /stopped/)
  assert.equal(session.cursor, 0)
  assert.ok(!(await events(session)).some(event => event.kind === "step_intent"))
  const selected = await fixture(html.replace("String(Number(document.querySelector('#count').value) * 0.42)", "'unexpected'"))
  const badPlan = { ...plan, steps: [{ ...plan.steps[1], after: "ready" }] }
  const failing = await open(selected, badPlan)
  t.after(() => failing.close())
  await assert.rejects(failing.step(digest(failing.lastObservation)), /stopped/)
  const history = await events(failing)
  assert.equal(history.filter(event => event.kind === "step_intent").length, 1)
  assert.ok(history.some(event => event.kind === "stopped" && event.data.reason.includes("uncertain")))
  await assert.rejects(failing.step(digest(failing.lastObservation)))
})

browserTest("passwords and explicitly redacted controls cannot be read or filled", async () => {
  const selected = await fixture(html.replace("type=\"number\"", "type=\"password\""))
  selected.definition.controls[0].locator = { kind: "test_id", name: "count" }
  await assert.rejects(open(selected), /opening refused/)
  const masked = await fixture()
  masked.definition.privacy.redact.push(masked.definition.controls[0].locator)
  await assert.rejects(open(masked), /opening refused/)
})

browserTest("selected loopback app is allowed, unexpected fetch is blocked before reaching server", async (t) => {
  const received = []
  const server = createServer((request, response) => {
    received.push(request.url)
    response.setHeader("Content-Type", "text/html")
    response.end(html)
  })
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve))
  t.after(() => new Promise(resolve => server.close(resolve)))
  const selected = await fixture()
  selected.definition = definition({ kind: "url", url: `http://127.0.0.1:${server.address().port}/` })
  const session = await open(selected, emptyPlan)
  t.after(() => session.close())
  await session.page.evaluate(() => fetch("/unauthorized").catch(() => null))
  await assert.rejects(session.observe(), /stopped/)
  assert.deepEqual(received, ["/"])
})

browserTest("unexpected socket, popup, script dialog and deadline stop sessions", async (t) => {
  for (const expression of ["new WebSocket('ws://127.0.0.1:9/blocked')", "window.open('about:blank')", "alert('synthetic')"]) {
    const session = await open(await fixture(), emptyPlan)
    t.after(() => session.close())
    await session.page.evaluate(expression)
    // Wait for the injected event, never retry a command or alter application state.
    for (let i = 0; i < 50 && !session.fault; i++)
      await new Promise(resolve => setTimeout(resolve, 10))
    assert.ok(session.fault)
    await assert.rejects(session.observe(), /stopped/)
  }
  const expired = await open(await fixture())
  t.after(() => expired.close())
  expired.deadline = 0
  await assert.rejects(expired.step(digest(expired.lastObservation)), /stopped/)
  assert.equal(expired.cursor, 0)
})

browserTest("CLI preview does not open software; confirmed independent process saves a completed run", async () => {
  const selected = await fixture()
  const definitionPath = join(selected.root, "definition.json")
  const planPath = join(selected.root, "plan.json")
  await writeFile(definitionPath, JSON.stringify(selected.definition), { mode: 0o600 })
  await writeFile(planPath, JSON.stringify(plan), { mode: 0o600 })
  const cli = fileURLToPath(new URL("../src/cli.mjs", import.meta.url))
  const execute = promisify(execFile)
  const options = ["--definition", definitionPath, "--plan", planPath]
  const preview = JSON.parse((await execute(process.execPath, [cli, "preview", ...options])).stdout)
  assert.ok(!(await readdir(selected.root)).some(name => name.startsWith("interface-")))
  await assert.rejects(execute(process.execPath, [cli, "run", ...options, "--confirm", preview.sha256, "--evidence", selected.root]))
  const result = await execute(process.execPath, [cli, "run", ...options, "--confirm", preview.sha256, "--evidence", selected.root, "--ack-new-run"])
  const report = JSON.parse(result.stdout)
  const history = await events({ evidence: { directory: report.evidence } })
  assert.equal(history.at(-1).kind, "closed")
  assert.equal(history.at(-1).data.completed_steps, 3)
  assert.equal(history.at(-1).data.physical_stop_confirmed, false)
})

browserTest("unapproved redirect and navigation are refused, even to the same origin", async (t) => {
  const received = []
  const server = createServer((request, response) => {
    received.push(request.url)
    response.writeHead(302, { Location: "/other" }).end()
  })
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve))
  t.after(() => new Promise(resolve => server.close(resolve)))
  const selected = await fixture()
  const origin = `http://127.0.0.1:${server.address().port}`
  selected.definition = definition({ kind: "url", url: `${origin}/` })
  selected.definition.network.push({ url: `${origin}/other`, method: "GET", max_requests: 1 })
  await assert.rejects(open(selected, emptyPlan), /opening refused/)
  assert.deepEqual(received, ["/"])
})

browserTest("observation budget and disabled controls stop before a click", async (t) => {
  const selected = await fixture()
  selected.definition.limits.max_steps = 1
  const session = await open(selected, emptyPlan)
  t.after(() => session.close())
  await session.observe()
  await session.observe()
  await assert.rejects(session.observe(), /stopped/)
  const disabled = await fixture(html.replace("<button id=\"run\">", "<button id=\"run\" disabled>"))
  const oneClick = { ...plan, steps: [plan.steps[1]] }
  const blocked = await open(disabled, oneClick)
  t.after(() => blocked.close())
  await assert.rejects(blocked.step(digest(blocked.lastObservation)), /stopped/)
  assert.ok(!(await events(blocked)).some(event => event.kind === "step_intent"))
})

browserTest("oversized network responses are refused without retaining response content", async (t) => {
  const server = createServer((_request, response) => {
    response.setHeader("Content-Type", "text/html; charset=utf-8")
    response.end(`OVERSIZED-SYNTHETIC-RESPONSE${"x".repeat(2097152)}`)
  })
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve))
  t.after(() => new Promise(resolve => server.close(resolve)))
  const selected = await fixture()
  selected.definition = definition({ kind: "url", url: `http://127.0.0.1:${server.address().port}/` })
  await assert.rejects(open(selected, emptyPlan), /opening refused/)
  const directory = (await readdir(selected.root)).find(name => name.startsWith("interface-"))
  const history = await events({ evidence: { directory: join(selected.root, directory) } })
  assert.ok(history.some(event => event.kind === "stopped" && event.data.fault.includes("budget")))
  assert.ok(!JSON.stringify(history).includes("OVERSIZED-SYNTHETIC-RESPONSE"))
})
