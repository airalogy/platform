/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { readdir, readFile } from "node:fs/promises"
import { dirname } from "node:path"
import test from "node:test"
import { BrowserInterfaceSession } from "../src/browser-session.mjs"
import { digest } from "../src/contract.mjs"
import { prepareExploration, runExploration, syncExploration } from "../src/exploration.mjs"
import { fingerprint, validateProposal, validateRequest } from "../src/exploration-contract.mjs"
import { previewSelectedInterface } from "../src/interface-backend.mjs"
import { fixture, plan } from "./fixture.mjs"

const policy = { goal: "Read two synthetic samples", actions: plan.steps, success: [{ control_id: "result", equals: "0.84" }] }
async function prepared() {
  const selected = await fixture()
  const files = await prepareExploration({ definition: selected.definition, policy, workspace: selected.root, platformUrl: "http://127.0.0.1/", gatewayId: "11111111-1111-1111-1111-111111111111", resourceId: "22222222-2222-2222-2222-222222222222" })
  const content = JSON.parse(await readFile(files.request_file))
  return { ...files, content }
}

class SyntheticProvider {
  constructor(request) {
    this.request = request
    this.turns = []
    this.reports = new Map()
    this.canProceed = true
    this.proposals = 0
    this.rejectFirstReport = false
  }

  async call(operation, payload = {}, turnId = null) {
    if (operation === "status")
      return { can_proceed: this.canProceed, effective_state: this.canProceed ? "open" : "cancelled", request: this.request, turns: this.turns, expires_at: new Date(Date.now() + 600000).toISOString() }
    if (operation === "turns") {
      const observation = payload.observation
      const proposal = observation.state === "complete"
        ? { kind: "finish", action_index: null, summary: "The selected synthetic result is present", missing_information: [] }
        : { kind: "act", action_index: observation.values.count === "2" ? 1 : 0, summary: "Use an approved synthetic step", missing_information: [] }
      const selected = this.override ? await this.override(proposal) : proposal
      this.proposals += 1
      const turn = { id: payload.id, previous_id: payload.previous_id, input: { observation, evidence_digest: payload.evidence_digest }, state: "generated", proposal: selected, candidate_digest: digest(selected) }
      this.turns.push(turn)
      return turn
    }
    if (operation === "report") {
      const old = this.reports.get(turnId)
      if (old)
        assert.deepEqual(old, payload.report)
      this.reports.set(turnId, payload.report)
      if (this.rejectFirstReport) {
        this.rejectFirstReport = false
        throw new Error("Synthetic lost receipt after saved report")
      }
      return { turn: this.turns.find(item => item.id === turnId) }
    }
    if (operation === "end") {
      this.canProceed = false
      return {}
    }
    throw new Error("Unexpected synthetic API operation")
  }
}

test("public exploration request excludes local paths, source bytes and bearer credentials", async () => {
  const value = await prepared()
  const exported = await readFile(value.authorization_file, "utf8")
  const request = validateRequest(JSON.parse(exported))
  assert.equal(request.spec.actions.length, 3)
  assert.ok(!exported.includes(value.content.token))
  assert.ok(!exported.includes(value.content.definition.target.source.path))
  assert.ok(!exported.includes("<!doctype"))
  assert.throws(() => validateRequest({ ...request, max_iterations: 6 }))
  assert.throws(() => validateRequest({ ...request, fingerprint: "0".repeat(64) }))
  const observed = { session_id: request.id, sequence: 0, local_preview_digest: request.spec.local_preview_digest, state: "ready", values: { count: "1", run: "Run simulation", result: "0", status: "Ready" }, enabled: { count: true, run: true, result: true, status: true } }
  assert.throws(() => validateProposal({ kind: "finish", action_index: null, summary: "Pretend done", missing_information: [] }, request.spec, observed))
  assert.throws(() => validateProposal({ kind: "act", action_index: 63, summary: "Unapproved action", missing_information: [] }, request.spec, observed))
})

test("shared API/Node golden request has identical canonical validation", async () => {
  const request = JSON.parse(await readFile(new URL("./exploration-fixture.json", import.meta.url)))
  assert.deepEqual(validateRequest(request), request)
})

