/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { readFileSync } from "node:fs"
import test from "node:test"
import ts from "typescript"

const source = readFileSync(new URL("../src/utils/workflow-editor.ts", import.meta.url), "utf8")
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext }, reportDiagnostics: true })
assert.deepEqual(compiled.diagnostics, [])
const { addWorkflowAssetInput, removeWorkflowAssetInput, workflowAssetSourceField, workflowAssetVersionCompatible, loadWorkflowAssetPage, createWorkflowComputeFileOutput, createWorkflowComputeOutput, createWorkflowAnalysisNode, createWorkflowId, normalizeWorkflowGraph, emptyWorkflowGraph, workflowGraphProblem, removeWorkflowNode, duplicateWorkflowNode, moveWorkflowNode, taskSupportsWorkflow, workflowDataProblem, workflowFields, workflowFieldsCompatible, workflowScalarFields, workflowPathKey, parseWorkflowScalar, workflowConditionText, workflowAnalysisProblem, workflowAnalysisOutputKey } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString("base64")}`)

function node(id, version = "version-1") {
  return { node_id: id, kind: "protocol", protocol_id: "protocol-1", protocol_version_id: version, title: `Card ${id}`, position: { x: 12, y: 24 }, initial_values: {} }
}
function edge(source, target) {
  return { edge_id: `${source}-${target}`, source_node_id: source, target_node_id: target, condition: null }
}
function graph(nodes, edges = []) {
  return { ...emptyWorkflowGraph(), nodes, edges }
}

test("HTTP-only intranet deployments can create UUIDs without secure-context randomUUID", () => {
  const ids = new Set(Array.from({ length: 100 }, () => createWorkflowId()))
  assert.equal(ids.size, 100)
  for (const id of ids)
    assert.match(id, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
})

test("API-authored revisions without canvas positions gain local layout without altering identities or saved values", () => {
  const original = graph([{ ...node("a"), position: null }, node("b")], [edge("a", "b")])
  const normalized = normalizeWorkflowGraph(original)
  assert.deepEqual(normalized.nodes[0].position, { x: 40, y: 40 })
  assert.equal(normalized.nodes[0].node_id, "a")
  assert.deepEqual(normalized.nodes[1], original.nodes[1])
  assert.deepEqual(normalized.edges, original.edges)
  assert.equal(original.nodes[0].position, null)
})

test("one card and independent parallel cards of the same Protocol are valid without AI", () => {
  assert.equal(workflowGraphProblem(emptyWorkflowGraph()), "empty")
  assert.equal(workflowGraphProblem(graph([node("first")])), null)
  assert.equal(workflowGraphProblem(graph([node("first"), node("second")])), null)
})

test("sequential, fork and join dependencies form a finite DAG", () => {
  const value = graph([node("a"), node("b"), node("c"), node("d")], [edge("a", "b"), edge("a", "c"), edge("b", "d"), edge("c", "d")])
  assert.equal(workflowGraphProblem(value), null)
  value.edges.push(edge("d", "a"))
  assert.equal(workflowGraphProblem(value), "cycle")
})

test("unknown, duplicate and self dependencies fail before preview", () => {
  assert.equal(workflowGraphProblem(graph([node("a")], [edge("a", "missing")])), "invalidEdge")
  assert.equal(workflowGraphProblem(graph([node("a")], [edge("a", "a")])), "invalidEdge")
  assert.equal(workflowGraphProblem(graph([node("a"), node("b")], [edge("a", "b"), edge("a", "b")])), "invalidEdge")
})

test("exact Protocol revision and unique node identity are required", () => {
  assert.equal(workflowGraphProblem(graph([node("a"), node("a")])), "incomplete")
  assert.equal(workflowGraphProblem(graph([{ ...node("a"), protocol_version_id: "" }])), "incomplete")
  assert.equal(workflowGraphProblem(graph([{ ...node("a"), title: "   " }])), "incomplete")
})

test("duplicating a Protocol card uses a new identity without sharing editable values", () => {
  const original = { ...node("a"), initial_values: { sample: { name: "A" } } }
  const duplicate = duplicateWorkflowNode(original, "b")
  assert.equal(duplicate.node_id, "b")
  assert.equal(duplicate.protocol_version_id, original.protocol_version_id)
  duplicate.initial_values.sample.name = "B"
  assert.equal(original.initial_values.sample.name, "A")
  assert.notDeepEqual(duplicate.position, original.position)
})

test("reordering cards preserves stable identities, versions, coordinates and execution edges", () => {
  const original = graph([node("a"), node("b"), node("c")], [edge("a", "c")])
  const moved = moveWorkflowNode(original, "c", -1)
  assert.deepEqual(moved.nodes.map(item => item.node_id), ["a", "c", "b"])
  assert.deepEqual(original.nodes.map(item => item.node_id), ["a", "b", "c"])
  assert.equal(moved.edges, original.edges)
  assert.equal(moved.nodes[1], original.nodes[2])
  assert.equal(moveWorkflowNode(original, "a", -1), original)
  assert.equal(moveWorkflowNode(original, "missing", 1), original)
})

test("removing a card removes only its incident dependencies", () => {
  const original = graph([node("a"), node("b"), node("c")], [edge("a", "b"), edge("b", "c"), edge("a", "c")])
  const removed = removeWorkflowNode(original, "b")
  assert.deepEqual(removed.nodes.map(item => item.node_id), ["a", "c"])
  assert.deepEqual(removed.edges, [edge("a", "c")])
  assert.equal(original.edges.length, 3)
})

test("Research Environment matching uses exact version IDs, not Protocol identity or display version", () => {
  const task = { protocols: [{ id: "protocol-1", version_id: "version-1", version: "1.0.0" }] }
  assert.equal(taskSupportsWorkflow(task, graph([node("a"), node("b")])), true)
  assert.equal(taskSupportsWorkflow(task, graph([node("a"), node("b", "version-2")])), false)
  assert.equal(taskSupportsWorkflow({ protocols: [] }, graph([node("a")])), false)
  assert.equal(taskSupportsWorkflow(task, emptyWorkflowGraph()), false)
})

test("Workflow labels have complete English and Chinese keys", () => {
  const en = JSON.parse(readFileSync(new URL("../../../packages/shared/src/locales/langs/en-us.json", import.meta.url), "utf8")).page.workflowDefinitions
  const zh = JSON.parse(readFileSync(new URL("../../../packages/shared/src/locales/langs/zh-cn.json", import.meta.url), "utf8")).page.workflowDefinitions
  assert.deepEqual(Object.keys(en).sort(), Object.keys(zh).sort())
  assert.deepEqual(Object.keys(en.validation).sort(), Object.keys(zh.validation).sort())
  assert.deepEqual(Object.keys(en.resolution).sort(), Object.keys(zh.resolution).sort())
  for (const [key, value] of Object.entries(zh))
    assert.ok(typeof value === "object" || value.trim(), `Missing Chinese label: ${key}`)
})

test("Task restrictions explain partial source access without implying all independent cards are blocked", () => {
  const translations = ["en-us", "zh-cn"].map(locale => JSON.parse(readFileSync(new URL(`../../../packages/shared/src/locales/langs/${locale}.json`, import.meta.url), "utf8")).page.workflowDefinitions.resolution)
  for (const translation of translations) {
    assert.ok(translation.taskRestrictedHint.trim())
    assert.notEqual(translation.taskRestrictedHint, translation.restrictedHint)
  }
  assert.match(translations[0].taskRestrictedHint, /independent cards/)
  assert.match(translations[1].taskRestrictedHint, /独立卡片仍可/)
  const taskView = readFileSync(new URL("../src/views/research/detail.vue", import.meta.url), "utf8")
  assert.match(taskView, /v-if="task\.workflow_data_restricted"[^>]*data-testid="workflow-task-restricted"[\s\S]*?resolution\.taskRestrictedHint/)
})

function scalarField(key, type = "number", unit = "mg/L") {
  return { path: ["var", key], title: key, value_type: type, unit, nullable: false }
}
function fieldCatalog() {
  return [{ id: "protocol-1", versions: [{ id: "version-1", fields: [scalarField("measurement"), scalarField("a.b"), scalarField("note", "string", null), scalarField("ready", "boolean", null)] }, { id: "version-2", fields: [scalarField("measurement", "number", "g/L")] }] }]
}
function condition(update = {}) {
  return { path: ["var", "measurement"], value_type: "number", operator: "gte", value: 2, unit: "mg/L", ...update }
}
function binding(update = {}) {
  return { binding_id: "binding-a", source_node_id: "a", source_path: ["var", "measurement"], target_node_id: "b", target_path: ["var", "measurement"], value_type: "number", unit: "mg/L", cardinality: "one", ...update }
}

function assetBinding(update = {}) {
  return { binding_id: "asset_binding_1", input_id: "asset_1", source_path: ["json", "metrics", "mean"], target_node_id: "a", target_path: ["var", "measurement"], value_type: "number", unit: "mg/L", cardinality: "one", ...update }
}

test("asset versions load one page at a time and keep previously loaded exact versions", async () => {
  const original = { items: [], nextOffset: 0 }
  const requested = []
  const first = await loadWorkflowAssetPage(original, async (offset) => {
    requested.push(offset)
    return { items: [{ version_id: "fixed-old", version: 1 }], next_offset: 100 }
  })
  assert.deepEqual(requested, [0])
  assert.deepEqual(original, { items: [], nextOffset: 0 })
  assert.equal(first.nextOffset, 100)
  const second = await loadWorkflowAssetPage(first, async (offset) => {
    requested.push(offset)
    return { items: [{ version_id: "fixed-old", version: 999 }, { version_id: "new", version: 2 }, { version_id: "new", version: 2 }], next_offset: null }
  })
  assert.deepEqual(requested, [0, 100])
  assert.deepEqual(second.items.map(item => item.version), [1, 2])
  assert.equal(second.items[0], first.items[0])
  assert.equal(await loadWorkflowAssetPage(second, () => {
    throw new Error("must not request after last page")
  }), second)
})

test("asset version page failures preserve prior choices and cursor for a successful retry", async () => {
  const original = { items: [{ version_id: "chosen-version" }], nextOffset: 100 }
  const before = JSON.stringify(original)
  await assert.rejects(loadWorkflowAssetPage(original, async (offset) => {
    assert.equal(offset, 100)
    throw new Error("temporary directory failure")
  }), /temporary directory failure/)
  assert.equal(JSON.stringify(original), before)
  const retried = await loadWorkflowAssetPage(original, async (offset) => {
    assert.equal(offset, 100)
    return { items: [{ version_id: "another-version" }], next_offset: null }
  })
  assert.deepEqual(retried.items.map(item => item.version_id), ["chosen-version", "another-version"])
  assert.equal(JSON.stringify(original), before)
})

test("repeated, backwards or malformed asset pagination cursors fail without advancing", async () => {
  const original = { items: [{ version_id: "chosen-version" }], nextOffset: 100 }
  for (const next_offset of [100, 0, -1, 100.5, Number.NaN]) {
    await assert.rejects(loadWorkflowAssetPage(original, async () => ({ items: [{ version_id: "discarded-page" }], next_offset })), /pagination cursor/)
    assert.deepEqual(original, { items: [{ version_id: "chosen-version" }], nextOffset: 100 })
  }
  const retried = await loadWorkflowAssetPage(original, async () => ({ items: [], next_offset: 200 }))
  assert.equal(retried.nextOffset, 200)
})

test("DataAsset slots upgrade only edited graphs, never become execution nodes or default old keys", () => {
  const original = graph([node("a")])
  const serialized = JSON.stringify(original)
  const next = addWorkflowAssetInput(original, "Calibrated measurements")
  assert.equal(next.schema_version, 5)
  assert.deepEqual(next.asset_inputs, [{ input_id: "asset_1", label: "Calibrated measurements" }])
  assert.deepEqual(next.asset_bindings, [])
  assert.equal(next.nodes, original.nodes)
  assert.equal(JSON.stringify(original), serialized)
  assert.equal(JSON.stringify(normalizeWorkflowGraph(original)), serialized)
  for (const schema_version of [1, 2, 3, 4]) {
    assert.equal(workflowGraphProblem({ ...original, schema_version, asset_inputs: [] }), "incomplete")
    assert.equal(workflowGraphProblem({ ...original, schema_version, asset_bindings: [] }), "incomplete")
  }
  const bound = { ...next, asset_bindings: [assetBinding()] }
  assert.equal(workflowGraphProblem(bound), null)
  assert.equal(workflowDataProblem(bound, fieldCatalog()), null)
  assert.equal(workflowDataProblem(next, fieldCatalog()), "invalidBinding")
  assert.deepEqual(removeWorkflowAssetInput(bound, "asset_1").asset_bindings, [])
  assert.deepEqual(removeWorkflowNode(bound, "a").asset_bindings, [])
  assert.equal(bound.asset_bindings.length, 1)
})

test("resource mappings share target and binding ID uniqueness with all card mappings", () => {
  const base = { ...addWorkflowAssetInput(graph([node("a"), node("b")], [edge("a", "b")]), "Source"), asset_bindings: [assetBinding({ target_node_id: "b" })] }
  assert.equal(workflowDataProblem({ ...base, bindings: [binding()] }, fieldCatalog()), "invalidBinding")
  assert.equal(workflowDataProblem({ ...base, bindings: [binding({ binding_id: "asset_binding_1", target_path: ["var", "a.b"] })] }, fieldCatalog()), "invalidBinding")
  assert.equal(workflowDataProblem({ ...base, asset_bindings: [assetBinding(), assetBinding({ binding_id: "another" })] }, fieldCatalog()), "invalidBinding")
  base.nodes[1].initial_values = { measurement: 0 }
  assert.equal(workflowDataProblem(base, fieldCatalog()), "invalidBinding")
})

test("DataAsset JSON declarations preserve literal keys and reject unsupported paths or units", () => {
  const base = addWorkflowAssetInput(graph([node("a")]), "Source")
  const validate = update => workflowDataProblem({ ...base, asset_bindings: [assetBinding(update)] }, fieldCatalog())
  assert.equal(validate({ source_path: ["json", "literal.with.dots"] }), null)
  assert.equal(validate({ source_path: ["json", "literal", "with", "dots"] }), null)
  for (const update of [
    { source_path: ["json"] },
    { source_path: ["json", ""] },
    { source_path: ["json", 0] },
    { source_path: ["json", ...Array.from({ length: 17 }, () => "nested")] },
    { source_path: ["json", "a".repeat(256)] },
    { source_path: ["var", "value"] },
    { input_id: "missing" },
    { binding_id: "INVALID" },
    { unit: "mg" },
    { unit: " mg/L" },
    { value_type: "string", target_path: ["var", "note"], unit: "mg/L" },
  ])
    assert.equal(validate(update), "invalidBinding", JSON.stringify(update))
  assert.equal(validate({ value_type: "string", target_path: ["var", "note"], unit: null }), null)
})

test("exact DataAsset version choices require declared fields and compatible targets, without latest fallback", () => {
  const base = { ...addWorkflowAssetInput(graph([node("a")]), "Source"), asset_bindings: [assetBinding()] }
  const version = { version_id: "fixed-version", fields: [{ ...scalarField("unused"), path: ["json", "metrics", "mean"] }] }
  assert.equal(workflowAssetVersionCompatible(version, base.asset_bindings, fieldCatalog(), base), true)
  assert.equal(workflowAssetVersionCompatible({ ...version, fields: [{ ...version.fields[0], unit: "g/L" }] }, base.asset_bindings, fieldCatalog(), base), false)
  assert.equal(workflowAssetVersionCompatible({ ...version, fields: [{ ...version.fields[0], path: ["json", "metrics.mean"] }] }, base.asset_bindings, fieldCatalog(), base), false)
  assert.equal(workflowAssetVersionCompatible({ ...version, fields: [] }, base.asset_bindings, fieldCatalog(), base), false)
  assert.equal(workflowAssetVersionCompatible(version, [], fieldCatalog(), base), false)
})

test("full DataAsset files bind only to FileId fields and enforce extension compatibility at selection", () => {
  const file = { path: ["var", "attachment"], title: "Attachment", value_type: "file", nullable: false, unit: null, file_extensions: ["csv"] }
  const catalog = [{ id: "protocol-1", versions: [{ id: "version-1", fields: [file] }] }]
  const base = { ...addWorkflowAssetInput(graph([node("a")]), "Source"), asset_bindings: [assetBinding({ source_path: ["file"], value_type: "file", unit: null, target_path: file.path })] }
  assert.equal(workflowDataProblem(base, catalog), null)
  assert.deepEqual(workflowAssetSourceField(base.asset_bindings[0]).file_extensions, null)
  const version = { fields: [{ ...file, path: ["file"] }] }
  assert.equal(workflowAssetVersionCompatible(version, base.asset_bindings, catalog, base), true)
  assert.equal(workflowAssetVersionCompatible({ fields: [{ ...version.fields[0], file_extensions: ["pdf"] }] }, base.asset_bindings, catalog, base), false)
  assert.equal(workflowDataProblem({ ...base, asset_bindings: [{ ...base.asset_bindings[0], source_path: ["file", "path"] }] }, catalog), "invalidBinding")
})

test("DataAsset UI translations and source receipts stay separate from Record sources", () => {
  const en = JSON.parse(readFileSync(new URL("../../../packages/shared/src/locales/langs/en-us.json", import.meta.url), "utf8")).page.workflowAssets
  const zh = JSON.parse(readFileSync(new URL("../../../packages/shared/src/locales/langs/zh-cn.json", import.meta.url), "utf8")).page.workflowAssets
  assert.deepEqual(Object.keys(en).sort(), Object.keys(zh).sort())
  for (const value of Object.values(zh))
    assert.ok(value.trim())
  const receipt = readFileSync(new URL("../src/views/workflow-definitions/components/workflow-resolution-summary.vue", import.meta.url), "utf8")
  assert.match(receipt, /receipt\.asset_sources/)
  assert.match(receipt, /data-testid="workflow-resolved-asset"/)
  assert.match(receipt, /source\.data_asset_version_id/)
})

test("conditional comparison values remain strict and unsafe numbers cannot silently round", () => {
  assert.equal(parseWorkflowScalar("false", "boolean"), false)
  assert.equal(parseWorkflowScalar("0", "number"), 0)
  assert.equal(parseWorkflowScalar("-2.5e-2", "number"), -0.025)
  assert.equal(parseWorkflowScalar("", "string"), "")
  for (const [value, type] of [["", "number"], [" ", "number"], ["1.", "number"], ["01", "number"], ["1.5", "integer"], ["Infinity", "number"], ["1e999", "number"], ["1e-999", "number"], ["9007199254740993", "number"], ["0", "boolean"], ["False", "boolean"]])
    assert.throws(() => parseWorkflowScalar(value, type))
})

test("conditions use the exact pinned source field, scalar type and unit", () => {
  const value = graph([node("a"), node("b")], [{ ...edge("a", "b"), condition: condition() }])
  assert.equal(workflowDataProblem(value, fieldCatalog()), null)
  value.nodes[0].protocol_version_id = "version-2"
  assert.equal(workflowDataProblem(value, fieldCatalog()), "invalidCondition")
  value.nodes[0].protocol_version_id = "version-1"
  value.edges[0].condition = condition({ path: ["var", "unknown"] })
  assert.equal(workflowDataProblem(value, fieldCatalog()), "invalidCondition")
  value.edges[0].condition = condition({ value: "2" })
  assert.equal(workflowDataProblem(value, fieldCatalog()), "invalidCondition")
  value.edges[0].condition = condition({ path: ["var", "ready"], value_type: "boolean", value: false, unit: null, operator: "gt" })
  assert.equal(workflowDataProblem(value, fieldCatalog()), "invalidCondition")
})

test("literal dotted field keys never become nested paths or expressions", () => {
  const value = graph([node("a"), node("b")], [{ ...edge("a", "b"), condition: condition({ path: ["var", "a.b"] }) }])
  assert.equal(workflowDataProblem(value, fieldCatalog()), null)
  assert.notEqual(workflowPathKey(["var", "a.b"]), workflowPathKey(["var", "a", "b"]))
  assert.match(workflowConditionText(value.edges[0].condition), /"a\.b" ≥ 2 mg\/L/)
})

test("fixed scalar field mappings require direct dependencies and no unit conversion", () => {
  const value = { ...graph([node("a"), node("b")], [edge("a", "b")]), bindings: [binding()] }
  assert.equal(workflowDataProblem(value, fieldCatalog()), null)
  assert.equal(workflowDataProblem({ ...value, edges: [] }, fieldCatalog()), "invalidBinding")
  assert.equal(workflowDataProblem({ ...value, bindings: [binding({ unit: "g/L" })] }, fieldCatalog()), "invalidBinding")
  assert.equal(workflowDataProblem({ ...value, nodes: [node("a"), node("b", "version-2")] }, fieldCatalog()), "invalidBinding")
  assert.equal(workflowFieldsCompatible(scalarField("a"), scalarField("b", "integer")), false)
})

test("mappings cannot overwrite explicit initial values or target the same field twice", () => {
  const value = { ...graph([node("a"), node("b")], [edge("a", "b")]), bindings: [binding()] }
  assert.equal(workflowDataProblem({ ...value, bindings: [binding(), binding({ binding_id: "binding-b" })] }, fieldCatalog()), "invalidBinding")
  value.nodes[1].initial_values = { measurement: 0 }
  assert.equal(workflowDataProblem(value, fieldCatalog()), "invalidBinding")
  value.nodes[1].initial_values = { "a.b": false }
  value.bindings = [binding({ target_path: ["var", "a.b"] })]
  assert.equal(workflowDataProblem(value, fieldCatalog()), "invalidBinding")
})

test("deleting a node removes incident mappings while copying/reordering leaves lineage independent", () => {
  const value = { ...graph([node("a"), node("b")], [edge("a", "b")]), bindings: [binding()] }
  assert.deepEqual(removeWorkflowNode(value, "a").bindings, [])
  assert.equal(moveWorkflowNode(value, "b", -1).bindings, value.bindings)
  assert.equal(workflowFields(node("a"), fieldCatalog())[0].unit, "mg/L")
  assert.equal(workflowFields(node("a", "missing"), fieldCatalog()).length, 0)
})

test("source-only schema fields remain valid conditions but cannot be binding targets", () => {
  const catalog = fieldCatalog()
  catalog[0].versions[0].fields[0].bindable_target = false
  const value = graph([node("a"), node("b")], [{ ...edge("a", "b"), condition: condition() }])
  assert.equal(workflowDataProblem(value, catalog), null)
  assert.equal(workflowFieldsCompatible(scalarField("measurement"), { ...scalarField("measurement"), bindable_target: false }), false)
  value.bindings = [binding()]
  assert.equal(workflowDataProblem(value, catalog), "invalidBinding")
})

function publication() {
  return { id: "published-1", title: "Shared mean", protocol_id: "protocol-1", protocol_version_id: "version-1", recipe: { numeric_fields: ["measurement"], group_by: [] } }
}
function analysisCard() {
  return { ...createWorkflowAnalysisNode(publication(), "analysis", { x: 50, y: 30 }), record_sources: [{ source_node_id: "a", cardinality: "one" }] }
}
function analysisGraph() {
  return { ...graph([node("a"), analysisCard(), node("b")], [edge("a", "analysis"), edge("analysis", "b")]), schema_version: 2 }
}

test("analysis cards only reference explicit publications and never inherit private recipes, provenance or Record selections", () => {
  const value = createWorkflowAnalysisNode({ ...publication(), source_selection: { record_ids: ["private-record"] }, ai_provenance: { question: "private question" } }, "analysis", { x: 4, y: 8 })
  assert.deepEqual(Object.keys(value).sort(), ["node_id", "kind", "method_publication_id", "record_sources", "input_policy", "analysis_outputs", "title", "position"].sort())
  assert.deepEqual(value.record_sources, [])
  assert.equal(JSON.stringify(value).includes("private"), false)
})

test("v1 Protocol revisions do not silently upgrade while Analysis graphs require schema v2", () => {
  const previous = graph([node("a")])
  assert.equal(normalizeWorkflowGraph(previous).schema_version, 1)
  const value = analysisGraph()
  assert.equal(workflowGraphProblem(value), null)
  assert.equal(workflowGraphProblem({ ...value, schema_version: 1 }), "incomplete")
  assert.equal(removeWorkflowNode(value, "analysis").schema_version, 2)
})

test("analysis Record inputs require all explicit, distinct, directly preceding compatible Protocol sources", () => {
  const value = analysisGraph()
  assert.equal(workflowAnalysisProblem(value, [publication()]), null)
  assert.equal(workflowAnalysisProblem(value, []), "invalidAnalysis")
  assert.equal(workflowAnalysisProblem({ ...value, edges: [] }, [publication()]), "invalidAnalysis")
  value.nodes[1].record_sources.push({ source_node_id: "a", cardinality: "one" })
  assert.equal(workflowAnalysisProblem(value, [publication()]), "invalidAnalysis")
  value.nodes[1].record_sources = [{ source_node_id: "analysis", cardinality: "one" }]
  assert.equal(workflowAnalysisProblem(value, [publication()]), "invalidAnalysis")
})

test("duplicating and deleting cards cannot retain hidden Record source links", () => {
  const value = analysisGraph()
  assert.deepEqual(duplicateWorkflowNode(value.nodes[1], "copy").record_sources, [])
  assert.deepEqual(removeWorkflowNode(value, "a").nodes.find(node => node.kind === "analysis").record_sources, [])
})

test("analysis conditions and mappings use only exact server-reviewed output paths and units", () => {
  const value = analysisGraph()
  const output = { path: ["analysis", "mean"], title: "Mean", value_type: "number", unit: "mg/L", nullable: true }
  value.bindings = [binding({ source_node_id: "analysis", source_path: output.path })]
  assert.equal(workflowDataProblem(value, fieldCatalog(), { analysis: [output] }), null)
  assert.equal(workflowDataProblem(value, fieldCatalog()), "invalidBinding")
  value.bindings[0].source_path = ["analysis", "invented"]
  assert.equal(workflowDataProblem(value, fieldCatalog(), { analysis: [output] }), "invalidBinding")
  const originalKey = workflowAnalysisOutputKey(value.nodes[1])
  value.nodes[1].analysis_outputs.push({ output_id: "mean", field: "measurement", statistic: "mean", group: {} })
  assert.notEqual(workflowAnalysisOutputKey(value.nodes[1]), originalKey)
})

test("Research Environment matching pins published analysis Protocol schema without treating an analysis as a Protocol card", () => {
  const task = { protocols: [{ id: "protocol-1", version_id: "version-1" }] }
  assert.equal(taskSupportsWorkflow(task, analysisGraph(), [publication()]), true)
  assert.equal(taskSupportsWorkflow(task, analysisGraph(), [{ ...publication(), protocol_version_id: "version-2" }]), false)
  assert.equal(taskSupportsWorkflow(task, analysisGraph()), false)
})

test("Project method publication and Analysis card labels have matching nonempty English and Chinese keys", () => {
  const messages = ["en-us", "zh-cn"].map(locale => JSON.parse(readFileSync(new URL(`../../../packages/shared/src/locales/langs/${locale}.json`, import.meta.url), "utf8")).page.workflowAnalysis)
  assert.deepEqual(Object.keys(messages[0]).sort(), Object.keys(messages[1]).sort())
  for (const locale of messages)
    assert.ok(Object.values(locale).every(text => typeof text === "string" && text.trim()))
})

function computePublication() {
  return { ...publication(), engine_version: "airalogy.compute.analysis.v1", recipe: { kind: "compute", language: "python", environment_revision_id: "environment-revision-1", source_code: "print('synthetic')", parameters: { threshold: 7 } }, compute_contract: { result_schema: { type: "object" } } }
}
function computeGraph() {
  const card = createWorkflowAnalysisNode(computePublication(), "analysis", { x: 0, y: 0 })
  card.record_sources = [{ source_node_id: "a", cardinality: "one" }]
  return { ...graph([node("a"), card, node("b")], [edge("a", "analysis"), edge("analysis", "b")]), schema_version: 3 }
}

test("Compute cards explicitly use graph v3 without copying source code, parameters or private origins into cards", () => {
  const value = computeGraph()
  const card = value.nodes[1]
  assert.equal(card.analysis_kind, "compute")
  assert.deepEqual(card.compute_outputs, [])
  assert.equal("analysis_outputs" in card, false)
  assert.equal("recipe" in card, false)
  assert.equal(JSON.stringify(card).includes("synthetic"), false)
  assert.equal(workflowGraphProblem(value), null)
  assert.equal(workflowGraphProblem({ ...value, schema_version: 2 }), "incomplete")
  assert.equal(normalizeWorkflowGraph(analysisGraph()).schema_version, 2)
  assert.equal("analysis_kind" in normalizeWorkflowGraph(analysisGraph()).nodes[1], false)
})

test("Compute cards require a published compute contract and reject a mismatched builtin kind", () => {
  assert.equal(workflowAnalysisProblem(computeGraph(), [computePublication()]), null)
  assert.equal(workflowAnalysisProblem(computeGraph(), [publication()]), "invalidAnalysis")
  assert.equal(workflowAnalysisProblem(computeGraph(), [{ ...computePublication(), compute_contract: undefined }]), "invalidAnalysis")
  assert.equal(workflowAnalysisProblem(analysisGraph(), [computePublication()]), "invalidAnalysis")
})

test("Compute ports preserve server-authored literal keys, units and nullable metadata, never infer from code", () => {
  const field = { path: ["metrics", "a.b"], title: "Synthetic literal-key metric", value_type: "number", unit: "mg/L", nullable: true, bindable_target: false, extra: "not a port contract" }
  const port = createWorkflowComputeOutput("mean", field)
  assert.deepEqual(port, { output_id: "mean", path: ["metrics", "a.b"], value_type: "number", unit: "mg/L", nullable: true })
  port.path.push("changed")
  assert.deepEqual(field.path, ["metrics", "a.b"])
  const value = computeGraph()
  const key = workflowAnalysisOutputKey(value.nodes[1])
  value.nodes[1].compute_outputs.push(createWorkflowComputeOutput("mean", field))
  assert.notEqual(workflowAnalysisOutputKey(value.nodes[1]), key)
  value.bindings = [binding({ source_node_id: "analysis", source_path: ["analysis", "mean"] })]
  assert.equal(workflowDataProblem(value, fieldCatalog(), { analysis: [{ ...field, path: ["analysis", "mean"] }] }), null)
  assert.equal(workflowDataProblem(value, fieldCatalog()), "invalidBinding")
})

test("Compute Workflow tasks must pin the exact environment revision, never substitute the newest environment", () => {
  const task = { protocols: [{ id: "protocol-1", version_id: "version-1" }], compute: [{ source_id: "environment", source_revision_id: "environment-revision-1" }] }
  assert.equal(taskSupportsWorkflow(task, computeGraph(), [computePublication()]), true)
  assert.equal(taskSupportsWorkflow({ ...task, compute: [] }, computeGraph(), [computePublication()]), false)
  assert.equal(taskSupportsWorkflow({ ...task, compute: [{ source_id: "environment", source_revision_id: "environment-revision-2" }] }, computeGraph(), [computePublication()]), false)
})

function fileField(extensions = ["csv"], patch = {}) {
  return { path: ["var", "source_file"], title: "Synthetic data file", value_type: "file", unit: null, nullable: false, file_extensions: extensions, ...patch }
}
test("file references are not strings, cannot become conditions and enforce declared extension compatibility", () => {
  assert.equal(workflowFieldsCompatible(fileField(), scalarField("source_file", "string")), false)
  assert.equal(workflowFieldsCompatible(fileField(), fileField(["pdf"])), false)
  assert.equal(workflowFieldsCompatible(fileField(["csv", "txt"]), fileField(["csv"])), false)
  assert.equal(workflowFieldsCompatible(fileField(["csv"]), fileField(["csv", "txt"])), true)
  assert.equal(workflowFieldsCompatible(fileField(null), fileField(["csv"])), true)
  assert.equal(workflowFieldsCompatible(fileField(), fileField(null, { bindable_target: false })), false)
  assert.deepEqual(workflowScalarFields([fileField(), scalarField("measurement")]), [scalarField("measurement")])
  const value = graph([node("a"), node("b")], [{ ...edge("a", "b"), condition: { path: ["var", "source_file"], value_type: "file", value: "arbitrary-id", operator: "eq", unit: null } }])
  assert.equal(workflowDataProblem(value, [{ id: "protocol-1", versions: [{ id: "version-1", fields: [fileField()] }] }]), "invalidCondition")
})
test("Protocol file binding requires graph v4 and explicit safe metadata, not hidden string initial values", () => {
  const value = graph([node("a"), node("b")], [edge("a", "b")])
  value.bindings = [binding({ source_path: ["var", "source_file"], target_path: ["var", "source_file"], value_type: "file", unit: null })]
  const fields = [{ id: "protocol-1", versions: [{ id: "version-1", fields: [fileField()] }] }]
  assert.equal(workflowGraphProblem(value), "incomplete")
  value.schema_version = 4
  assert.equal(workflowGraphProblem(value), null)
  assert.equal(workflowDataProblem(value, fields), null)
  value.nodes[1].initial_values.source_file = "manual-existing-file"
  assert.equal(workflowDataProblem(value, fields), "invalidBinding")
})
test("Compute file ports reference declared mount names only and change the output catalog identity", () => {
  const value = computeGraph()
  const oldKey = workflowAnalysisOutputKey(value.nodes[1])
  const port = createWorkflowComputeFileOutput("data_file", { mount_name: "data.csv", title: "Synthetic output", source_file_id: "private", download_url: "private://source", file_extensions: ["csv"] })
  assert.deepEqual(port, { output_id: "data_file", mount_name: "data.csv" })
  value.nodes[1].compute_file_outputs = [port]
  assert.notEqual(workflowAnalysisOutputKey(value.nodes[1]), oldKey)
  assert.equal(workflowGraphProblem(value), "incomplete")
  value.schema_version = 4
  assert.equal(workflowGraphProblem(value), null)
  assert.equal(normalizeWorkflowGraph(computeGraph()).schema_version, 3)
})
