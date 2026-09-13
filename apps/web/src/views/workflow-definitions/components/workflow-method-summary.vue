<template>
  <section class="workflow-method-summary" data-testid="workflow-method-summary">
    <template v-if="computeRecipe">
      <n-alert type="warning" class="mb-3">
        {{ t('page.workflowAnalysis.computeContractHint') }}
      </n-alert>
      <dl class="method-grid aira-type-meta">
        <dt>{{ t('page.analysis.compute.language') }}</dt><dd>{{ computeRecipe.language === 'python' ? 'Python' : 'R' }}</dd>
        <dt>{{ t('page.analysis.compute.environment') }}</dt><dd>{{ method.compute_contract?.environment.name || computeRecipe.environment_revision_id }} · r{{ method.compute_contract?.environment.metadata.environment_revision ?? '—' }}</dd>
        <dt>{{ t('page.analysis.compute.image') }}</dt><dd>{{ method.compute_contract?.environment.metadata.image_ref || '—' }}</dd>
        <dt>{{ t('page.analysis.compute.network') }}</dt><dd>{{ method.compute_contract?.environment.metadata.network_policy || '—' }} · {{ method.compute_contract?.environment.metadata.allowed_egress_hosts.join(', ') }}</dd>
      </dl>
      <analysis-compute-input-declarations :inputs="computeRecipe.input_files" />
      <h4 class="aira-type-label">
        {{ t('page.analysis.compute.source') }}
      </h4>
      <pre tabindex="0" data-testid="workflow-published-compute-code">{{ computeRecipe.source_code }}</pre>
      <h4 class="aira-type-label">
        {{ t('page.analysis.compute.parameters') }}
      </h4><pre tabindex="0">{{ JSON.stringify(computeRecipe.parameters, null, 2) }}</pre>
      <h4 class="aira-type-label">
        {{ t('page.analysis.compute.outputs') }}
      </h4><pre tabindex="0">{{ JSON.stringify(computeRecipe.output_files, null, 2) }}</pre>
      <h4 class="aira-type-label">
        {{ t('page.workflowAnalysis.computeResultContract') }}
      </h4><pre tabindex="0" data-testid="workflow-published-result-schema">{{ JSON.stringify(method.compute_contract?.result_schema, null, 2) }}</pre>
      <details><summary>{{ t('page.analysis.compute.resources') }} · {{ t('page.workflowAnalysis.inputContract') }}</summary><pre tabindex="0">{{ JSON.stringify({ resources: method.compute_contract?.environment.metadata.resource_limits, input: method.compute_contract?.input_schema_contract }, null, 2) }}</pre></details>
    </template>
    <template v-else-if="builtinRecipe">
      <dl class="method-grid aira-type-meta">
        <dt>{{ t('page.analysis.numericFields') }}</dt><dd>{{ builtinRecipe.numeric_fields.map(fieldLabel).join(' · ') }}</dd>
        <dt>{{ t('page.analysis.groupBy') }}</dt><dd>{{ builtinRecipe.group_by.length ? builtinRecipe.group_by.map(fieldLabel).join(' · ') : t('page.analysis.allRecords') }}</dd>
        <dt>{{ t('page.analysis.missingPolicy') }}</dt><dd>{{ t(`page.analysis.missing.${builtinRecipe.missing_policy}`) }}</dd>
        <dt>{{ t('page.analysis.fieldFilters', { count: builtinRecipe.filters.length }) }}</dt>
        <dd>
          <ul v-if="builtinRecipe.filters.length" class="my-0 pl-4">
            <li v-for="(filter, index) in builtinRecipe.filters" :key="index">
              {{ fieldLabel(filter.field) }} · {{ t(`page.analysis.operators.${filter.op}`) }} · {{ JSON.stringify(filter.value) }}
            </li>
          </ul><span v-else>—</span>
        </dd>
      </dl>
    </template>
  </section>
</template>

<script setup lang="ts">
import type { WorkflowAnalysisPublication } from "@/service/api/workflow-analysis-methods"
import { isComputeAnalysisRecipe } from "@/utils/analysis-compute"
import AnalysisComputeInputDeclarations from "@/views/analysis/components/analysis-compute-input-declarations.vue"
import { computed } from "vue"
import { useI18n } from "vue-i18n"

const props = defineProps<{ method: Pick<WorkflowAnalysisPublication, "recipe" | "compute_contract" | "input_fields"> }>()
const { t } = useI18n()
const computeRecipe = computed(() => isComputeAnalysisRecipe(props.method.recipe) ? props.method.recipe : null)
const builtinRecipe = computed(() => !isComputeAnalysisRecipe(props.method.recipe) ? props.method.recipe : null)
function fieldLabel(key: string) {
  const field = props.method.input_fields.find(field => field.key === key)
  return `${field?.title || key} [${key}]${field?.unit ? ` (${field.unit})` : ""}`
}
</script>

<style scoped>
.workflow-method-summary { min-width: 0; overflow-wrap: anywhere; }
.method-grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; }
.method-grid dt { font-weight: 600; }
.method-grid dd { margin: 0 0 8px; }
pre { max-width: 100%; max-height: 24rem; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; padding: 12px; border-radius: 8px; background: #f8fafc; }
pre:focus-visible { outline: 2px solid #0084e2; outline-offset: 2px; }
</style>
