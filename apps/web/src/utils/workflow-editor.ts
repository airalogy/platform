import type { WorkflowAnalysisPublication, WorkflowComputeFileField, WorkflowComputeFileOutput, WorkflowComputeOutput } from "@/service/api/workflow-analysis-methods"
import type { WorkflowAnalysisNode, WorkflowAssetBinding, WorkflowAssetVersion, WorkflowCondition, WorkflowContext, WorkflowField, WorkflowGraph, WorkflowNode, WorkflowScalarField, WorkflowScalarType, WorkflowTaskContext } from "@/service/api/workflow-definitions"

function isComputeAnalysisRecipe(recipe: WorkflowAnalysisPublication["recipe"]): recipe is Extract<WorkflowAnalysisPublication["recipe"], { kind: "compute" }> {
  return "kind" in recipe && recipe.kind === "compute"
}

export function isWorkflowProjectRecipe(recipe: WorkflowAnalysisPublication["recipe"]): recipe is Extract<WorkflowAnalysisPublication["recipe"], { kind: "project" }> {
  return "kind" in recipe && recipe.kind === "project"
}

export function workflowAnalysisSchemaVersion(node: WorkflowAnalysisNode): 2 | 3 | 6 {
  return node.analysis_kind === "project" ? 6 : node.analysis_kind === "compute" ? 3 : 2
}

export function createWorkflowId() {
  // getRandomValues works on HTTP-only private Lab deployments as well.
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 0x0F) | 0x40
  bytes[8] = (bytes[8] & 0x3F) | 0x80
  const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join("")
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

export function normalizeWorkflowGraph(graph: WorkflowGraph): WorkflowGraph {
  const copy: WorkflowGraph = JSON.parse(JSON.stringify(graph))
  copy.nodes = copy.nodes.map((node, index) => ({ ...node, position: node.position ?? { x: 40 + index % 3 * 310, y: 40 + Math.floor(index / 3) * 150 } }))
  return copy
}

export function emptyWorkflowGraph(): WorkflowGraph {
  return { schema_version: 1, nodes: [], edges: [], bindings: [] }
}

/** UI convenience validation only. The API remains authoritative for execution. */
export function workflowGraphProblem(graph: WorkflowGraph): "empty" | "incomplete" | "invalidEdge" | "cycle" | null {
  if (!graph.nodes.length)
    return "empty"
  if (graph.schema_version < 5 && (Object.hasOwn(graph, "asset_inputs") || Object.hasOwn(graph, "asset_bindings")))
    return "incomplete"
  if (graph.schema_version < 4 && (graph.bindings.some(binding => binding.value_type === "file") || graph.nodes.some(node => node.kind === "analysis" && node.analysis_kind === "compute" && node.compute_file_outputs?.length)))
    return "incomplete"
  const ids = new Set(graph.nodes.map(node => node.node_id))
  if (ids.size !== graph.nodes.length || graph.nodes.some(node => !node.node_id || !node.title.trim() || (node.kind === "protocol" ? !node.protocol_id || !node.protocol_version_id : !node.method_publication_id || graph.schema_version < workflowAnalysisSchemaVersion(node))))
    return "incomplete"
  const incoming = new Map(graph.nodes.map(node => [node.node_id, 0]))
  const outgoing = new Map(graph.nodes.map(node => [node.node_id, [] as string[]]))
  const pairs = new Set<string>()
  for (const edge of graph.edges) {
    const pair = JSON.stringify([edge.source_node_id, edge.target_node_id])
    if (!ids.has(edge.source_node_id) || !ids.has(edge.target_node_id) || pairs.has(pair) || edge.source_node_id === edge.target_node_id)
      return "invalidEdge"
    pairs.add(pair)
    incoming.set(edge.target_node_id, incoming.get(edge.target_node_id)! + 1)
    outgoing.get(edge.source_node_id)!.push(edge.target_node_id)
  }
  const ready = [...incoming].filter(([, count]) => count === 0).map(([id]) => id)
  let visited = 0
  for (let index = 0; index < ready.length; index++) {
    visited++
    for (const target of outgoing.get(ready[index])!) {
      incoming.set(target, incoming.get(target)! - 1)
      if (!incoming.get(target))
        ready.push(target)
    }
  }
  return visited === graph.nodes.length ? null : "cycle"
}

