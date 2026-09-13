<template>
  <section v-if="graph.edges.length || graph.bindings.length || analysisNodes.length" class="workflow-data-summary" data-testid="workflow-data-summary">
    <article v-for="node in analysisNodes" :key="node.node_id" class="mb-4" data-testid="workflow-analysis-summary">
      <h4 class="aira-type-label">
        {{ node.title }} · {{ $t('page.workflowAnalysis.analysisCard') }}
      </h4>
      <p>{{ $t('page.workflowAnalysis.methodSnapshot') }}: {{ method(node.method_publication_id)?.title ?? node.method_publication_id }}</p>
      <p class="aira-type-meta">
        {{ $t('page.workflowAnalysis.snapshotDigest') }}: {{ method(node.method_publication_id)?.digest ?? '—' }}
      </p>
      <p>{{ $t('page.workflowAnalysis.selectedSources') }}: {{ node.record_sources.map(source => nodeTitle(source.source_node_id)).join(' · ') }}</p>
      <n-alert type="info" class="mb-3">
        {{ $t('page.workflowAnalysis.pendingRecords') }}
      </n-alert>
      <ul v-if="node.analysis_kind === 'compute'">
        <li v-for="output in node.compute_outputs" :key="output.output_id">
          {{ output.output_id }}: {{ workflowPathLabel(output.path) }} · {{ $t(`page.workflowDefinitions.fieldTypes.${output.value_type}`) }} · {{ output.unit || '—' }}
        </li>
        <li v-for="output in node.compute_file_outputs ?? []" :key="output.output_id">
          {{ output.output_id }}: {{ output.mount_name }} · {{ $t('page.workflowDefinitions.fieldTypes.file') }}
        </li>
      </ul>
      <ul v-else>
        <li v-for="output in node.analysis_outputs" :key="output.output_id">
          {{ output.output_id }}: {{ output.field }} · {{ $t(`page.analysis.statistics.${output.statistic}`) }} · {{ JSON.stringify(output.group) }}
        </li>
      </ul>
      <workflow-method-summary v-if="method(node.method_publication_id)?.compute_contract" :method="method(node.method_publication_id)!" />
      <details v-if="method(node.method_publication_id)">
        <summary>{{ $t('page.workflowAnalysis.recipe') }}</summary>
        <pre class="analysis-recipe" tabindex="0">{{ JSON.stringify(method(node.method_publication_id)?.recipe, null, 2) }}</pre>
      </details>
    </article>
    <h4 class="aira-type-label mb-2">
      {{ $t("page.workflowDefinitions.conditions.previewTitle") }}
    </h4>
    <ol class="workflow-summary-list">
      <li v-for="edge in graph.edges" :key="edge.edge_id">
        <strong>{{ nodeTitle(edge.source_node_id) }} → {{ nodeTitle(edge.target_node_id) }}</strong>
        <div class="mt-1">
          {{ edge.condition ? workflowConditionText(edge.condition) : $t("page.workflowDefinitions.conditions.always") }}
        </div>
      </li>
    </ol>
    <template v-if="graph.bindings.length">
      <h4 class="aira-type-label mb-2">
        {{ $t("page.workflowDefinitions.bindings.title") }}
      </h4>
      <ol class="workflow-summary-list">
        <li v-for="binding in graph.bindings" :key="binding.binding_id">
          <strong>{{ nodeTitle(binding.source_node_id) }}</strong> {{ workflowPathLabel(binding.source_path) }}
          → <strong>{{ nodeTitle(binding.target_node_id) }}</strong> {{ workflowPathLabel(binding.target_path) }}
          <div class="aira-type-meta aira-text-secondary mt-1">
            {{ $t(`page.workflowDefinitions.fieldTypes.${binding.value_type}`) }}<template v-if="binding.unit">
              · {{ binding.unit }}
            </template>
            · {{ $t(binding.value_type === 'file' ? 'page.workflowFiles.oneFile' : 'page.workflowDefinitions.bindings.oneValue') }}
          </div>
          <p v-if="binding.value_type === 'file'" class="aira-type-meta my-1">
            {{ fileDescription(binding.source_node_id, binding.source_path) }} → {{ fileDescription(binding.target_node_id, binding.target_path) }}
          </p>
        </li>
      </ol>
      <n-alert type="info" class="mt-3">
        {{ $t("page.workflowDefinitions.bindings.approvalHint") }}
      </n-alert>
      <n-alert v-if="graph.bindings.some(binding => binding.value_type === 'file')" type="warning" class="mt-3" data-testid="workflow-file-binding-preview">
        {{ $t('page.workflowFiles.previewHint') }}
      </n-alert>
    </template>
  </section>
</template>

<script setup lang="ts">
import type { WorkflowAnalysisPublication } from "@/service/api/workflow-analysis-methods"
import type { WorkflowField, WorkflowGraph } from "@/service/api/workflow-definitions"
import { workflowConditionText, workflowPathLabel } from "@/utils/workflow-editor"
import { computed } from "vue"
import WorkflowMethodSummary from "./workflow-method-summary.vue"

const props = defineProps<{ graph: Pick<WorkflowGraph, "nodes" | "edges" | "bindings">, methods?: WorkflowAnalysisPublication[], fieldCatalog?: Record<string, WorkflowField[]> }>()
function fileDescription(nodeId: string, path: string[]) {
  const field = props.fieldCatalog?.[nodeId]?.find(field => JSON.stringify(field.path) === JSON.stringify(path))
  return `${field?.title || workflowPathLabel(path)} (${field?.value_type === "file" ? field.file_extensions?.join(", ") || "*" : "—"})`
}
const analysisNodes = computed(() => props.graph.nodes.filter(node => node.kind === "analysis"))
function method(id: string) {
  return props.methods?.find(method => method.id === id)
}
function nodeTitle(id: string) {
  return props.graph.nodes.find(node => node.node_id === id)?.title ?? id
}
</script>

<style scoped>
.workflow-data-summary { margin-top: 16px; padding-top: 6px; border-top: 1px solid #e2e8f0; overflow-wrap: anywhere; }
.workflow-summary-list { padding-inline-start: 22px; }
.workflow-summary-list li { margin-bottom: 14px; }
.analysis-recipe { max-height: 20rem; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
