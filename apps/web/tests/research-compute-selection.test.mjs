/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { readFileSync } from "node:fs"
import test from "node:test"
import ts from "typescript"

const source = readFileSync(new URL("../src/utils/research-compute-selection.ts", import.meta.url), "utf8")
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext }, reportDiagnostics: true })
assert.deepEqual(compiled.diagnostics, [])
const { resolveResearchComputeSelection } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString("base64")}`)
const old = { source_id: "environment", source_revision_id: "revision-1", available: true }
const latest = { ...old, source_revision_id: "revision-2" }
const retired = { ...old, source_revision_id: "revision-0", available: false }

test("exact environment selection keeps older enabled revisions, while suggestions explicitly resolve current revisions", () => {
  assert.deepEqual(resolveResearchComputeSelection([], [old.source_revision_id], [latest], [old, latest]), [old.source_revision_id])
  assert.deepEqual(resolveResearchComputeSelection([old.source_id], [], [latest], [old, latest]), [latest.source_revision_id])
  assert.deepEqual(resolveResearchComputeSelection([], [], [latest], [old, latest]), [])
})

test("unknown or unavailable suggested environments cannot silently disappear from the confirmed Task", () => {
  assert.throws(() => resolveResearchComputeSelection(["unknown"], [], [latest], [old, latest]))
  assert.throws(() => resolveResearchComputeSelection([], ["unknown-revision"], [latest], [old, latest]))
  assert.throws(() => resolveResearchComputeSelection([], [retired.source_revision_id], [latest], [old, latest, retired]))
})

test("only one explicit revision per environment is allowed and mixed legacy/exact selections are rejected", () => {
  assert.throws(() => resolveResearchComputeSelection([], [old.source_revision_id, latest.source_revision_id], [latest], [old, latest]))
  assert.throws(() => resolveResearchComputeSelection([old.source_id], [old.source_revision_id], [latest], [old, latest]))
  assert.throws(() => resolveResearchComputeSelection([], [old.source_revision_id, old.source_revision_id], [latest], [old, latest]))
})
