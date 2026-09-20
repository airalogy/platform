/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { readFileSync } from "node:fs"
import test from "node:test"
import ts from "typescript"

const source = readFileSync(new URL("../src/utils/knowledge-presentation.ts", import.meta.url), "utf8")
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext }, reportDiagnostics: true })
assert.deepEqual(compiled.diagnostics, [])
const { knowledgeViewFromQuery, researchArtifactTypeKey, researchArtifactVersionLabel } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString("base64")}`)

test("Knowledge provenance preserves each supported artifact type and both locale labels exist", () => {
  const locales = ["en-us", "zh-cn"].map(locale => JSON.parse(readFileSync(new URL(`../../../packages/shared/src/locales/langs/${locale}.json`, import.meta.url), "utf8")))
  for (const type of ["record", "data_asset", "knowledge", "paper_library_entry", "action_output", "analysis_publication", "external"]) {
    const key = researchArtifactTypeKey(type)
    assert.equal(key, `page.research.artifactType.${type}`)
    for (const locale of locales)
      assert.equal(typeof key.split(".").reduce((value, part) => value[part], locale), "string")
  }
  for (const unknown of ["legacy_source", "", "__proto__", "constructor"])
    assert.equal(researchArtifactTypeKey(unknown), "page.research.artifactType.external")
})

test("analysis publications and historical action outputs display SHA-256, never a fake version", () => {
  const digest = "c7".repeat(32)
  for (const type of ["analysis_publication", "action_output"]) {
    assert.equal(researchArtifactVersionLabel(type, digest), `SHA-256 ${digest}`)
    assert.equal(researchArtifactVersionLabel(type, digest, true), `SHA-256 ${digest.slice(0, 12)}…`)
    assert.equal(researchArtifactVersionLabel(type, ""), "")
  }
  for (const type of ["record", "data_asset", "knowledge", "paper_library_entry"])
    assert.equal(researchArtifactVersionLabel(type, "12"), "v12")
  assert.equal(researchArtifactVersionLabel("record", null), "")
  assert.equal(researchArtifactVersionLabel("external", undefined), "")
})

test("only an explicit literal items query selects Knowledge Notes; default entries remain Paper Library", () => {
  assert.equal(knowledgeViewFromQuery("items"), "items")
  for (const value of [undefined, null, "papers", "", "other", ["items"], ["items", "papers"], { view: "items" }])
    assert.equal(knowledgeViewFromQuery(value), "papers")
  // The same parser is intentionally applied on initial render and navigation.
  assert.deepEqual([undefined, "items", "papers", "items", undefined].map(knowledgeViewFromQuery), ["papers", "items", "papers", "items", "papers"])
})

test("research navigation supplies only a view hint, consumed initially and on route changes", () => {
  const knowledge = readFileSync(new URL("../src/views/knowledge/index.vue", import.meta.url), "utf8")
  const panel = readFileSync(new URL("../src/views/research/components/research-assets-panel.vue", import.meta.url), "utf8")
  assert.match(knowledge, /const activeView = ref\(knowledgeViewFromQuery\(route\.query\.view\)\)/)
  assert.match(knowledge, /watch\(\(\) => route\.fullPath, async \(\) => \{\s+activeView\.value = knowledgeViewFromQuery\(route\.query\.view\)/)
  assert.match(panel, /function openProjectKnowledge\(\) \{[\s\S]*?query: \{ view: "items" \}/)
  assert.match(knowledge, /\$t\(researchArtifactTypeKey\(source\.source_snapshot\.artifact_type\)\)/)
  assert.match(knowledge, /researchArtifactVersionLabel\(source\.source_snapshot\.artifact_type, source\.source_snapshot\.artifact_version\)/)
  assert.doesNotMatch(knowledge, /artifact_type === "record" \? "Record" : "DataAsset"/)
  assert.doesNotMatch(knowledge, /route\.query\.(?:body|knowledge_id|artifact_id)/)
})
