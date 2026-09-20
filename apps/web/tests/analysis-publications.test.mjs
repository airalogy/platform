/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { readFileSync } from "node:fs"
import test from "node:test"
import ts from "typescript"
import { reactive } from "vue"

const source = readFileSync(new URL("../src/utils/analysis-publications.ts", import.meta.url), "utf8")
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext }, reportDiagnostics: true })
assert.deepEqual(compiled.diagnostics, [])
const { analysisPublicationCommand, publicationConfirmationKey } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString("base64")}`)

test("publication preview freezes literal fields and the exact interpretation without mutating a Vue draft", () => {
  const draft = reactive({
    task_id: "task-1",
    title: " Selected evidence ",
    summary: " Human context ",
    sections: [{ section_id: "source:first", fields: ["dose.mean", "__proto__"] }, { section_id: "source:second", fields: [] }],
    interpretation_revision_id: "exact-revision-id",
  })
  const command = analysisPublicationCommand(draft)
  assert.deepEqual(command, {
    task_id: "task-1",
    title: "Selected evidence",
    summary: "Human context",
    sections: [{ section_id: "source:first", fields: ["dose.mean", "__proto__"] }],
    interpretation_revision_id: "exact-revision-id",
  })
  draft.title = "Edited after preview"
  draft.sections[0].fields.pop()
  draft.interpretation_revision_id = "new-revision"
  assert.equal(command.title, "Selected evidence")
  assert.equal(command.sections[0].fields.length, 2)
  assert.equal(command.interpretation_revision_id, "exact-revision-id")
})

test("a valid v4 idempotency key is available without secure-context randomUUID", () => {
  const keys = Array.from({ length: 100 }, publicationConfirmationKey)
  assert.equal(new Set(keys).size, 100)
  for (const key of keys)
    assert.match(key, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
  assert.doesNotMatch(source, /crypto\.randomUUID/)
})

test("confirmation reuses its frozen command and key; run changes invalidate in-flight UI results", () => {
  const panel = readFileSync(new URL("../src/views/analysis/components/analysis-publication-panel.vue", import.meta.url), "utf8")
  assert.match(panel, /const command = analysisPublicationCommand\(draft\)/)
  assert.match(panel, /prepared = command/)
  assert.match(panel, /\.\.\.prepared,\s+preview_digest: preview\.value\.preview_digest/)
  assert.match(panel, /client_idempotency_key: idempotencyKey/)
  assert.equal(panel.match(/idempotencyKey = publicationConfirmationKey\(\)/g)?.length, 1)
  assert.equal(panel.match(/epoch !== requestEpoch/g)?.length, 4)
  assert.match(panel, /watch\(\(\) => props\.analysisId/)
  assert.match(panel, /expired\.value && !confirmationAttempted\.value/)
  assert.match(panel, /confirmationAttempted\.value = true/)
})

test("published copies are displayed as statistics, remain reviewable and can feed Knowledge", () => {
  const panel = readFileSync(new URL("../src/views/research/components/research-assets-panel.vue", import.meta.url), "utf8")
  assert.match(panel, /<analysis-publication-report :snapshot="item\.artifact_snapshot\.snapshot"/)
  assert.match(panel, /quality_state === "validated" && \["record", "data_asset", "action_output", "analysis_publication"\]/)
  const report = readFileSync(new URL("../src/views/analysis/components/analysis-publication-report.vue", import.meta.url), "utf8")
  assert.match(report, /<analysis-result-table :result="section\.report"/)
  assert.match(report, /snapshot\.interpretation\.content\.limitations/)
  assert.match(report, /record\.record_version/)
  assert.doesNotMatch(report, /v-html|run\.question|source\.data/)
})
