import type { AnalysisRecipe } from "@/service/api/analysis"
import type { ProjectAnalysisRecipe } from "@/service/api/project-analysis"
import type { WorkflowAnalysisPublication, WorkflowAnalysisPublicationRequest, WorkflowProjectOutput } from "@/service/api/workflow-analysis-methods"
import type { WorkflowGraph, WorkflowProjectAnalysisNode } from "@/service/api/workflow-definitions"

/** Construct only the approved schema pins; saved questions and Record selections never leave the private method. */
export function projectMethodPublicationInputs(recipe: ProjectAnalysisRecipe, protocols: Record<string, string | null>, versions: Record<string, string[]>): NonNullable<WorkflowAnalysisPublicationRequest["project_inputs"]> | null {
  if (!recipe.slots.length || new Set(recipe.slots.map(slot => protocols[slot.slot_id])).size !== recipe.slots.length || recipe.slots.some(slot => !protocols[slot.slot_id] || !versions[slot.slot_id]?.length))
    return null
  return recipe.slots.map(slot => ({ slot_id: slot.slot_id, protocol_id: protocols[slot.slot_id]!, protocol_version_ids: [...new Set(versions[slot.slot_id])].sort() }))
}

export function workflowProjectSourceOptions(graph: WorkflowGraph, node: WorkflowProjectAnalysisNode, method: WorkflowAnalysisPublication | undefined, slotId: string) {
  const slot = method?.project_contract?.slots.find(slot => slot.slot_id === slotId)
  return graph.nodes.filter(upstream => upstream.kind === "protocol" && upstream.protocol_id === slot?.protocol_id
    && slot.versions.some(version => version.id === upstream.protocol_version_id)
    && graph.edges.some(edge => edge.source_node_id === upstream.node_id && edge.target_node_id === node.node_id))
    .map(upstream => ({ label: upstream.title, value: upstream.node_id, disabled: node.record_sources.some(source => source.source_node_id === upstream.node_id && source.slot_id !== slotId) }))
}

/** Replace one explicit slot only; array ordering is never a source address. */
export function replaceWorkflowProjectSources(node: WorkflowProjectAnalysisNode, slotId: string, ids: string[]): WorkflowProjectAnalysisNode["record_sources"] {
  const others = node.record_sources.filter(source => source.slot_id !== slotId)
  return [...others, ...[...new Set(ids)].filter(id => !others.some(source => source.source_node_id === id)).map(source_node_id => ({ slot_id: slotId, source_node_id, cardinality: "one" as const }))]
}

export function workflowProjectOutputRecipe(method: WorkflowAnalysisPublication | undefined, source: WorkflowProjectOutput["source"]): AnalysisRecipe | null {
  const recipe = method?.recipe
  if (!recipe || !("kind" in recipe) || recipe.kind !== "project")
    return null
  return source.kind === "join" ? recipe.join?.recipe ?? null : recipe.slots.find(slot => slot.slot_id === source.slot_id)?.recipe ?? null
}

export function workflowProjectOutputFields(method: WorkflowAnalysisPublication | undefined, source: WorkflowProjectOutput["source"]): WorkflowAnalysisPublication["input_fields"] {
  const recipe = method?.recipe
  if (!recipe || !("kind" in recipe) || recipe.kind !== "project")
    return []
  // Version.fields is raw AIMD metadata, not a field catalog. Only the server
  // interprets schemas and intersects compatible fields across allowed versions.
  const fieldsForSlot = (slotId: string) => {
    const fields = method?.project_input_fields?.[slotId]
    return Array.isArray(fields) ? fields : []
  }
  if (source.kind === "local")
    return fieldsForSlot(source.slot_id)
  return (recipe.join?.outputs ?? []).flatMap((output) => {
    const field = fieldsForSlot(output.slot_id).find(field => field.key === output.field)
    return field ? [{ ...field, key: output.output_id, title: output.semantic_label, unit: output.unit }] : []
  })
}

/** A full group tuple and literal slot/join address are required; never use a report's array index. */
export function workflowProjectOutputValid(method: WorkflowAnalysisPublication | undefined, output: WorkflowProjectOutput, existing: WorkflowProjectOutput[]): boolean {
  const recipe = workflowProjectOutputRecipe(method, output.source)
  const fields = workflowProjectOutputFields(method, output.source)
  return !!recipe && /^[a-z][a-z0-9_-]{0,63}$/.test(output.output_id) && !existing.some(item => item.output_id === output.output_id)
    && recipe.numeric_fields.includes(output.field) && fields.some(field => field.key === output.field)
    && ["count", "missing", "invalid", "mean", "median", "min", "max", "sum", "sample_stddev"].includes(output.statistic)
    && Object.keys(output.group).length === recipe.group_by.length && recipe.group_by.every(key => Object.hasOwn(output.group, key) && fields.some(field => field.key === key))
    && Object.values(output.group).every(value => value === null || typeof value === "string" || typeof value === "boolean" || (typeof value === "number" && Number.isFinite(value)))
}