export function removeWorkflowNode(graph: WorkflowGraph, nodeId: string): WorkflowGraph {
  return { ...graph, nodes: graph.nodes.filter(node => node.node_id !== nodeId).map(node => node.kind === "analysis" ? { ...node, record_sources: node.record_sources.filter(source => source.source_node_id !== nodeId) } : node), edges: graph.edges.filter(edge => edge.source_node_id !== nodeId && edge.target_node_id !== nodeId), bindings: graph.bindings.filter(binding => binding.source_node_id !== nodeId && binding.target_node_id !== nodeId), ...(graph.asset_bindings ? { asset_bindings: graph.asset_bindings.filter(binding => binding.target_node_id !== nodeId) } : {}) }
}

/** New resource inputs upgrade only the edited graph; old revisions retain their exact shape. */
export function addWorkflowAssetInput(graph: WorkflowGraph, label: string): WorkflowGraph {
  const inputs = graph.asset_inputs ?? []
  let index = 1
  while (inputs.some(input => input.input_id === `asset_${index}`))
    index += 1
  return { ...graph, schema_version: graph.schema_version < 5 ? 5 : graph.schema_version, asset_inputs: [...inputs, { input_id: `asset_${index}`, label }], asset_bindings: graph.asset_bindings ?? [] }
}

export function removeWorkflowAssetInput(graph: WorkflowGraph, inputId: string): WorkflowGraph {
  return { ...graph, asset_inputs: graph.asset_inputs?.filter(input => input.input_id !== inputId), asset_bindings: graph.asset_bindings?.filter(binding => binding.input_id !== inputId) }
}

/** Only a declaration: source bytes and actual JSON values are validated by the API. */
export function workflowAssetSourceField(binding: Pick<WorkflowAssetBinding, "source_path" | "value_type" | "unit">): WorkflowField {
  const common = { path: binding.source_path, title: workflowPathLabel(binding.source_path), nullable: false }
  return binding.value_type === "file" ? { ...common, value_type: "file", unit: null, file_extensions: null } : { ...common, value_type: binding.value_type, unit: binding.unit }
}

export function workflowAssetVersionCompatible(version: WorkflowAssetVersion, bindings: WorkflowAssetBinding[], protocols: WorkflowContext["protocols"], graph: WorkflowGraph): boolean {
  return bindings.length > 0 && bindings.every((binding) => {
    const field = version.fields.find(field => workflowPathKey(field.path) === workflowPathKey(binding.source_path))
    const target = workflowFields(graph.nodes.find(node => node.node_id === binding.target_node_id), protocols).find(field => workflowPathKey(field.path) === workflowPathKey(binding.target_path))
    return field && target && field.value_type === binding.value_type && (field.unit ?? null) === binding.unit && workflowFieldsCompatible(field, target)
  })
}

export interface WorkflowAssetPageState {
  items: WorkflowAssetVersion[]
  nextOffset: number | null
}

/** Fetch exactly one page; errors leave the current cursor and choices retriable. */
export async function loadWorkflowAssetPage(state: WorkflowAssetPageState, fetchPage: (offset: number) => Promise<{ items: WorkflowAssetVersion[], next_offset: number | null }>): Promise<WorkflowAssetPageState> {
  const offset = state.nextOffset
  if (offset === null)
    return state
  const page = await fetchPage(offset)
  if (page.next_offset !== null && (!Number.isSafeInteger(page.next_offset) || page.next_offset <= offset))
    throw new Error("Invalid data asset version pagination cursor")
  const seen = new Set(state.items.map(item => item.version_id))
  const additions = page.items.filter((item) => {
    if (seen.has(item.version_id))
      return false
    seen.add(item.version_id)
    return true
  })
  return { items: [...state.items, ...additions], nextOffset: page.next_offset }
}

export function workflowFields(node: WorkflowNode | undefined, protocols: WorkflowContext["protocols"], analysisFields: Record<string, WorkflowField[]> = {}): WorkflowField[] {
  if (node?.kind === "analysis")
    return analysisFields[node.node_id] ?? []
  return protocols.find(protocol => protocol.id === node?.protocol_id)?.versions.find(version => version.id === node?.protocol_version_id)?.fields ?? []
}

export function workflowAnalysisOutputKey(node: WorkflowAnalysisNode) {
  return JSON.stringify([node.method_publication_id, node.analysis_kind === "project" ? node.project_outputs : node.analysis_kind === "compute" ? node.compute_outputs : node.analysis_outputs, ...(node.analysis_kind === "compute" && node.compute_file_outputs?.length ? [node.compute_file_outputs] : [])])
}

