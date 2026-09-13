/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { readFileSync } from "node:fs"
import test from "node:test"
import ts from "typescript"

// Exercise the exact browser helper with the already installed TypeScript
// compiler. The helper has no runtime imports, HTTP clients, or model calls.
const source = readFileSync(new URL("../src/utils/analysis-selection.ts", import.meta.url), "utf8")
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
  reportDiagnostics: true,
})
assert.deepEqual(compiled.diagnostics, [])
const { createAnalysisSelectionTransfer: create, consumeAnalysisSelectionTransfer: consume, discardAnalysisSelectionTransfer: discard } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString("base64")}`)

class MemoryStorage {
  values = new Map()

  get length() { return this.values.size }
  key(index) { return [...this.values.keys()][index] ?? null }
  getItem(key) { return this.values.get(key) ?? null }
  setItem(key, value) { this.values.set(key, String(value)) }
  removeItem(key) { this.values.delete(key) }
}

const id = index => `00000000-0000-4000-8000-${String(index).padStart(12, "0")}`
const scope = { userId: id(1), projectId: id(2), protocolId: id(3) }
const latest = { mode: "latest", filters: { q: "  control  ", version: 2 } }
const selected = { mode: "selected", filters: {}, records: [{ id: id(10), version: 1 }, { id: id(11), version: 7 }] }
const storageKey = token => `airalogy.analysis-selection.${token}`

test("latest selection preserves the applied supported filters without page limits", () => {
  const storage = new MemoryStorage()
  const filters = { ...latest.filters, user_id: id(4), protocol_version: "1.2.3", number: 18, page: 4, page_size: 10 }
  const token = create({ ...scope, selection: { mode: "latest", filters } }, storage, 1000)
  assert.deepEqual(consume(token, scope, storage, 1001), {
    mode: "latest",
    filters: { user_id: id(4), protocol_version: "1.2.3", q: "control", number: 18, version: 2 },
  })
})

test("navigation tokens contain neither filters nor Record references", () => {
  const storage = new MemoryStorage()
  const first = create({ ...scope, selection: latest }, storage, 1000)
  const second = create({ ...scope, selection: latest }, storage, 1000)
  assert.match(first, /^[0-9a-f]{32}$/)
  assert.notEqual(first, second)
})

test("handoff never stores Record contents or unknown properties", () => {
  const storage = new MemoryStorage()
  const token = create({ ...scope, data: "PRIVATE_CONTENT", selection: { ...selected, data: "PRIVATE_CONTENT", records: selected.records.map(record => ({ ...record, data: "PRIVATE_CONTENT" })) } }, storage, 1000)
  assert.ok(!storage.getItem(storageKey(token)).includes("PRIVATE_CONTENT"))
  assert.deepEqual(consume(token, scope, storage, 1001), selected)
})

test("cross-page selection pins every displayed revision and never intersects later filters", () => {
  const storage = new MemoryStorage()
  const token = create({ ...scope, selection: { ...selected, filters: { q: "later page" } } }, storage, 1000)
  assert.deepEqual(consume(token, scope, storage, 1001), selected)
})

test("handoff is consumed exactly once", () => {
  const storage = new MemoryStorage()
  const token = create({ ...scope, selection: selected }, storage, 1000)
  assert.deepEqual(consume(token, scope, storage, 1001), selected)
  assert.equal(consume(token, scope, storage, 1002), null)
  assert.equal(storage.getItem(storageKey(token)), null)
})

test("handoff rejects changed user, Project or Protocol scope", () => {
  for (const key of ["userId", "projectId", "protocolId"]) {
    const storage = new MemoryStorage()
    const token = create({ ...scope, selection: selected }, storage, 1000)
    assert.equal(consume(token, { ...scope, [key]: id(99) }, storage, 1001), null)
    assert.equal(consume(token, scope, storage, 1002), null)
  }
})

test("handoff expires after ten minutes and never falls back to all Records", () => {
  const storage = new MemoryStorage()
  const token = create({ ...scope, selection: latest }, storage, 1000)
  assert.equal(consume(token, scope, storage, 601000), null)
})

test("invalid token, missing token and corrupt JSON fail closed", () => {
  const storage = new MemoryStorage()
  assert.equal(consume("../unrelated", scope, storage, 1000), null)
  assert.equal(consume("a".repeat(32), scope, storage, 1000), null)
  const token = create({ ...scope, selection: selected }, storage, 1000)
  storage.setItem(storageKey(token), "{bad json")
  assert.equal(consume(token, scope, storage, 1001), null)
})

test("forged expiry or selection modes cannot broaden scope", () => {
  for (const mutation of [{ expiresAt: 10000000 }, { selection: { mode: "all", filters: {} } }]) {
    const storage = new MemoryStorage()
    const token = create({ ...scope, selection: selected }, storage, 1000)
    const saved = JSON.parse(storage.getItem(storageKey(token)))
    storage.setItem(storageKey(token), JSON.stringify({ ...saved, ...mutation }))
    assert.equal(consume(token, scope, storage, 1001), null)
  }
})

test("invalid scope IDs and filter scalar types are rejected before storage", () => {
  const storage = new MemoryStorage()
  assert.throws(() => create({ ...scope, userId: "wrong", selection: latest }, storage))
  for (const filters of [{ q: {} }, { version: 0 }, { number: true }, { number: 1.5 }])
    assert.throws(() => create({ ...scope, selection: { mode: "latest", filters } }, storage))
  assert.equal(storage.length, 0)
})

test("selected references require valid IDs and strict positive integer revisions", () => {
  const storage = new MemoryStorage()
  for (const record of [{ id: "bad", version: 1 }, { id: id(10), version: 0 }, { id: id(10), version: true }, { id: id(10), version: 1.5 }])
    assert.throws(() => create({ ...scope, selection: { ...selected, records: [record] } }, storage))
  assert.equal(storage.length, 0)
})

test("duplicate, empty and oversized selections cannot create a handoff", () => {
  const storage = new MemoryStorage()
  for (const records of [[], [{ id: id(10), version: 1 }, { id: id(10), version: 2 }], Array.from({ length: 5001 }, (_, index) => ({ id: id(index + 10), version: 1 }))])
    assert.throws(() => create({ ...scope, selection: { ...selected, records } }, storage))
  assert.equal(storage.length, 0)
})

test("creating a handoff removes only expired analysis keys", () => {
  const storage = new MemoryStorage()
  storage.setItem("unrelated", "preserve")
  const old = create({ ...scope, selection: latest }, storage, 1000)
  const live = create({ ...scope, selection: latest }, storage, 600000)
  create({ ...scope, selection: latest }, storage, 601001)
  assert.equal(storage.getItem(storageKey(old)), null)
  assert.notEqual(storage.getItem(storageKey(live)), null)
  assert.equal(storage.getItem("unrelated"), "preserve")
})

test("failed navigation discards only its own handoff", () => {
  const storage = new MemoryStorage()
  storage.setItem("unrelated", "preserve")
  const token = create({ ...scope, selection: latest }, storage, 1000)
  discard(token, storage)
  discard("../unrelated", storage)
  assert.equal(storage.getItem(storageKey(token)), null)
  assert.equal(storage.getItem("unrelated"), "preserve")
})