test("native development grants are distinct from general native control and read-only surveys", async () => {
  const request = JSON.parse(await readFile(new URL("./exploration-fixture.json", import.meta.url)))
  request.spec.target.kind = "native_macos_simulation"
  request.fingerprint = fingerprint(request)
  validateRequest(request)
  for (const kind of ["native_macos", "native_windows", "visual"]) {
    const invalid = structuredClone(request)
    invalid.spec.target.kind = kind
    invalid.fingerprint = fingerprint(invalid)
    assert.throws(() => validateRequest(invalid))
  }
  request.spec.controls[0].read = "checked"
  request.fingerprint = fingerprint(request)
  assert.throws(() => validateRequest(request))
  assert.throws(() => previewSelectedInterface({ schema: "airalogy.native-read-definition.v1" }, { schema: "airalogy.interface-plan.v1", steps: [] }, policy), /read-only/)
})

test("API base rejects query-bearing endpoints before creating credentials", async () => {
  const selected = await fixture()
  await assert.rejects(prepareExploration({ definition: selected.definition, policy, workspace: selected.root, platformUrl: "https://example.invalid/?secret=value", gatewayId: "11111111-1111-1111-1111-111111111111", resourceId: "22222222-2222-2222-2222-222222222222" }), /query/)
})

const browserTest = (name, fn) => test(name, { skip: process.env.RUN_INTERFACE_BROWSER_TESTS !== "1" }, fn)
browserTest("adaptive model choices execute actual browser steps and stop on independently checked success", async () => {
  const files = await prepared()
  const client = new SyntheticProvider(files.content.request)
  const outcome = await runExploration(files.request_file, { confirmation: files.local_preview_digest, client })
  assert.equal(outcome.state, "client_reported_success")
  assert.equal(client.proposals, 3)
  assert.equal(client.reports.size, 2)
  const after = [...client.reports.values()].at(-1).after
  assert.equal(after.values.result, "0.84")
  assert.equal(after.sequence, 2)
  assert.equal(outcome.hardware_qualified, false)
  await assert.rejects(runExploration(files.request_file, { confirmation: files.local_preview_digest, client }))
})

browserTest("out-of-policy model output and cancellation do not cause local actions", async () => {
  for (const cancel of [false, true]) {
    const files = await prepared()
    const client = new SyntheticProvider(files.content.request)
    client.override = async (proposal) => {
      if (cancel)
        client.canProceed = false
      return cancel ? proposal : { ...proposal, action_index: 63 }
    }
    await assert.rejects(runExploration(files.request_file, { confirmation: files.local_preview_digest, client }))
    assert.equal(client.reports.size, 0)
  }
})

browserTest("lost action receipt syncs immutable evidence without reopening a browser or asking a model", async () => {
  const files = await prepared()
  const client = new SyntheticProvider(files.content.request)
  client.rejectFirstReport = true
  await assert.rejects(runExploration(files.request_file, { confirmation: files.local_preview_digest, client }), /lost receipt/)
  assert.equal(client.proposals, 1)
  const before = await readdir(dirname(files.request_file))
  client.canProceed = false // Saved reports remain recoverable after cancellation.
  const synced = await syncExploration(files.request_file, { client })
  assert.equal(synced.synced_reports, 1)
  assert.equal(synced.browser_opened, false)
  assert.equal(client.proposals, 1)
  assert.deepEqual(await readdir(dirname(files.request_file)), before)
  assert.equal([...client.reports.values()][0].after.values.count, "2")
  await assert.rejects(runExploration(files.request_file, { confirmation: files.local_preview_digest, client }))
})

browserTest("AI-disabled authorization never launches and a used grant cannot start from a copied request", async () => {
  const files = await prepared()
  const client = new SyntheticProvider(files.content.request)
  client.canProceed = false
  await assert.rejects(runExploration(files.request_file, { confirmation: files.local_preview_digest, client }))
  assert.ok(!(await readdir(dirname(files.request_file))).includes("run.started"))
  client.canProceed = true
  client.turns.push({ id: "existing" })
  await assert.rejects(runExploration(files.request_file, { confirmation: files.local_preview_digest, client }), /saved turns/)
  assert.ok(!(await readdir(dirname(files.request_file))).includes("run.started"))
})

browserTest("page changes during model consideration stop even a proposed finish", async (t) => {
  const original = BrowserInterfaceSession.open
  let session
  t.mock.method(BrowserInterfaceSession, "open", async (...args) => {
    session = await original(...args)
    return session
  })
  const files = await prepared()
  const client = new SyntheticProvider(files.content.request)
  client.override = async (proposal) => {
    if (proposal.kind === "finish")
      await session.page.getByTestId("result").evaluate((element) => { element.textContent = "99" })
    return proposal
  }
  await assert.rejects(runExploration(files.request_file, { confirmation: files.local_preview_digest, client }), /changed while/)
  assert.equal(client.proposals, 3)
  assert.equal(client.reports.size, 2)
  assert.equal(client.canProceed, true) // No successful end was reported.
})
