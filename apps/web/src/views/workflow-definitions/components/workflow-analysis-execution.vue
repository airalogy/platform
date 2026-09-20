<template>
  <section v-if="action.kind === 'analysis_run' && !action.workflow_data_restricted" class="analysis-execution mt-3" data-testid="workflow-analysis-execution">
    <template v-if="method">
      <h4 class="aira-type-label my-2">
        {{ method.title }} · {{ t('page.workflowAnalysis.analysisCard') }}
      </h4>
      <div class="aira-type-meta">
        {{ t('page.workflowAnalysis.snapshotDigest') }}: {{ method.digest }}
      </div>
      <workflow-method-summary v-if="!action.analysis_run?.compute" :method="method" data-testid="workflow-analysis-method-contract" />
      <analysis-compute-contract v-if="action.analysis_run?.compute" :contract="action.analysis_run.compute" :mode="action.approval?.status === 'pending' ? 'approval' : 'historical'" />
      <template v-if="action.analysis_run?.compute && method.compute_contract">
        <h4 class="aira-type-label">
          {{ t('page.workflowAnalysis.computeResultContract') }}
        </h4>
        <pre class="analysis-execution-json" tabindex="0" data-testid="workflow-compute-approved-result-schema">{{ JSON.stringify(method.compute_contract.result_schema, null, 2) }}</pre>
      </template>
      <details><summary>{{ t('page.workflowAnalysis.recipe') }}</summary><pre class="analysis-execution-json" tabindex="0">{{ JSON.stringify(method.recipe, null, 2) }}</pre></details>
    </template>
    <template v-if="projectInput">
      <p class="aira-type-meta">{{ t('page.workflowAnalysis.actualInput') }}: {{ projectInput.selection.inputs.reduce((total, input) => total + (input.selection.mode === 'selected' ? input.selection.records.length : 0), 0) }}</p>
      <article v-for="slot in projectInput.selection.inputs" :key="slot.slot_id" class="my-3" data-testid="workflow-project-resolved-slot">
        <strong>{{ method?.project_contract?.slots.find(item => item.slot_id === slot.slot_id)?.label || slot.slot_id }} · {{ slot.slot_id }}</strong>
        <p class="aira-type-meta my-1">Protocol · {{ slot.protocol_id }}</p>
        <ul class="pl-5">
          <li v-for="source in projectInput.source_nodes.filter(source => source.slot_id === slot.slot_id)" :key="source.source_node_id" class="aira-type-meta my-2">
            {{ sourceTitles?.[source.source_node_id] || source.source_node_id }} → {{ t('page.workflowDefinitions.resolution.record') }} · {{ source.record_id }} · {{ t('page.workflowDefinitions.revision', { number: source.record_version }) }}
            <div>{{ t('page.workflowDefinitions.protocolVersion') }} · {{ source.protocol_version_id }}</div>
          </li>
        </ul>
      </article>
      <p class="aira-type-meta">{{ t('page.workflowAnalysis.sourceDigest') }}: {{ projectInput.source_digest }}</p>
      <template v-if="action.approval?.status === 'pending'">
        <n-alert type="info" class="my-3">{{ t('page.workflowAnalysis.actualApproval') }}</n-alert>
        <details v-if="projectInput.summary?.schema === 'airalogy.project-result.v1'"><summary>{{ t('page.workflowProjectAnalysis.inputPreview') }}</summary><project-analysis-result :result="projectInput.summary" /></details>
      </template>
    </template>
    <template v-else-if="input">
      <p v-if="input.summary?.counts" class="aira-type-meta">
        {{ t('page.analysis.countSummary', { ...input.summary.counts }) }}
      </p>
      <p class="aira-type-meta">
        {{ t('page.workflowAnalysis.actualInput') }}: {{ input.selection.records.length }}
      </p>
      <div class="aira-type-meta">
        {{ t('page.workflowAnalysis.sourceDigest') }}: {{ input.source_digest }}
      </div>
      <p v-if="action.approval?.status === 'pending'" class="aira-type-meta">
        {{ t('page.workflowAnalysis.actualApproval') }}
      </p>
    </template>
    <p v-else class="aira-type-meta">
      {{ t('page.workflowAnalysis.pendingRecords') }}
    </p>
    <template v-if="computeJob">
      <n-tag class="my-2" :type="computeJob.status === 'completed' ? 'success' : computeJob.status === 'failed' ? 'error' : 'info'" data-testid="workflow-compute-state">
        {{ t(`page.analysis.compute.states.${computeJob.status}`) }}
      </n-tag>
      <n-alert v-if="computeJob.status === 'queued'" type="info" class="mb-3">
        {{ t('page.analysis.compute.queuedHint') }}
      </n-alert>
      <n-alert v-if="computeJob.error || computeJob.cancel_reason" type="warning" class="mb-3">
        {{ computeJob.error || computeJob.cancel_reason }}
      </n-alert>
    </template>
    <div v-if="outputs.length" class="aira-type-meta mt-2">
      <strong>{{ t('page.workflowAnalysis.outputs') }}</strong>
      <ul class="pl-5">
        <li v-for="output in outputs" :key="output.output_id">
          {{ output.output_id }}: {{ output.field }} · {{ t(`page.analysis.statistics.${output.statistic}`) }} · {{ JSON.stringify(output.group) }}
        </li>
      </ul>
    </div>
    <div v-if="projectOutputs.length" class="aira-type-meta mt-2" data-testid="workflow-project-output-summary">
      <strong>{{ t('page.workflowAnalysis.outputs') }}</strong>
      <ul class="pl-5"><li v-for="output in projectOutputs" :key="output.output_id">
        {{ output.output_id }}: {{ output.source.kind === 'join' ? t('page.workflowProjectAnalysis.joinResult') : `${t('page.workflowProjectAnalysis.localResult')} · ${output.source.slot_id}` }} · {{ output.field }} · {{ t(`page.analysis.statistics.${output.statistic}`) }} · {{ JSON.stringify(output.group) }}
      </li></ul>
    </div>
    <template v-if="result?.report">
      <h4 class="aira-type-label">
        {{ t('page.workflowAnalysis.analysisResult') }}
      </h4>
      <project-analysis-result v-if="projectReport" :result="projectReport" />
      <template v-else-if="builtinReport">
        <p class="aira-type-meta">
          {{ t('page.analysis.countSummary', { ...builtinReport.counts }) }}
        </p>
        <analysis-result-charts :result="builtinReport" />
        <analysis-result-table :result="builtinReport" />
      </template>
      <div v-else-if="computeOutputs.length" class="workflow-port-table" tabindex="0">
        <table data-testid="workflow-compute-result-table">
          <thead><tr><th>{{ t('page.workflowAnalysis.outputName') }}</th><th>{{ t('page.analysis.value') }}</th><th>{{ t('page.workflowAnalysis.outputType') }}</th></tr></thead><tbody>
            <tr v-for="output in computeOutputs" :key="output.output_id">
              <th>{{ output.output_id }}</th><td>{{ JSON.stringify(result.outputs.analysis?.[output.output_id]) }}</td><td>{{ output.value_type }} · {{ output.unit || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <pre v-else class="analysis-execution-json" tabindex="0" data-testid="workflow-compute-report-only">{{ JSON.stringify((result.report as AnalysisComputeResult).computed_result, null, 2) }}</pre>
      <p v-if="computeJob?.actual_cost != null" class="aira-type-meta">
        {{ t('page.analysis.compute.actualCost') }}: {{ computeJob.actual_cost }} {{ computeJob.currency }}
      </p>
      <div v-for="output in computeJob?.output_manifest ?? []" :key="output.id" class="workflow-output-file my-3">
        <div class="min-w-0">
          <strong>{{ output.asset_name || output.mount_name }}</strong><p class="aira-type-meta my-1">
            {{ output.media_type }} · {{ output.byte_size ?? '—' }} B · {{ output.checksum_sha256 || '—' }}
          </p>
        </div>
        <n-button v-if="taskId && action.analysis_run?.output_download_base && output.status === 'registered' && output.checksum_sha256" :loading="downloading === output.id" size="small" data-testid="workflow-compute-download" @click="download(output.id, output.mount_name, output.media_type)">
          {{ t('common.download') }}
        </n-button>
      </div>
      <n-alert v-if="downloadError" type="error" class="my-3">
        {{ downloadError }}
      </n-alert>
      <pre class="analysis-execution-json" tabindex="0" data-testid="workflow-analysis-result-ports">{{ JSON.stringify(result.outputs, null, 2) }}</pre>
      <details class="mt-3">
        <summary>{{ t('page.workflowAnalysis.fullResult') }}</summary><pre class="analysis-execution-json" tabindex="0">{{ JSON.stringify(result.report, null, 2) }}</pre>
      </details>
      <div class="aira-type-meta mt-2">
        {{ t('page.workflowAnalysis.resultDigest') }}: {{ result.result_digest }}
      </div>
      <n-button v-if="projectRoute && action.analysis_run?.can_open_private_report && action.analysis_run.id" class="mt-3" size="small" data-testid="workflow-analysis-open-report" @click="openReport">
        {{ t('page.workflowAnalysis.openReport') }}
      </n-button>
    </template>
  </section>
</template>

<script setup lang="ts">
import type { AnalysisResult } from "@/service/api/analysis"
import type { AnalysisComputeResult } from "@/service/api/analysis-compute"
import type { ProjectAnalysisSelection, ProjectAnalysisResult as ProjectResult } from "@/service/api/project-analysis"
import type { ResearchAction } from "@/service/api/research-tasks"
import type { WorkflowAnalysisOutput, WorkflowComputeOutput, WorkflowProjectOutput } from "@/service/api/workflow-analysis-methods"
import { downloadWorkflowAnalysisOutput } from "@/service/api/research-tasks"
import { isComputeAnalysisRecipe } from "@/utils/analysis-compute"
import { isWorkflowProjectRecipe } from "@/utils/workflow-editor"
import AnalysisComputeContract from "@/views/analysis/components/analysis-compute-contract.vue"
import AnalysisResultCharts from "@/views/analysis/components/analysis-result-charts.vue"
import AnalysisResultTable from "@/views/analysis/components/analysis-result-table.vue"
import ProjectAnalysisResult from "@/views/analysis/components/project-analysis-result.vue"
import { downloadAs } from "@airalogy/shared/utils"
import { computed, ref } from "vue"
import { useI18n } from "vue-i18n"
import { useRouter } from "vue-router"
import WorkflowMethodSummary from "./workflow-method-summary.vue"

const props = defineProps<{ action: ResearchAction, taskId?: string, projectRoute?: { labUid: string, projectUid: string }, sourceTitles?: Record<string, string> }>()
const { t } = useI18n()
const router = useRouter()
const method = computed(() => props.action.analysis_run?.method)
const computeJob = computed(() => props.action.analysis_run?.compute_job)
const downloading = ref("")
const downloadError = ref("")
const input = computed(() => props.action.input_data.analysis_kind !== "project" ? props.action.input_data.analysis_input as { source_digest: string, selection: { records: Array<{ id: string, version: number }> }, summary?: { counts?: AnalysisResult["counts"] } } | undefined : undefined)
const projectInput = computed(() => props.action.input_data.analysis_kind === "project"
  ? props.action.input_data.analysis_input as {
    source_digest: string
    selection: ProjectAnalysisSelection
    source_nodes: Array<{ slot_id: string, source_node_id: string, protocol_id: string, protocol_version_id: string, record_id: string, record_version: number }>
    summary?: ProjectResult
  } | undefined
  : undefined)
const outputs = computed(() => (props.action.input_data.analysis_outputs ?? []) as WorkflowAnalysisOutput[])
const computeOutputs = computed(() => (props.action.input_data.compute_outputs ?? []) as WorkflowComputeOutput[])
const projectOutputs = computed(() => (props.action.input_data.project_outputs ?? []) as WorkflowProjectOutput[])
const result = computed(() => props.action.output_data.analysis_result as { analysis_id: string, result_digest: string, outputs: { analysis?: Record<string, unknown> }, report?: AnalysisResult | AnalysisComputeResult | ProjectResult } | undefined)
const projectReport = computed(() => result.value?.report && "schema" in result.value.report && result.value.report.schema === "airalogy.project-result.v1" ? result.value.report as ProjectResult : undefined)
const builtinReport = computed(() => method.value && !isComputeAnalysisRecipe(method.value.recipe) && !isWorkflowProjectRecipe(method.value.recipe) ? result.value?.report as AnalysisResult | undefined : undefined)
async function download(id: string, name: string, mediaType: string) {
  if (!props.taskId || props.action.workflow_data_restricted)
    return
  downloading.value = id
  downloadError.value = ""
  try {
    const data = await downloadWorkflowAnalysisOutput(props.taskId, props.action.id, id)
    downloadAs(data, name, mediaType)
  }
  catch { downloadError.value = t("page.analysis.compute.accessChanged") }
  finally { downloading.value = "" }
}
async function openReport() {
  if (!props.projectRoute || !props.action.analysis_run?.can_open_private_report || !props.action.analysis_run.id)
    return
  await router.push({ name: "project-analysis", params: props.projectRoute, query: { runId: props.action.analysis_run.id, ...(method.value && isWorkflowProjectRecipe(method.value.recipe) ? { scope: "project" } : {}) } })
}
</script>

<style scoped>
.analysis-execution { min-width: 0; overflow-wrap: anywhere; }
.analysis-execution-json { max-height: 24rem; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; padding: 12px; border-radius: 8px; background: white; }
.workflow-port-table { max-width: 100%; overflow: auto; }
.workflow-port-table table { width: 100%; border-collapse: collapse; text-align: left; }
.workflow-port-table th, .workflow-port-table td { padding: 8px; border-bottom: 1px solid #e2e8f0; }
.workflow-output-file { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; overflow-wrap: anywhere; }
</style>
