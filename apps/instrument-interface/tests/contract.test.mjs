/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { chmod, mkdtemp, readFile, symlink, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import test from "node:test"
import { previewInterface } from "../src/browser-session.mjs"
import { canonical, digest, exactUrl, validateDefinition, validatePlan } from "../src/contract.mjs"
import { Evidence, readPrivateSelection } from "../src/evidence.mjs"
import { definition, fixture, plan } from "./fixture.mjs"

test("canonical hashing is stable, bounded, and rejects non-JSON", () => {
  assert.equal(digest({ b: 2, a: 1 }), digest({ a: 1, b: 2 }))
  assert.throws(() => canonical(Number.NaN))
  assert.throws(() => canonical({ value: undefined }))
  const cycle = {}
  cycle.cycle = cycle
  assert.throws(() => canonical(cycle), /deeply/)
})

test("strict definitions and plans reject broader authority", () => {
  const valid = definition({ kind: "url", url: "http://127.0.0.1:8080/" })
  validateDefinition(valid)
  const local = { ...valid, target: { ...valid.target, source: { kind: "file", path: "/selected.html", sha256: "0".repeat(64) } }, network: [] }
  validatePlan(plan, local)
  assert.throws(() => validatePlan(plan, valid), /observation-only/)
  const mutations = [
    value => value.target.scope = { kind: "css", name: "*" },
    value => value.network[0].method = "POST",
    value => value.network.push({ ...value.network[0], url: "https://example.com/" }),
    value => value.network[0].max_requests = 101,
    value => value.controls.push(value.controls[0]),
    value => value.controls[0].operations.push("evaluate"),
    value => value.limits.duration_seconds = 901,
    value => value.limits.max_steps = 41,
    value => value.states[0].checks[0].control_id = "undeclared",
    value => value.script = "arbitrary code",
    value => value.privacy.screenshot = "true",
  ]
  for (const mutate of mutations) {
    const changed = structuredClone(valid)
    mutate(changed)
    assert.throws(() => validateDefinition(changed))
  }
  for (const url of ["http://lab.example/", "https://user:secret@example.com/", "https://example.com/#key", "file:///tmp/index.html", "https://example.com"])
    assert.throws(() => exactUrl(url))
  assert.throws(() => validatePlan({ ...plan, steps: [...plan.steps].reverse() }, local))
  assert.throws(() => validatePlan({ ...plan, steps: [{ ...plan.steps[0], value: { javascript: true } }] }, local))
})

test("preview binds selected bytes, engine, target and exact plan", async () => {
  const selected = await fixture()
  const preview = await previewInterface(selected.definition, plan)
  assert.equal(preview.plan.steps.length, 3)
  assert.throws(() => preview.plan.steps.push(plan.steps[0]))
  assert.notEqual(preview.sha256, (await previewInterface(selected.definition, { ...plan, steps: [] })).sha256)
  selected.definition.target.version = "other"
  assert.equal(preview.definition.target.version, "1.0")
  await writeFile(selected.definition.target.source.path, "changed")
  await assert.rejects(previewInterface(selected.definition, plan), /bytes changed/)
})

test("selected files reject symlinks, excess bytes, directories and relative paths", async () => {
  const selected = await fixture()
  const link = join(selected.root, "link.html")
  await symlink(selected.definition.target.source.path, link)
  await assert.rejects(readPrivateSelection(link))
  await assert.rejects(readPrivateSelection(selected.root))
  await assert.rejects(readPrivateSelection(selected.definition.target.source.path, 1))
  await assert.rejects(readPrivateSelection("relative.json"))
})

test("private evidence is exclusive, bounded by sequence and hash-chained", async () => {
  const root = await mkdtemp(join(tmpdir(), "airalogy-evidence-test-"))
  const evidence = await Evidence.create(root, { consent: "synthetic" })
  const first = await evidence.append("test", { value: 1 })
  await evidence.append("test", { value: 2 })
  const next = JSON.parse(await readFile(join(evidence.directory, "0001.json")))
  assert.equal(next.previous, first)
  const { sha256, ...event } = next
  assert.equal(digest(event), sha256)
  await assert.rejects(evidence.write("0001.json", Buffer.from("overwrite")))
  await assert.rejects(evidence.write("../escape", Buffer.alloc(0)))
  await chmod(root, 0o755)
  await assert.rejects(Evidence.create(root, {}), /owner-only/)
})

test("runtime and repository browser-test engines resolve to the same pinned release", async () => {
  const { createRequire } = await import("node:module")
  const local = createRequire(import.meta.url)
  const repository = createRequire(new URL("../../../package.json", import.meta.url))
  assert.equal(local("playwright/package.json").version, repository("@playwright/test/package.json").version)
})
