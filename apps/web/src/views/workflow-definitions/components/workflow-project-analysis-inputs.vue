<template>
  <section class="project-analysis-inputs" data-testid="workflow-project-analysis-settings">
    <n-alert type="info" class="mb-4">{{ t('page.workflowProjectAnalysis.sourcesHint') }}</n-alert>
    <n-form label-placement="top" :disabled="disabled">
      <n-form-item v-for="slot in method?.project_contract?.slots ?? []" :key="slot.slot_id" :label="`${slot.label} · ${slot.slot_id}`" required>
        <div class="w-full min-w-0">
          <n-select :value="node.record_sources.filter(source => source.slot_id === slot.slot_id).map(source => source.source_node_id)" :options="sourceOptions(slot.slot_id)" multiple clearable :data-testid="`workflow-project-sources-${slot.slot_id}`" @update:value="ids => emit('sources', replaceWorkflowProjectSources(node, slot.slot_id, ids))" />
          <p class="aira-type-meta my-2">{{ t('page.workflowProjectAnalysis.allowedVersions') }}: {{ slot.versions.map(version => version.version).join(' · ') }}</p>
          <p v-if="!sourceOptions(slot.slot_id).length" class="aira-type-meta">{{ t('page.workflowAnalysis.noSources') }}</p>
        </div>
      </n-form-item>
    </n-form>
    <h4 class="aira-type-label">{{ t('page.workflowAnalysis.outputs') }}</h4>
    <p class="aira-type-meta">{{ t('page.workflowProjectAnalysis.outputsHint') }}</p>
    <p v-if="!node.project_outputs.length" class="aira-type-meta">{{ t('page.workflowAnalysis.noOutputs') }}</p>
    <article v-for="output in node.project_outputs" :key="output.output_id" class="project-output-row" data-testid="workflow-project-output">
      <div class="min-w-0"><strong>{{ output.output_id }}</strong><p class="aira-type-meta my-1">{{ sourceLabel(output.source) }} · {{ output.field }} · {{ t(`page.analysis.statistics.${output.statistic}`) }}</p><code>{{ JSON.stringify(output.group) }}</code></div>
      <n-button size="small" :disabled="disabled" @click="emit('outputs', node.project_outputs.filter(item => item.output_id !== output.output_id))">{{ t('common.delete') }}</n-button>
    </article>
    <n-form label-placement="top" :disabled="disabled" class="project-output-form">
      <n-form-item :label="t('page.workflowProjectAnalysis.outputSource')" required>
        <n-select v-model:value="sourceKey" :options="outputSourceOptions" data-testid="workflow-project-output-source" />
      </n-form-item>
      <n-form-item :label="t('page.workflowAnalysis.outputName')" required><n-input v-model:value="outputId" :maxlength="64" placeholder="mean_measurement" data-testid="workflow-project-output-id" /></n-form-item>
      <n-form-item :label="t('page.workflowAnalysis.field')" required><n-select v-model:value="fieldKey" :options="fieldOptions" data-testid="workflow-project-output-field" /></n-form-item>
      <n-form-item :label="t('page.workflowAnalysis.statistic')" required><n-select v-model:value="statistic" :options="statistics.map(value => ({ value, label: t(`page.analysis.statistics.${value}`) }))" data-testid="workflow-project-statistic" /></n-form-item>
      <n-form-item v-for="group in outputRecipe?.group_by ?? []" :key="group" :label="`${t('page.workflowAnalysis.group')} · ${group}`" required>
        <div class="w-full space-y-2">
          <n-select v-model:value="groupTypes[group]" :options="groupTypeOptions(group)" :disabled="disabled || groupNulls[group]" :aria-label="`${group} type`" />
          <n-input v-model:value="groupValues[group]" :disabled="disabled || groupNulls[group]" :aria-label="group" />
          <n-checkbox v-model:checked="groupNulls[group]">{{ t('page.workflowAnalysis.nullGroup') }}</n-checkbox>
        </div>
      </n-form-item>
      <n-button :disabled="disabled || !draftOutput" data-testid="workflow-project-add-output" @click="addOutput">{{ t('page.workflowAnalysis.addOutput') }}</n-button>
    </n-form>
  </section>
</template>

<script setup lang="ts">
import type { WorkflowAnalysisPublication, WorkflowProjectOutput } from "@/service/api/workflow-analysis-methods"
import type { WorkflowGraph, WorkflowProjectAnalysisNode, WorkflowScalarType } from "@/service/api/workflow-definitions"
import { isWorkflowProjectRecipe, parseWorkflowScalar } from "@/utils/workflow-editor"
import { replaceWorkflowProjectSources, workflowProjectOutputFields, workflowProjectOutputRecipe, workflowProjectOutputValid, workflowProjectSourceOptions } from "@/utils/workflow-project-analysis"
import { computed, ref, watch } from "vue"
import { useI18n } from "vue-i18n"

