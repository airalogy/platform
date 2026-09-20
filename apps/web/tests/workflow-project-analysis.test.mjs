/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { readFileSync } from "node:fs"
import test from "node:test"
import ts from "typescript"

async function loadUtility(filename) {
  const source = readFileSync(new URL(`../src/utils/${filename}.ts`, import.meta.url), "utf8")
  const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext }, reportDiagnostics: true })
  assert.deepEqual(compiled.diagnostics, [])
  return import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString("base64")}`)
}
const { projectMethodPublicationInputs, workflowProjectSourceOptions, replaceWorkflowProjectSources, workflowProjectOutputRecipe, workflowProjectOutputFields, workflowProjectOutputValid } = await loadUtility("workflow-project-analysis")
const { addWorkflowAssetInput, createWorkflowAnalysisNode, duplicateWorkflowNode, removeWorkflowNode, replaceWorkflowAnalysisMethod, taskSupportsWorkflow, workflowAnalysisProblem, workflowGraphProblem, workflowAnalysisOutputKey, normalizeWorkflowGraph } = await loadUtility("workflow-editor")

const statistics = { schema_version: 1, numeric_fields: ["signal"], group_by: ["condition"], filters: [], missing_policy: "exclude", chart: "none" }
const fields = [{ key: "signal", title: "Signal", type: "number", unit: "mV" }, { key: "condition", title: "Condition", type: ["string", "null"], unit: null }]
function version(id, number) {
  return {
    id,
    version: number,
    schema_digest: `schema-${id}`,
    json_schema: { type: "object", properties: { signal: { type: "number", title: "Signal", unit: "mV" }, condition: { anyOf: [{ type: "string" }, { type: "null" }], title: "Condition" } } },
    fields: {},
  }
}
function method() {
  return {
    id: "project-method",
    title: "Two source method",
    project_id: "project",
    protocol_id: null,
    protocol_version_id: null,
    input_fields: [],
    compute_contract: {},
    engine_version: "airalogy.project-analysis.v1",
    recipe: { kind: "project", schema_version: 1, mode: "relational", slots: [{ slot_id: "left", label: "Assay", recipe: structuredClone(statistics) }, { slot_id: "right", label: "Validation", recipe: structuredClone(statistics) }], join: { outputs: [{ slot_id: "right", output_id: "validation", semantic_label: "Validation result", field: "signal", unit: "mV" }], recipe: { ...statistics, numeric_fields: ["validation"], group_by: [] } } },
    project_contract: { schema_version: 1, slots: [{ slot_id: "left", label: "Assay", protocol_id: "protocol-a", versions: [version("a1", "0.0.1"), version("a2", "0.0.2")] }, { slot_id: "right", label: "Validation", protocol_id: "protocol-b", versions: [version("b1", "0.0.1")] }] },
    project_input_fields: { left: structuredClone(fields), right: structuredClone(fields) },
  }
}
function protocol(id, protocolId, versionId) {
  return { node_id: id, kind: "protocol", protocol_id: protocolId, protocol_version_id: versionId, title: id, position: { x: 0, y: 0 }, initial_values: {} }
}
function fixture() {
  const publication = method()
  const analysis = createWorkflowAnalysisNode(publication, "analysis", { x: 0, y: 0 })
  analysis.record_sources = [{ slot_id: "left", source_node_id: "a", cardinality: "one" }, { slot_id: "left", source_node_id: "a-repeat", cardinality: "one" }, { slot_id: "right", source_node_id: "b", cardinality: "one" }]
  const graph = { schema_version: 6, nodes: [protocol("a", "protocol-a", "a1"), protocol("a-repeat", "protocol-a", "a1"), protocol("b", "protocol-b", "b1"), analysis], edges: ["a", "a-repeat", "b"].map(id => ({ edge_id: `${id}-analysis`, source_node_id: id, target_node_id: "analysis", condition: null })), bindings: [] }
  return { publication, analysis, graph }
}

test("Project publication requires explicit complete distinct slots and never copies historical selections", () => {
  const recipe = method().recipe
  assert.equal(projectMethodPublicationInputs(recipe, { left: "a", right: "b" }, { left: ["v1"], right: [] }), null)
  assert.equal(projectMethodPublicationInputs(recipe, { left: "a", right: "a" }, { left: ["v1"], right: ["v1"] }), null)
  const result = projectMethodPublicationInputs(recipe, { left: "a", right: "b", stale: "secret" }, { left: ["v2", "v1", "v2"], right: ["v3"], stale: ["private"] })
  assert.deepEqual(result, [{ slot_id: "left", protocol_id: "a", protocol_version_ids: ["v1", "v2"] }, { slot_id: "right", protocol_id: "b", protocol_version_ids: ["v3"] }])
  assert.equal(JSON.stringify(result).includes("private"), false)
})

test("schema 6 Project cards have only explicit Project ports and retain legacy graph serialization", () => {
  const { analysis, graph } = fixture()
  assert.equal(analysis.analysis_kind, "project")
  assert.deepEqual(analysis.project_outputs, [])
  assert.equal(Object.hasOwn(analysis, "analysis_outputs"), false)
  assert.equal(Object.hasOwn(analysis, "compute_outputs"), false)
  assert.equal(workflowGraphProblem(graph), null)
  assert.equal(workflowGraphProblem({ ...graph, schema_version: 5 }), "incomplete")
  assert.equal(addWorkflowAssetInput(graph, "Reagent input").schema_version, 6)
  for (const version of [1, 2, 3, 4, 5]) {
    const old = { schema_version: version, nodes: [protocol("a", "protocol-a", "a1")], edges: [], bindings: [] }
    assert.equal(JSON.stringify(normalizeWorkflowGraph(old)), JSON.stringify(old))
  }
})

test("multiple nodes per slot use explicit allowed versions and cannot share one node across slots", () => {
  const { analysis, publication, graph } = fixture()
  assert.equal(workflowAnalysisProblem(graph, [publication]), null)
  assert.deepEqual(workflowProjectSourceOptions(graph, analysis, publication, "left").map(option => option.value), ["a", "a-repeat"])
  const stale = structuredClone(graph)
  stale.nodes[0].protocol_version_id = "a3"
  assert.deepEqual(workflowProjectSourceOptions(stale, analysis, publication, "left").map(option => option.value), ["a-repeat"])
  assert.equal(workflowAnalysisProblem(stale, [publication]), "invalidAnalysis")
  analysis.record_sources.push({ slot_id: "right", source_node_id: "a", cardinality: "one" })
  assert.equal(workflowAnalysisProblem(graph, [publication]), "invalidAnalysis")
  analysis.record_sources.pop()
  const next = replaceWorkflowProjectSources(analysis, "right", ["a", "b", "b"])
  assert.deepEqual(next, analysis.record_sources)
  graph.edges = graph.edges.filter(edge => edge.source_node_id !== "b")
  assert.equal(workflowAnalysisProblem(graph, [publication]), "invalidAnalysis")
})

test("task pins need only actual upstream versions, not unused allowed version alternatives", () => {
  const { graph, publication } = fixture()
  const task = { protocols: [{ id: "protocol-a", version_id: "a1" }, { id: "protocol-b", version_id: "b1" }] }
  assert.equal(taskSupportsWorkflow(task, graph, [publication]), true)
  assert.equal(taskSupportsWorkflow({ protocols: task.protocols.slice(0, 1) }, graph, [publication]), false)
})

test("local and join ports resolve by literal slot IDs and field names, not recipe order", () => {
  const publication = method()
  const local = { output_id: "mean_signal", source: { kind: "local", slot_id: "left" }, field: "signal", statistic: "mean", group: { condition: "treated" } }
  const joined = { output_id: "mean_validation", source: { kind: "join" }, field: "validation", statistic: "mean", group: {} }
  assert.equal(workflowProjectOutputValid(publication, local, []), true)
  assert.equal(workflowProjectOutputValid(publication, joined, []), true)
  publication.recipe.slots.reverse()
  assert.deepEqual(workflowProjectOutputRecipe(publication, local.source), statistics)
  assert.equal(workflowProjectOutputFields(publication, joined.source)[0].key, "validation")
  assert.equal(workflowProjectOutputFields(publication, joined.source)[0].unit, "mV")
  for (const invalid of [{ ...local, group: {} }, { ...local, source: { kind: "local", slot_id: "0" } }, { ...joined, field: "signal" }, { ...local, group: { condition: ["treated"] } }, { ...local, group: { condition: Number.NaN } }])
    assert.equal(workflowProjectOutputValid(publication, invalid, []), false)
  assert.equal(workflowProjectOutputValid(publication, local, [local]), false)
  const node = createWorkflowAnalysisNode(publication, "a", { x: 0, y: 0 })
  const before = workflowAnalysisOutputKey(node)
  node.project_outputs.push(local)
  assert.notEqual(workflowAnalysisOutputKey(node), before)
  node.project_outputs[0].source = { kind: "join" }
  assert.notEqual(workflowAnalysisOutputKey(node), before)
})

test("raw ProtocolVersion fields dictionaries never replace server-derived slot field catalogs", () => {
  const publication = method()
  const local = { output_id: "mean_signal", source: { kind: "local", slot_id: "left" }, field: "signal", statistic: "mean", group: { condition: "treated" } }
  const joined = { output_id: "mean_validation", source: { kind: "join" }, field: "validation", statistic: "mean", group: {} }
  const before = JSON.stringify(publication.project_contract)
  assert.equal(Array.isArray(publication.project_contract.slots[0].versions[0].fields), false)
  assert.deepEqual(workflowProjectOutputFields(publication, local.source), fields)
  assert.deepEqual(workflowProjectOutputFields(publication, local.source).find(field => field.key === "condition").type, ["string", "null"])
  assert.equal(workflowProjectOutputValid(publication, local, []), true)
  assert.equal(workflowProjectOutputValid(publication, joined, []), true)
  assert.equal(JSON.stringify(publication.project_contract), before)

  delete publication.project_input_fields
  assert.deepEqual(workflowProjectOutputFields(publication, local.source), [])
  assert.deepEqual(workflowProjectOutputFields(publication, joined.source), [])
  assert.equal(workflowProjectOutputValid(publication, local, []), false)
  assert.equal(workflowProjectOutputValid(publication, joined, []), false)
  publication.project_input_fields = { left: { signal: { type: "number" } } }
  assert.deepEqual(workflowProjectOutputFields(publication, local.source), [])
})

test("clone, upstream deletion and method switching do not retain stale source or output bindings", () => {
  const { analysis, publication, graph } = fixture()
  assert.deepEqual(duplicateWorkflowNode(analysis, "copy").record_sources, [])
  const removed = removeWorkflowNode(graph, "a")
  assert.equal(removed.nodes.at(-1).record_sources.some(source => source.source_node_id === "a"), false)
  graph.bindings.push({ source_node_id: "analysis", target_node_id: "b", source_path: ["analysis", "old"] })
  graph.edges.push({ edge_id: "conditional", source_node_id: "analysis", target_node_id: "b", condition: { path: ["analysis", "old"] } })
  assert.equal(replaceWorkflowAnalysisMethod(graph, "analysis", { ...publication, id: "new-method" }), graph)
  graph.edges.pop()
  const switched = replaceWorkflowAnalysisMethod(graph, "analysis", { ...publication, id: "new-method" })
  assert.deepEqual(switched.nodes.at(-1).record_sources, [])
  assert.deepEqual(switched.nodes.at(-1).project_outputs, [])
  assert.deepEqual(switched.bindings, [])
  assert.equal(switched.edges.some(edge => edge.edge_id === "conditional"), false)
  assert.equal(switched.edges.length, 3)
  assert.equal(graph.bindings.length, 1)
})

test("Project Workflow disclosure, slot selection and safety messages have matching English and Chinese translations", () => {
  const en = JSON.parse(readFileSync(new URL("../../../packages/shared/src/locales/langs/en-us.json", import.meta.url), "utf8")).page.workflowProjectAnalysis
  const zh = JSON.parse(readFileSync(new URL("../../../packages/shared/src/locales/langs/zh-cn.json", import.meta.url), "utf8")).page.workflowProjectAnalysis
  assert.deepEqual(Object.keys(en).sort(), Object.keys(zh).sort())
  for (const key of ["publicationHint", "allowedVersions", "excluded", "sourcesHint", "outputsHint", "outputSource", "localResult", "joinResult", "inputPreview", "methodChangeBlocked", "methodChanged"])
    assert.ok(en[key]?.trim() && zh[key]?.trim(), key)
})
