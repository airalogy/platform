<template>
  <section class="analysis-inputs" data-testid="workflow-analysis-settings">
    <n-alert type="info" class="mb-4">
      {{ t('page.workflowAnalysis.pendingRecords') }}
    </n-alert>
    <n-form label-placement="top" :disabled="disabled">
      <n-form-item :label="t('page.workflowAnalysis.recordSources')" required>
        <n-select :value="node.record_sources.map(source => source.source_node_id)" :options="sourceOptions" multiple clearable data-testid="workflow-analysis-sources" @update:value="updateSources" />
        <template #feedback>
          {{ t('page.workflowAnalysis.recordSourcesHint') }}
        </template>
      </n-form-item>
      <p v-if="!sourceOptions.length" class="aira-type-meta">
        {{ t('page.workflowAnalysis.noSources') }}
      </p>
    </n-form>
    <analysis-compute-input-declarations :inputs="computeRecipe?.input_files" workflow />
    <workflow-compute-outputs v-if="node.analysis_kind === 'compute'" :node="node" :disabled="disabled" @change="emit('computeOutputs', $event)" @files="emit('computeFiles', $event)" />
    <template v-else>
      <h4 class="aira-type-label">
        {{ t('page.workflowAnalysis.outputs') }}
      </h4>
      <p class="aira-type-meta">
        {{ t('page.workflowAnalysis.outputsHint') }}
      </p>
      <p v-if="!node.analysis_outputs.length" class="aira-type-meta">
        {{ t('page.workflowAnalysis.noOutputs') }}
      </p>
      <article v-for="output in node.analysis_outputs" :key="output.output_id" class="output-row mb-3" data-testid="workflow-analysis-output">
        <div class="min-w-0">
          <strong>{{ output.output_id }}</strong>
          <p class="aira-type-meta my-1">
            {{ output.field }} · {{ t(`page.analysis.statistics.${output.statistic}`) }}
          </p>
          <code v-if="Object.keys(output.group).length">{{ JSON.stringify(output.group) }}</code>
        </div>
        <n-button size="small" :disabled="disabled" @click="emit('outputs', node.analysis_outputs.filter(item => item.output_id !== output.output_id))">
          {{ t('common.delete') }}
        </n-button>
      </article>
      <n-form v-if="builtinRecipe" label-placement="top" :disabled="disabled" class="output-form">
        <n-form-item :label="t('page.workflowAnalysis.outputName')" required>
          <n-input v-model:value="outputId" :maxlength="64" placeholder="mean_measurement" data-testid="workflow-analysis-output-id" />
        </n-form-item>
        <n-form-item :label="t('page.workflowAnalysis.field')" required>
          <n-select v-model:value="fieldKey" :options="fieldOptions" data-testid="workflow-analysis-output-field" />
        </n-form-item>
        <n-form-item :label="t('page.workflowAnalysis.statistic')" required>
          <n-select v-model:value="statistic" :options="statistics.map(value => ({ value, label: t(`page.analysis.statistics.${value}`) }))" data-testid="workflow-analysis-statistic" />
        </n-form-item>
        <div v-for="group in builtinRecipe.group_by" :key="group" class="group-input mb-3">
          <n-form-item :label="`${t('page.workflowAnalysis.group')} · ${group}`" required>
            <div class="w-full space-y-2">
              <n-select v-model:value="groupTypes[group]" :options="groupTypeOptions(group)" :disabled="disabled || groupNulls[group]" />
              <n-input v-model:value="groupValues[group]" :disabled="disabled || groupNulls[group]" :aria-label="group" />
              <n-checkbox v-model:checked="groupNulls[group]">
                {{ t('page.workflowAnalysis.nullGroup') }}
              </n-checkbox>
            </div>
          </n-form-item>
        </div>
        <n-button :disabled="disabled || !draftOutput" data-testid="workflow-analysis-add-output" @click="addOutput">
          {{ t('page.workflowAnalysis.addOutput') }}
        </n-button>
      </n-form>
    </template>
  </section>
</template>

<script setup lang="ts">
import type { WorkflowAnalysisOutput, WorkflowAnalysisPublication, WorkflowComputeFileOutput, WorkflowComputeOutput } from "@/service/api/workflow-analysis-methods"
import type { WorkflowAnalysisNode, WorkflowGraph, WorkflowScalarType } from "@/service/api/workflow-definitions"
import { isComputeAnalysisRecipe } from "@/utils/analysis-compute"
import { parseWorkflowScalar } from "@/utils/workflow-editor"
import AnalysisComputeInputDeclarations from "@/views/analysis/components/analysis-compute-input-declarations.vue"
import { computed, ref, watch } from "vue"
import { useI18n } from "vue-i18n"
import WorkflowComputeOutputs from "./workflow-compute-outputs.vue"