/** Preserve backend-authored literal path segments; never infer ports from code or old results. */
export function createWorkflowComputeOutput(outputId: string, field: WorkflowScalarField): WorkflowComputeOutput {
  return { output_id: outputId, path: [...field.path], value_type: field.value_type, unit: field.unit, nullable: field.nullable }
}
export function createWorkflowComputeFileOutput(outputId: string, file: WorkflowComputeFileField): WorkflowComputeFileOutput {
  return { output_id: outputId, mount_name: file.mount_name }
}

/** A card references an explicitly published snapshot, never copies the private method or its inputs. */
export function createWorkflowAnalysisNode(method: WorkflowAnalysisPublication, nodeId: string, position: { x: number, y: number }): WorkflowAnalysisNode {
  if (isWorkflowProjectRecipe(method.recipe))
    return { node_id: nodeId, kind: "analysis", analysis_kind: "project", method_publication_id: method.id, record_sources: [], input_policy: "all_declared", project_outputs: [], title: method.title, position: { ...position } }
  if (isComputeAnalysisRecipe(method.recipe))
    return { node_id: nodeId, kind: "analysis", analysis_kind: "compute", method_publication_id: method.id, record_sources: [], input_policy: "all_declared", compute_outputs: [], title: method.title, position: { ...position } }
  return { node_id: nodeId, kind: "analysis", method_publication_id: method.id, record_sources: [], input_policy: "all_declared", analysis_outputs: [], title: method.title, position: { ...position } }
}

/** Remove dependent conditions explicitly before switching; never silently make a guarded branch unconditional. */
export function replaceWorkflowAnalysisMethod(graph: WorkflowGraph, nodeId: string, method: WorkflowAnalysisPublication): WorkflowGraph {
  const previous = graph.nodes.find(node => node.node_id === nodeId)
  if (previous?.kind !== "analysis" || previous.method_publication_id === method.id || graph.edges.some(edge => edge.source_node_id === nodeId && edge.condition))
    return graph
  const replacement = { ...createWorkflowAnalysisNode(method, previous.node_id, previous.position), title: previous.title }
  const minimum = workflowAnalysisSchemaVersion(replacement)
  return { ...graph, schema_version: graph.schema_version < minimum ? minimum : graph.schema_version, nodes: graph.nodes.map(node => node.node_id === nodeId ? replacement : node), bindings: graph.bindings.filter(binding => binding.source_node_id !== nodeId) }
}

export function workflowAnalysisProblem(graph: WorkflowGraph, methods: WorkflowAnalysisPublication[]): "invalidAnalysis" | null {
  for (const node of graph.nodes) {
    if (node.kind !== "analysis")
      continue
    const method = methods.find(method => method.id === node.method_publication_id)
    if (!method || (node.analysis_kind === "project") !== isWorkflowProjectRecipe(method.recipe) || (node.analysis_kind === "compute") !== isComputeAnalysisRecipe(method.recipe) || (node.analysis_kind === "compute" && !method.compute_contract) || node.input_policy !== "all_declared" || !node.record_sources.length)
      return "invalidAnalysis"
    if (node.analysis_kind === "project" && (!method.project_contract?.slots.length || method.project_contract.slots.some(slot => !node.record_sources.some(source => source.slot_id === slot.slot_id))))
      return "invalidAnalysis"
    const sources = new Set<string>()
    for (const source of node.record_sources) {
      const upstream = graph.nodes.find(item => item.node_id === source.source_node_id)
      const slot = node.analysis_kind === "project" ? method.project_contract?.slots.find(slot => slot.slot_id === source.slot_id) : undefined
      const sourceKey = source.source_node_id
      if (source.cardinality !== "one" || sources.has(sourceKey) || upstream?.kind !== "protocol"
        || (node.analysis_kind === "project" ? !slot || upstream.protocol_id !== slot.protocol_id || !slot.versions.some(version => version.id === upstream.protocol_version_id) : source.slot_id !== undefined || upstream.protocol_id !== method.protocol_id)
        || !graph.edges.some(edge => edge.source_node_id === source.source_node_id && edge.target_node_id === node.node_id)) {
        return "invalidAnalysis"
      }
      sources.add(sourceKey)
    }
  }
  return null
}

