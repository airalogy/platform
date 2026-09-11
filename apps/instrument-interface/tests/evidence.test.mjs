/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { mkdtemp, readdir, readFile, rm } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import test from "node:test"
import { BrowserRuntime } from "../src/browser-runtime.mjs"
import { digest } from "../src/contract.mjs"
import { Evidence } from "../src/evidence.mjs"

async function evidenceFor(t) {
  const root = await mkdtemp(join(tmpdir(), "airalogy-evidence-test-"))
  t.after(() => rm(root, { recursive: true, force: true }))
  return Evidence.create(root, { owned_fixture: true })
}

test("concurrent evidence appends retain one ordered hash chain and selected data", async (t) => {
  const evidence = await evidenceFor(t)
  const data = { reason: "selected" }
  const pending = [evidence.append("stopped", data), evidence.append("closed", {}), evidence.append("reviewed", {})]
  data.reason = "changed after append"
  const results = await Promise.all(pending)
  let previous = null
  for (let sequence = 0; sequence < results.length; sequence++) {
    const { sha256, ...event } = JSON.parse(await readFile(join(evidence.directory, `${String(sequence).padStart(4, "0")}.json`), "utf8"))
    assert.equal(event.sequence, sequence)
    assert.equal(event.previous, previous)
    assert.equal(sha256, digest(event))
    assert.equal(sha256, results[sequence])
    if (!sequence)
      assert.equal(event.data.reason, "selected")
    previous = sha256
  }
  assert.equal(evidence.sequence, 3)
  assert.equal(evidence.previous, previous)
})

test("failed evidence persistence poisons queued and future appends without overwrite", async (t) => {
  const evidence = await evidenceFor(t)
  const write = evidence.write.bind(evidence)
  let calls = 0
  evidence.write = async (...args) => {
    calls++
    await write(...args)
    throw new Error("injected persistence failure")
  }
  const results = await Promise.allSettled([evidence.append("intent", {}), evidence.append("result", {})])
  for (const result of results) {
    assert.equal(result.status, "rejected")
    assert.match(result.reason.message, /injected persistence failure/)
  }
  await assert.rejects(evidence.append("closed", {}), /injected persistence failure/)
  assert.equal(calls, 1)
  assert.equal(evidence.sequence, 0)
  assert.equal(evidence.previous, null)
  assert.deepEqual((await readdir(evidence.directory)).sort(), ["0000.json", "preview.json"])
})

test("concurrent browser closes await the same durable receipt or failure", async (t) => {
  for (const fail of [false, true]) {
    const evidence = await evidenceFor(t)
    let release
    const gate = new Promise((resolve) => {
      release = resolve
    })
    const runtime = new BrowserRuntime({ definition: { limits: { duration_seconds: 30 } } }, evidence)
    let closed = 0
    runtime.context = {
      close: async () => {
        closed++
        await gate
      },
    }
    if (fail)
      evidence.write = async () => { throw new Error("injected close receipt failure") }
    const first = runtime.close()
    const second = runtime.close()
    const completion = Promise.allSettled([first, second])
    assert.equal(runtime.closed, true)
    release()
    const results = await completion
    assert.equal(first, second)
    assert.equal(closed, 1)
    assert.deepEqual(results.map(result => result.status), fail ? ["rejected", "rejected"] : ["fulfilled", "fulfilled"])
    if (!fail) {
      const event = JSON.parse(await readFile(join(evidence.directory, "0000.json"), "utf8"))
      assert.equal(event.kind, "closed")
      assert.equal(event.data.physical_stop_confirmed, false)
    }
  }
})