const props = defineProps<{ graph: WorkflowGraph, node: WorkflowAnalysisNode, method?: WorkflowAnalysisPublication, disabled: boolean }>()
const emit = defineEmits<{ sources: [sources: WorkflowAnalysisNode["record_sources"]], outputs: [outputs: WorkflowAnalysisOutput[]], computeOutputs: [outputs: WorkflowComputeOutput[]], computeFiles: [outputs: WorkflowComputeFileOutput[]] }>()
const { t } = useI18n()
const outputId = ref("")
const fieldKey = ref<string | null>(null)
const statistic = ref<WorkflowAnalysisOutput["statistic"]>("mean")
const groupValues = ref<Record<string, string>>({})
const groupTypes = ref<Record<string, WorkflowScalarType>>({})
const groupNulls = ref<Record<string, boolean>>({})
const statistics: WorkflowAnalysisOutput["statistic"][] = ["count", "missing", "invalid", "mean", "median", "min", "max", "sum", "sample_stddev"]
const sourceOptions = computed(() => props.graph.nodes.filter(node => node.kind === "protocol" && node.protocol_id === props.method?.protocol_id && props.graph.edges.some(edge => edge.source_node_id === node.node_id && edge.target_node_id === props.node.node_id)).map(node => ({ label: node.title, value: node.node_id })))
const builtinRecipe = computed(() => props.method && !isComputeAnalysisRecipe(props.method.recipe) ? props.method.recipe : null)
const computeRecipe = computed(() => props.method && isComputeAnalysisRecipe(props.method.recipe) ? props.method.recipe : null)
const fieldOptions = computed(() => (builtinRecipe.value?.numeric_fields ?? []).map(key => ({ value: key, label: props.method?.input_fields.find(field => field.key === key)?.title || key })))
function groupTypeOptions(key: string) {
  const field = props.method?.input_fields.find(field => field.key === key)
  const types = Array.isArray(field?.type) ? field.type : [field?.type]
  return types.filter((type): type is WorkflowScalarType => ["string", "number", "integer", "boolean"].includes(type || "")).map(type => ({ value: type, label: t(`page.workflowDefinitions.fieldTypes.${type}`) }))
}
const draftOutput = computed<WorkflowAnalysisOutput | null>(() => {
  if (props.node.analysis_kind === "compute" || !/^[a-z][a-z0-9_-]{0,63}$/.test(outputId.value) || !fieldKey.value || props.node.analysis_outputs.some(output => output.output_id === outputId.value))
    return null
  const group: WorkflowAnalysisOutput["group"] = {}
  try {
    for (const key of builtinRecipe.value?.group_by ?? []) {
      if (!groupNulls.value[key] && !groupTypes.value[key])
        return null
      group[key] = groupNulls.value[key] ? null : parseWorkflowScalar(groupValues.value[key] ?? "", groupTypes.value[key])
    }
  }
  catch { return null }
  return { output_id: outputId.value, field: fieldKey.value, statistic: statistic.value, group }
})
function updateSources(ids: string[]) {
  emit("sources", ids.map(source_node_id => ({ source_node_id, cardinality: "one" })))
}
function addOutput() {
  if (!draftOutput.value || props.disabled || props.node.analysis_kind === "compute")
    return
  emit("outputs", [...props.node.analysis_outputs, draftOutput.value])
  outputId.value = ""
}
watch(() => [props.node.node_id, props.node.method_publication_id], () => {
  outputId.value = ""
  fieldKey.value = null
  groupValues.value = {}
  groupNulls.value = {}
  groupTypes.value = Object.fromEntries((builtinRecipe.value?.group_by ?? []).map(key => [key, groupTypeOptions(key)[0]?.value]))
}, { immediate: true })
</script>

<style scoped>
.analysis-inputs { min-width: 0; }
.output-row { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; padding: 12px; border: 1px solid #e2e8f0; border-radius: 8px; background: white; overflow-wrap: anywhere; }
.output-form { padding: 14px; border: 1px solid #e2e8f0; border-radius: 8px; background: white; }
</style>
