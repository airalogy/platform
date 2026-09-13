/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { readFileSync } from "node:fs"
import test from "node:test"
import ts from "typescript"

const source = readFileSync(new URL("../src/utils/workflow-conversion.ts", import.meta.url), "utf8")
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext }, reportDiagnostics: true })
assert.deepEqual(compiled.diagnostics, [])
const { createWorkflowConversionDraft, workflowConversionReady } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString("base64")}`)
function context() {
  return {
    source: { project_id: "project", digest: "fixed-source", title: "Synthetic legacy workflow" },
    nodes: [1, 2].map(index => ({ protocol_index: index, protocol_id: `protocol-${index}`, suggested_version_id: `version-${index}`, versions: [{ id: "latest-version", version: "2.0.0" }, { id: `version-${index}`, version: "1.0.0" }] })),
    edges: [{ edge_id: "a", text: "1 -> 2", supported: true, source_protocol_index: 1, target_protocol_index: 2 }],
    blockers: [],
    logic_text: "Sensitive old decision guidance",
    path_data: { records: ["old-record"], private_goal: "private research goal" },
  }
}
function acknowledge(draft) {
  return { ...draft, acknowledge_versions: true, acknowledge_structure_only: true, acknowledge_logic_omission: true }
}
test("conversion copies only explicit structure and starts with every acknowledgement unchecked", () => {
  const value = context()
  const draft = createWorkflowConversionDraft(value)
  assert.equal(workflowConversionReady(draft, value), false)
  assert.equal(workflowConversionReady(acknowledge(draft), value), true)
  assert.equal(draft.description, "")
  for (const privateText of ["Sensitive", "old-record", "private research goal", "path_data", "logic_text"])
    assert.equal(JSON.stringify(draft).includes(privateText), false)
})
test("conversion only suggests a resolvable embedded revision and never selects latest for an unknown version", () => {
  const value = context()
  assert.equal(createWorkflowConversionDraft(value).nodes[0].protocol_version_id, "version-1")
  value.nodes[0].suggested_version_id = "not-found"
  const draft = acknowledge(createWorkflowConversionDraft(value))
  assert.equal(draft.nodes[0].protocol_version_id, "")
  assert.equal(workflowConversionReady(draft, value), false)
  draft.nodes[0].protocol_version_id = "latest-version"
  assert.equal(workflowConversionReady(draft, value), true)
})
test("unsupported or unreadable old edges are not guessed into directions", () => {
  const value = context()
  value.edges.push({ edge_id: "b", text: "2 <-> 1", supported: false, source_protocol_index: 2, target_protocol_index: 1 })
  value.edges.push({ edge_id: "c", text: "when the scientist decides", supported: false, source_protocol_index: null, target_protocol_index: null })
  assert.deepEqual(createWorkflowConversionDraft(value).edges, [{ source_protocol_index: 1, target_protocol_index: 2 }])
})
test("changed sources, unavailable Protocols, replacement identities and duplicate nodes cannot be previewed as ready", () => {
  const value = context()
  const draft = acknowledge(createWorkflowConversionDraft(value))
  assert.equal(workflowConversionReady({ ...draft, source_digest: "stale" }, value), false)
  assert.equal(workflowConversionReady({ ...draft, project_id: "other" }, value), false)
  assert.equal(workflowConversionReady({ ...draft, nodes: [draft.nodes[0], draft.nodes[0]] }, value), false)
  assert.equal(workflowConversionReady(draft, { ...value, blockers: [{ code: "protocol_unavailable" }] }), false)
  value.nodes[0].protocol_id = null
  assert.equal(workflowConversionReady(draft, value), false)
})
test("legacy conversion and controlled-file labels have complete matching English and Chinese keys", () => {
  const messages = ["en-us", "zh-cn"].map(locale => JSON.parse(readFileSync(new URL(`../../../packages/shared/src/locales/langs/${locale}.json`, import.meta.url), "utf8")).page)
  for (const namespace of ["workflowLegacy", "workflowFiles"]) {
    assert.deepEqual(Object.keys(messages[0][namespace]).sort(), Object.keys(messages[1][namespace]).sort())
    for (const locale of messages)
      assert.ok(Object.values(locale[namespace]).every(text => typeof text === "string" && text.trim()))
  }
})