const props = defineProps<{ graph: WorkflowGraph, node: WorkflowProjectAnalysisNode, method?: WorkflowAnalysisPublication, disabled: boolean }>()
const emit = defineEmits<{ sources: [sources: WorkflowProjectAnalysisNode["record_sources"]], outputs: [outputs: WorkflowProjectOutput[]] }>()
const { t } = useI18n()
const sourceKey = ref<string | null>(null)
const outputId = ref("")
const fieldKey = ref<string | null>(null)
const statistic = ref<WorkflowProjectOutput["statistic"]>("mean")
const groupValues = ref<Record<string, string>>({})
const groupTypes = ref<Record<string, WorkflowScalarType>>({})
const groupNulls = ref<Record<string, boolean>>({})
const statistics: WorkflowProjectOutput["statistic"][] = ["count", "missing", "invalid", "mean", "median", "min", "max", "sum", "sample_stddev"]
const projectRecipe = computed(() => props.method && isWorkflowProjectRecipe(props.method.recipe) ? props.method.recipe : null)
const outputSourceOptions = computed(() => [
  ...(projectRecipe.value?.slots ?? []).map(slot => ({ value: `local:${slot.slot_id}`, label: `${t('page.workflowProjectAnalysis.localResult')} · ${slot.label} [${slot.slot_id}]` })),
  ...(projectRecipe.value?.join ? [{ value: "join", label: t("page.workflowProjectAnalysis.joinResult") }] : []),
])
const outputSource = computed<WorkflowProjectOutput["source"] | null>(() => sourceKey.value === "join" ? { kind: "join" } : sourceKey.value?.startsWith("local:") ? { kind: "local", slot_id: sourceKey.value.slice(6) } : null)
const outputRecipe = computed(() => outputSource.value ? workflowProjectOutputRecipe(props.method, outputSource.value) : null)
const outputFields = computed(() => outputSource.value ? workflowProjectOutputFields(props.method, outputSource.value) : [])
const fieldOptions = computed(() => (outputRecipe.value?.numeric_fields ?? []).flatMap((key) => {
  const field = outputFields.value.find(field => field.key === key)
  return field ? [{ value: key, label: field.title || key }] : []
}))
function sourceOptions(slotId: string) {
  return workflowProjectSourceOptions(props.graph, props.node, props.method, slotId)
}
function sourceLabel(source: WorkflowProjectOutput["source"]) {
  return source.kind === "join" ? t("page.workflowProjectAnalysis.joinResult") : `${t("page.workflowProjectAnalysis.localResult")} · ${projectRecipe.value?.slots.find(slot => slot.slot_id === source.slot_id)?.label || source.slot_id} [${source.slot_id}]`
}
function groupTypeOptions(key: string) {
  const field = outputFields.value.find(field => field.key === key)
  const types = Array.isArray(field?.type) ? field.type : [field?.type]
  return types.filter((type): type is WorkflowScalarType => ["string", "number", "integer", "boolean"].includes(type || "")).map(type => ({ value: type, label: t(`page.workflowDefinitions.fieldTypes.${type}`) }))
}
const draftOutput = computed<WorkflowProjectOutput | null>(() => {
  if (!outputSource.value || !fieldKey.value || !outputRecipe.value)
    return null
  const group: WorkflowProjectOutput["group"] = {}
  try {
    for (const key of outputRecipe.value.group_by) {
      if (!groupNulls.value[key] && !groupTypes.value[key])
        return null
      group[key] = groupNulls.value[key] ? null : parseWorkflowScalar(groupValues.value[key] ?? "", groupTypes.value[key])
    }
  }
  catch { return null }
  const output = { output_id: outputId.value, source: outputSource.value, field: fieldKey.value, statistic: statistic.value, group }
  return workflowProjectOutputValid(props.method, output, props.node.project_outputs) ? output : null
})
function addOutput() {
  if (!draftOutput.value || props.disabled)
    return
  emit("outputs", [...props.node.project_outputs, draftOutput.value])
  outputId.value = ""
}
watch(() => [props.node.node_id, props.node.method_publication_id], () => {
  sourceKey.value = null
  outputId.value = ""
}, { immediate: true })
watch(outputSource, () => {
  fieldKey.value = null
  groupValues.value = {}
  groupNulls.value = {}
  groupTypes.value = Object.fromEntries((outputRecipe.value?.group_by ?? []).map(key => [key, groupTypeOptions(key)[0]?.value]))
}, { immediate: true })
</script>

<style scoped>
.project-analysis-inputs { min-width: 0; overflow-wrap: anywhere; }
.project-output-row { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; padding: 12px; margin-bottom: 12px; border: 1px solid #e2e8f0; border-radius: 8px; background: white; }
.project-output-form { min-width: 0; padding: 14px; border: 1px solid #e2e8f0; border-radius: 8px; background: white; }
</style>