export function workflowPathKey(path: string[]) {
  return JSON.stringify(path)
}

export function workflowPathLabel(path: string[]) {
  return path.map(segment => JSON.stringify(segment)).join(" / ")
}

export function parseWorkflowScalar(text: string, type: WorkflowScalarType): string | number | boolean {
  if (type === "string")
    return text
  if (type === "boolean") {
    if (text !== "true" && text !== "false")
      throw new Error("invalid_boolean")
    return text === "true"
  }
  if (!text.trim() || !/^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:e[+-]?\d+)?$/i.test(text.trim()))
    throw new Error("invalid_number")
  const number = Number(text)
  const nonzeroMantissa = /[1-9]/.test(text.trim().split(/e/i)[0])
  if (!Number.isFinite(number) || (number === 0 && nonzeroMantissa) || (Number.isInteger(number) && !Number.isSafeInteger(number)) || (type === "integer" && !Number.isInteger(number)))
    throw new Error("invalid_number")
  return number
}

export function workflowConditionText(condition: WorkflowCondition) {
  const operators = { eq: "=", ne: "≠", gt: ">", gte: "≥", lt: "<", lte: "≤" }
  return `${workflowPathLabel(condition.path)} ${operators[condition.operator]} ${JSON.stringify(condition.value)}${condition.unit ? ` ${condition.unit}` : ""}`
}

export function workflowFieldsCompatible(source: WorkflowField, target: WorkflowField) {
  if (target.bindable_target === false || source.value_type !== target.value_type || (source.unit ?? null) !== (target.unit ?? null))
    return false
  if (source.value_type === "file" && target.value_type === "file" && source.file_extensions && target.file_extensions)
    return source.file_extensions.every(extension => target.file_extensions!.includes(extension))
  return true
}
export function workflowScalarFields(fields: WorkflowField[]): WorkflowScalarField[] {
  return fields.filter((field): field is WorkflowScalarField => field.value_type !== "file")
}

/** Validate selected metadata only, never evaluate conditions or copy experiment data in the browser. */
export function workflowDataProblem(graph: WorkflowGraph, protocols: WorkflowContext["protocols"], analysisFields: Record<string, WorkflowField[]> = {}): "invalidCondition" | "invalidBinding" | null {
  const fields = (id: string) => workflowFields(graph.nodes.find(node => node.node_id === id), protocols, analysisFields)
  for (const edge of graph.edges) {
    const condition = edge.condition
    if (!condition)
      continue
    const field = fields(edge.source_node_id).find(field => workflowPathKey(field.path) === workflowPathKey(condition.path))
    if (!field || field.value_type === "file" || field.value_type !== condition.value_type || (field.unit ?? null) !== (condition.unit ?? null))
      return "invalidCondition"
    if (!["eq", "ne"].includes(condition.operator) && !["number", "integer"].includes(condition.value_type))
      return "invalidCondition"
    try {
      if (parseWorkflowScalar(String(condition.value), condition.value_type) !== condition.value)
        return "invalidCondition"
    }
    catch {
      return "invalidCondition"
    }
  }
  const targets = new Set<string>()
  const bindingIds = new Set<string>()
  for (const binding of graph.bindings) {
    const targetNode = graph.nodes.find(node => node.node_id === binding.target_node_id)
    const source = fields(binding.source_node_id).find(field => workflowPathKey(field.path) === workflowPathKey(binding.source_path))
    const target = fields(binding.target_node_id).find(field => workflowPathKey(field.path) === workflowPathKey(binding.target_path))
    const key = JSON.stringify([binding.target_node_id, binding.target_path])
    if (!graph.edges.some(edge => edge.source_node_id === binding.source_node_id && edge.target_node_id === binding.target_node_id)
      || !source || !target || !workflowFieldsCompatible(source, target) || source.value_type !== binding.value_type
      || (source.unit ?? null) !== (binding.unit ?? null) || binding.cardinality !== "one" || targets.has(key) || bindingIds.has(binding.binding_id)
      || targetNode?.kind !== "protocol" || Object.hasOwn(targetNode.initial_values, binding.target_path[1])) {
      return "invalidBinding"
    }
    targets.add(key)
    bindingIds.add(binding.binding_id)
  }
  const inputs = graph.asset_inputs ?? []
  const assetBindings = graph.asset_bindings ?? []
  const inputIds = new Set(inputs.map(input => input.input_id))
  if (inputs.length > 32 || graph.bindings.length + assetBindings.length > 128 || inputIds.size !== inputs.length
    || inputs.some(input => !/^[a-z][a-z0-9_-]{0,63}$/.test(input.input_id) || !input.label.trim() || input.label.length > 255 || !assetBindings.some(binding => binding.input_id === input.input_id))) {
    return "invalidBinding"
  }
  for (const binding of assetBindings) {
    const targetNode = graph.nodes.find(node => node.node_id === binding.target_node_id)
    const target = fields(binding.target_node_id).find(field => workflowPathKey(field.path) === workflowPathKey(binding.target_path))
    const key = JSON.stringify([binding.target_node_id, binding.target_path])
    const pathValid = binding.value_type === "file"
      ? workflowPathKey(binding.source_path) === "[\"file\"]" && binding.unit === null
      : binding.source_path[0] === "json" && binding.source_path.length >= 2 && binding.source_path.length <= 17 && binding.source_path.slice(1).every(segment => typeof segment === "string" && segment.length > 0 && segment.length <= 255)
    if (graph.schema_version < 5 || !inputIds.has(binding.input_id) || !pathValid || !/^[a-z][a-z0-9_-]{0,63}$/.test(binding.binding_id)
      || (binding.unit !== null && (!["number", "integer"].includes(binding.value_type) || !binding.unit.trim() || binding.unit.trim() !== binding.unit))
      || !target || !workflowFieldsCompatible(workflowAssetSourceField(binding), target) || binding.cardinality !== "one"
      || targets.has(key) || bindingIds.has(binding.binding_id) || targetNode?.kind !== "protocol" || Object.hasOwn(targetNode.initial_values, binding.target_path[1])) {
      return "invalidBinding"
    }
    targets.add(key)
    bindingIds.add(binding.binding_id)
  }
  return null
}

