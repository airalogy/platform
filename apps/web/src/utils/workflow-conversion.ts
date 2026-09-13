import type { WorkflowConversionContext, WorkflowConversionRequest } from "@/service/api/workflow-conversions"

/** Only copy a reviewed structure. Never import execution history, goals or free-text logic. */
export function createWorkflowConversionDraft(context: WorkflowConversionContext): WorkflowConversionRequest {
  return {
    project_id: context.source.project_id,
    source_digest: context.source.digest,
    title: context.source.title,
    description: "",
    nodes: context.nodes.map(node => ({
      protocol_index: node.protocol_index,
      protocol_id: node.protocol_id || "",
      protocol_version_id: node.versions.some(version => version.id === node.suggested_version_id) ? node.suggested_version_id! : "",
    })),
    edges: context.edges.filter(edge => edge.supported && edge.source_protocol_index !== null && edge.target_protocol_index !== null).map(edge => ({ source_protocol_index: edge.source_protocol_index!, target_protocol_index: edge.target_protocol_index! })),
    acknowledge_versions: false,
    acknowledge_structure_only: false,
    acknowledge_logic_omission: false,
  }
}

export function workflowConversionReady(draft: WorkflowConversionRequest, context: WorkflowConversionContext): boolean {
  return draft.project_id === context.source.project_id && draft.source_digest === context.source.digest
    && !!draft.title.trim() && draft.nodes.length === context.nodes.length && draft.nodes.length > 0
    && new Set(draft.nodes.map(node => node.protocol_index)).size === draft.nodes.length
    && !(context.blockers?.length)
    && draft.acknowledge_versions && draft.acknowledge_structure_only && draft.acknowledge_logic_omission
    && draft.nodes.every((node) => {
      const original = context.nodes.find(item => item.protocol_index === node.protocol_index)
      return !!original?.protocol_id && original.protocol_id === node.protocol_id && original.versions.some(version => version.id === node.protocol_version_id)
    })
}