/** Copies configuration, never node identity or incoming/outgoing execution dependencies. */
export function duplicateWorkflowNode(node: WorkflowNode, nodeId: string): WorkflowNode {
  const copy = { ...structuredClone(node), node_id: nodeId, position: { x: node.position.x + 48, y: node.position.y + 96 } }
  if (copy.kind === "analysis")
    copy.record_sources = []
  return copy
}

export function taskSupportsWorkflow(task: WorkflowTaskContext, graph: WorkflowGraph, methods: WorkflowAnalysisPublication[] = []): boolean {
  return graph.nodes.length > 0 && graph.nodes.every((node) => {
    const resource = node.kind === "protocol" ? node : methods.find(method => method.id === node.method_publication_id)
    if (node.kind === "analysis" && node.analysis_kind === "project") {
      const method = methods.find(method => method.id === node.method_publication_id)
      return !!method?.project_contract?.slots.length && node.record_sources.length > 0 && node.record_sources.every((source) => {
        const upstream = graph.nodes.find(item => item.node_id === source.source_node_id)
        const slot = method.project_contract?.slots.find(item => item.slot_id === source.slot_id)
        return upstream?.kind === "protocol" && slot?.protocol_id === upstream.protocol_id && slot.versions.some(version => version.id === upstream.protocol_version_id)
          && task.protocols.some(pin => pin.id === upstream.protocol_id && pin.version_id === upstream.protocol_version_id)
      })
    }
    if (!resource || !task.protocols.some(pin => pin.id === resource.protocol_id && pin.version_id === resource.protocol_version_id))
      return false
    if (node.kind === "analysis" && node.analysis_kind === "compute") {
      const method = methods.find(method => method.id === node.method_publication_id)
      if (!method || !isComputeAnalysisRecipe(method.recipe))
        return false
      const revisionId = method.recipe.environment_revision_id
      return !!task.compute?.some(environment => environment.source_revision_id === revisionId)
    }
    return true
  })
}

/** Sequence is presentation order, not an implicit execution dependency. */
export function moveWorkflowNode(graph: WorkflowGraph, nodeId: string, offset: -1 | 1): WorkflowGraph {
  const index = graph.nodes.findIndex(node => node.node_id === nodeId)
  const next = index + offset
  if (index < 0 || next < 0 || next >= graph.nodes.length)
    return graph
  const nodes = [...graph.nodes]
  ;[nodes[index], nodes[next]] = [nodes[next], nodes[index]]
  return { ...graph, nodes }
}
