<template>
  <project-analysis-workbench v-if="projectScope && projectInfo" :key="projectInfo.id" :project-id="projectInfo.id" @single="changeAnalysisScope(false)" />
  <div v-else class="analysis-page py-8" data-testid="analysis-workbench">
    <header class="flex flex-wrap items-start justify-between gap-3">
      <div class="min-w-0">
        <div class="aira-type-eyebrow aira-type-eyebrow--accent">
          {{ $t("page.analysis.eyebrow") }}
        </div>
        <h1 class="aira-type-page-title mb-0 mt-1">
          {{ $t("page.analysis.title") }}
        </h1>
        <p class="aira-type-body aira-text-secondary mt-2 max-w-3xl">
          {{ $t("page.analysis.description") }}
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <n-button data-testid="analysis-open-project" @click="changeAnalysisScope(true)">
          {{ $t('page.projectAnalysis.open') }}
        </n-button>
        <n-button :loading="loading" @click="refreshWorkspace">
          {{ $t("common.refresh") }}
        </n-button>
      </div>
    </header>

    <n-alert type="info" class="mb-5">
      {{ $t("page.analysis.privateHint") }}
    </n-alert>
    <n-alert v-if="loadError" type="error" class="mb-4" data-testid="analysis-error">
      {{ loadError }}
    </n-alert>
    <section v-if="computeApprovalId && projectInfo" class="analysis-panel">
      <n-button class="mb-3" @click="closeComputeApproval">
        {{ $t("page.analysis.compute.backToWorkbench") }}
      </n-button>
      <analysis-compute-report :run-id="computeApprovalId" :project-id="projectInfo.id" approval-only />
    </section>
    <n-spin v-else :show="loading">
      <div class="analysis-grid">
        <section class="analysis-panel">
          <h2 class="aira-type-section-title mt-0">
            {{ $t("page.analysis.configure") }}
          </h2>
          <n-form label-placement="top" :disabled="busy || contextLoading">
            <n-form-item :label="$t('page.analysis.protocol')" required>
              <n-select
                v-model:value="protocolId"
                :options="protocolOptions"
                filterable
                remote
                :loading="contextLoading"
                data-testid="analysis-protocol"
                @update:value="value => selectProtocol(value)"
                @search="searchProtocols"
              />
            </n-form-item>
            <n-alert v-if="selectionError" type="warning" class="mb-4" data-testid="analysis-selection-error">
              {{ $t("page.analysis.invalidSelection") }}
            </n-alert>
            <div v-if="protocolId && !context && !contextLoading" class="mb-4 flex flex-wrap gap-2">
              <n-button v-if="requestedSelection" data-testid="analysis-retry-context" @click="retrySelectionContext">
                {{ $t("common.retry") }}
              </n-button>
              <n-button data-testid="analysis-use-latest" @click="useLatestRecords">
                {{ $t("page.analysis.useLatest") }}
              </n-button>
            </div>
            <template v-if="context">
              <n-alert v-if="context.own_records_only" type="info" class="mb-4">
                {{ $t("page.analysis.ownRecordsOnly") }}
              </n-alert>
              <n-alert v-for="field in context.fields.filter(item => item.unsupported_reason)" :key="field.key" type="warning" class="mb-4">
                {{ fieldLabel(field) }}: {{ field.unsupported_reason }}
              </n-alert>
              <div class="analysis-scope mb-4">
                <div class="aira-type-label">
                  {{ $t("page.analysis.sourceScope") }}
                </div>
                <p class="aira-type-body my-2" data-testid="analysis-selection-summary">
                  {{ selection?.mode === "selected"
                    ? $t("page.analysis.selectedScope", { count: selection.records.length })
                    : selection ? $t("page.analysis.filteredScope") : $t("page.analysis.noSelection") }}
                </p>
                <div v-if="selection?.mode === 'latest' && Object.keys(selection.filters).length" class="flex flex-wrap gap-2">
                  <n-tag v-for="(value, key) in selection.filters" :key="key" size="small">
                    {{ sourceFilterLabel(key) }}: {{ value }}
                  </n-tag>
                </div>
                <div class="aira-type-meta mb-2">
                  {{ $t("page.analysis.recordLimit", { count: context.limits.max_records }) }}
                </div>
                <n-button size="small" :disabled="busy" data-testid="analysis-use-latest" @click="useLatestRecords">
                  {{ $t("page.analysis.useLatest") }}
                </n-button>
              </div>
              <n-form-item :label="$t('page.analysis.question')">
                <n-input v-model:value="question" type="textarea" :maxlength="4000" :autosize="{ minRows: 2, maxRows: 5 }" data-testid="analysis-question" />
                <template #feedback>
                  {{ $t("page.analysis.questionHint") }}
                </template>
              </n-form-item>
              <analysis-ai-panel
                v-if="protocolId && projectInfo && analysisMode !== 'compute'"
                kind="draft" :protocol-id="protocolId" :project-id="projectInfo.id"
                :selection="selection" :question="question" :available="context.ai_available"
                @adopt="adoptAIDraft" @manual="startManualAnalysis" @research-task="openAdvancedAnalysis"
              />
              <n-form-item :label="$t('page.analysis.compute.mode')">
                <n-select v-model:value="analysisMode" :options="analysisModeOptions" data-testid="analysis-mode" />
              </n-form-item>
              <analysis-compute-form
                v-if="analysisMode === 'compute' && protocolId && selection && projectInfo"
                :protocol-id="protocolId" :project-id="projectInfo.id" :selection="selection" :question="question" :seed="computeSeed" :ai-available="context.ai_available"
                @created="handleComputeCreated" @revision-saved="loadPipeline"
              />
              <template v-else>
                <n-alert v-if="activeAIDraftId" type="info" class="mb-4" data-testid="analysis-ai-adopted">
                  {{ $t("page.analysis.ai.adoptedHint") }}
                </n-alert>
                <n-form-item :label="$t('page.analysis.numericFields')" required>
                  <n-select v-model:value="numericFields" :options="numericOptions" multiple filterable :max="20" data-testid="analysis-numeric-fields" />
                </n-form-item>
                <n-form-item :label="$t('page.analysis.groupBy')">
                  <n-select v-model:value="groupBy" :options="scalarOptions" multiple filterable clearable :max="3" data-testid="analysis-group-by" />
                </n-form-item>
                <n-form-item :label="$t('page.analysis.missingPolicy')">
                  <n-select v-model:value="missingPolicy" :options="missingOptions" data-testid="analysis-missing-policy" />
                </n-form-item>
                <n-form-item :label="$t('page.analysis.charts.selector')">
                  <n-select v-model:value="chartType" :options="chartOptions" data-testid="analysis-chart-type" />
                  <template #feedback>
                    {{ $t("page.analysis.charts.selectorHint") }}
                  </template>
                </n-form-item>
                <n-collapse class="mb-4">
                  <n-collapse-item :title="$t('page.analysis.fieldFilters', { count: filters.length })" name="filters">
                    <div v-for="(filter, index) in filters" :key="filter.key" class="analysis-filter mb-3">
                      <n-select v-model:value="filter.field" :options="scalarOptions" :placeholder="$t('page.analysis.field')" :aria-label="$t('page.analysis.field')" />
                      <n-select v-model:value="filter.op" :options="operatorOptions(filter.field)" :aria-label="$t('page.analysis.operator')" />
                      <n-input
                        v-if="!['missing', 'present'].includes(filter.op)"
                        v-model:value="filter.valueText"
                        :type="filter.op === 'in' ? 'textarea' : 'text'"
                        :placeholder="filter.op === 'in' ? $t('page.analysis.valuesHint') : $t('page.analysis.value')"
                        :aria-label="$t('page.analysis.value')"
                      />
                      <n-button size="small" @click="filters.splice(index, 1)">
                        {{ $t("common.delete") }}
                      </n-button>
                    </div>
                    <n-button :disabled="filters.length >= 20" size="small" @click="addFilter">
                      {{ $t("page.analysis.addFilter") }}
                    </n-button>
                  </n-collapse-item>
                </n-collapse>
                <n-alert v-if="recipeError" type="warning" class="mb-4">
                  {{ recipeError }}
                </n-alert>
                <n-alert v-if="methodChanged" type="info" class="mb-4">
                  {{ $t("page.analysis.methodChanged") }}
                </n-alert>
                <div class="flex flex-wrap gap-2">
                  <n-button type="primary" :disabled="!recipe || !selection || selectionError || methodChanged" :loading="busy" data-testid="analysis-preview" @click="handlePreview">
                    {{ $t("page.analysis.preview") }}
                  </n-button>
                  <n-button v-if="activePipeline" :disabled="!recipe" @click="confirmSaveRevision">
                    {{ $t("page.analysis.saveRevision", { number: activePipeline.current_revision + 1 }) }}
                  </n-button>
                </div>
              </template>
            </template>
          </n-form>
          <n-empty v-if="!protocolId" :description="$t('page.analysis.chooseProtocol')" />
        </section>

        <div class="min-w-0 space-y-5">
          <section v-if="run" class="analysis-panel" data-testid="analysis-report">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="min-w-0">
                <h2 class="aira-type-section-title mb-1 mt-0">
                  {{ run.question || $t("page.analysis.report") }}
                </h2>
                <div class="aira-type-meta break-all">
                  {{ protocols.find(item => item.id === run?.protocol_id)?.name || run.protocol_id }}
                </div>
                <div class="aira-type-meta">
                  {{ formatTime(run.created_at) }} · {{ statusLabel(run.status) }}
                </div>
              </div>
              <div class="flex flex-wrap gap-2">
                <n-button v-if="builtinRun && (run.status === 'pending' || run.status === 'running')" size="small" @click="confirmCancel">
                  {{ $t("common.cancel") }}
                </n-button>
                <n-button v-if="run.status === 'succeeded'" size="small" data-testid="analysis-save-pipeline" @click="saveModal = true">
                  {{ $t("page.analysis.saveMethod") }}
                </n-button>
                <n-button size="small" data-testid="analysis-rerun" @click="prepareRerun">
                  {{ $t("page.analysis.rerun") }}
                </n-button>
                <n-button v-if="run.result" size="small" @click="downloadReport">
                  {{ $t("page.analysis.download") }}
                </n-button>
              </div>
            </div>
            <n-alert v-if="run.error" type="error" class="mt-4">
              {{ run.error }}
            </n-alert>
            <analysis-compute-report v-if="!builtinRun && projectInfo" :run-id="run.id" :project-id="projectInfo.id" @updated="handleComputeUpdated" />
            <n-alert v-if="builtinRun && (run.status === 'pending' || run.status === 'running')" type="info" class="mt-4">
              {{ $t("page.analysis.runningHint") }}
            </n-alert>
            <template v-if="builtinRun?.result">
              <p class="aira-type-body">
                {{ $t("page.analysis.countSummary", builtinRun.result.counts) }}
              </p>
              <n-alert type="info" class="mb-4">
                {{ $t("page.analysis.descriptiveOnly") }}
              </n-alert>
              <div v-if="builtinRun.result.warnings.length" class="mb-4 space-y-2">
                <n-alert v-for="(warning, index) in builtinRun.result.warnings" :key="index" type="warning">
                  {{ warningLabel(warning) }}
                </n-alert>
              </div>
              <analysis-result-charts :result="builtinRun.result" />
              <analysis-result-table :result="builtinRun.result" />
            </template>
            <analysis-ai-panel
              v-if="projectInfo && run.status === 'succeeded' && run.result"
              kind="interpretation" :protocol-id="run.protocol_id" :project-id="projectInfo.id"
              :selection="run.source_selection" :run="run"
              :available="Boolean(context?.ai_available && context.protocol_id === run.protocol_id)"
            />
            <analysis-publication-panel v-if="builtinRun?.status === 'succeeded'" :key="builtinRun.id" :analysis-id="builtinRun.id" />
            <n-collapse class="mt-4">
              <n-collapse-item :title="$t('page.analysis.provenance')" name="sources">
                <dl class="analysis-digests aira-type-meta">
                  <dt>{{ $t("page.analysis.engine") }}</dt><dd>{{ run.engine_version }}</dd>
                  <dt>{{ $t("page.analysis.sourceDigest") }}</dt><dd>{{ run.source_digest }}</dd>
                  <dt>{{ $t("page.analysis.recipeDigest") }}</dt><dd>{{ run.recipe_digest }}</dd>
                  <dt>{{ $t("page.analysis.resultDigest") }}</dt><dd>{{ run.result_digest || "—" }}</dd>
                </dl>
                <template v-if="run.ai_provenance?.request_id">
                  <h3 class="aira-type-label">
                    {{ $t("page.analysis.ai.provenance") }}
                  </h3>
                  <dl class="analysis-digests aira-type-meta">
                    <dt>{{ $t("page.analysis.ai.model") }}</dt><dd>{{ run.ai_provenance.model }}</dd>
                    <dt>ID</dt><dd>{{ run.ai_provenance.request_id }}</dd>
                    <dt>{{ $t("page.analysis.ai.inputDigest") }}</dt><dd>{{ run.ai_provenance.input_digest }}</dd>
                    <dt>{{ $t("page.analysis.ai.outputDigest") }}</dt><dd>{{ run.ai_provenance.output_digest }}</dd>
                  </dl>
                  <p class="aira-type-meta">
                    {{ run.ai_provenance.user_edited ? $t("page.analysis.ai.userEdited") : $t("page.analysis.ai.adoptedUnchanged") }}
                  </p>
                  <p v-if="run.ai_provenance.inherited" class="aira-type-meta">
                    {{ $t("page.analysis.ai.inheritedHint") }}
                  </p>
                </template>
                <div class="analysis-table-scroll" tabindex="0">
                  <table class="analysis-table">
                    <thead><tr><th>{{ $t("page.analysis.record") }}</th><th>{{ $t("common.version") }}</th><th>Protocol</th></tr></thead>
                    <tbody>
                      <tr v-for="source in run.source_snapshot?.records || []" :key="source.record_id">
                        <td>
                          <n-button text type="primary" @click="openSource(source)">
                            #{{ source.number }}
                          </n-button>
                        </td>
                        <td>{{ source.record_version }}</td><td>{{ source.protocol_version }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </n-collapse-item>
            </n-collapse>
          </section>

          <section v-if="computeApprovals.length" class="analysis-panel">
            <h2 class="aira-type-section-title mt-0">
              {{ $t("page.analysis.compute.myApprovals") }}
            </h2>
            <button v-for="item in computeApprovals" :key="item.analysis_id" class="analysis-history-item mb-2" data-testid="analysis-compute-approval-item" @click="openComputeApproval(item.analysis_id)">
              {{ item.question || $t("page.analysis.compute.approvalTitle") }}
            </button>
          </section>
          <section class="analysis-panel">
            <h2 class="aira-type-section-title mt-0">
              {{ $t("page.analysis.history") }}
            </h2>
            <n-empty v-if="!runs.length" :description="$t('page.analysis.noRuns')" />
            <div v-else class="space-y-2">
              <button v-for="item in runs" :key="item.id" class="analysis-history-item" @click="openRun(item.id)">
                <span class="aira-type-label">{{ item.question || $t("page.analysis.report") }}</span>
                <span class="aira-type-meta">{{ formatTime(item.created_at) }} · {{ statusLabel(item.status) }}</span>
              </button>
            </div>
          </section>
          <section class="analysis-panel">
            <h2 class="aira-type-section-title mt-0">
              {{ $t("page.analysis.savedMethods") }}
            </h2>
            <n-empty v-if="!pipelines.length" :description="$t('page.analysis.noMethods')" />
            <article v-for="item in pipelines" :key="item.id" class="mb-3">
              <button class="analysis-history-item mb-2" data-testid="analysis-pipeline-item" @click="loadPipeline(item.id)">
                <span class="aira-type-label">{{ item.title }}</span><span class="aira-type-meta">r{{ item.current_revision }} · {{ $t("page.workflowAnalysis.privateOnly") }} · {{ $t("page.analysis.loadMethod") }}</span>
              </button>
              <n-button size="small" data-testid="analysis-publish-method" @click="openMethodPublication(item.id)">
                {{ $t("page.workflowAnalysis.publishAction") }}
              </n-button>
            </article>
          </section>
        </div>
      </div>
    </n-spin>
    <analysis-method-publish-modal v-if="projectInfo" v-model:show="publishMethodVisible" :project-id="projectInfo.id" :project-name="projectInfo.name" :pipeline-id="publishPipelineId" />

    <n-modal v-model:show="previewVisible" preset="card" class="aira-dialog" style="--aira-dialog-width: 48rem" :title="$t('page.analysis.confirmTitle')" :mask-closable="false" :closable="!busy" data-testid="analysis-preview-dialog">
      <template v-if="preview">
        <n-alert v-if="loadError" type="error" class="mb-4">
          {{ loadError }}
        </n-alert>
        <n-alert type="info">
          {{ $t("page.analysis.destination", { project: preview.summary.project_name, protocol: preview.summary.protocol_name }) }}
        </n-alert>
        <p class="aira-type-body">
          {{ $t("page.analysis.countSummary", preview.summary.counts) }}
        </p>
        <div class="flex flex-wrap gap-2">
          <n-tag v-for="field in preview.summary.fields.filter(item => preview?.recipe.numeric_fields.includes(item.key))" :key="`${field.key}:${field.protocol_version}`">
            {{ fieldLabel(field) }} · {{ field.protocol_version }}
          </n-tag>
        </div>
        <dl class="analysis-digests aira-type-meta mt-4">
          <dt>{{ $t("page.analysis.groupBy") }}</dt><dd>{{ preview.recipe.group_by.join(" · ") || $t("page.analysis.allRecords") }}</dd>
          <dt>{{ $t("page.analysis.missingPolicy") }}</dt><dd>{{ $t(`page.analysis.missing.${preview.recipe.missing_policy}`) }}</dd>
          <dt>{{ $t("page.analysis.charts.selector") }}</dt><dd>{{ $t(`page.analysis.charts.types.${preview.recipe.chart}`) }}</dd>
          <dt>{{ $t("page.analysis.engine") }}</dt><dd>{{ preview.summary.engine_version }}</dd>
          <dt>{{ $t("page.analysis.recipeDigest") }}</dt><dd>{{ preview.recipe_digest }}</dd>
        </dl>
        <ul v-if="preview.recipe.filters.length" class="aira-type-meta pl-5">
          <li v-for="(filter, index) in preview.recipe.filters" :key="index">
            {{ filter.field }} · {{ $t(`page.analysis.operators.${filter.op}`) }} {{ filter.value === null ? "" : Array.isArray(filter.value) ? filter.value.join(" · ") : String(filter.value) }}
          </li>
        </ul>
        <div class="analysis-table-scroll mt-4" tabindex="0">
          <table class="analysis-table">
            <thead><tr><th>{{ $t("page.analysis.field") }}</th><th>{{ $t("page.analysis.statistics.count") }}</th><th>{{ $t("page.analysis.statistics.missing") }}</th><th>{{ $t("page.analysis.statistics.invalid") }}</th></tr></thead>
            <tbody>
              <tr v-for="(stats, key) in preview.summary.field_stats" :key="key">
                <th scope="row">
                  {{ key }}
                </th><td>{{ stats.count }}</td><td>{{ stats.missing }}</td><td>{{ stats.invalid }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <n-collapse class="mt-4">
          <n-collapse-item :title="$t('page.analysis.provenance')" name="preview-sources">
            <ul class="aira-type-meta max-h-48 overflow-auto pl-5">
              <li v-for="source in preview.summary.sources" :key="source.record_id">
                #{{ source.number }} · {{ $t("common.version") }} {{ source.record_version }} · Protocol {{ source.protocol_version }}
              </li>
            </ul>
          </n-collapse-item>
        </n-collapse>
        <p class="aira-type-meta">
          {{ $t("page.analysis.previewEffect") }}
        </p>
        <p class="aira-type-meta">
          {{ $t("page.analysis.expiresAt", { time: formatTime(preview.expires_at) }) }}
        </p>
        <n-alert v-for="(warning, index) in preview.summary.warnings" :key="index" type="warning" class="mt-2">
          {{ warningLabel(warning) }}
        </n-alert>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button :disabled="busy" @click="previewVisible = false">
            {{ $t("page.analysis.backToEdit") }}
          </n-button>
          <n-button type="primary" :loading="busy" data-testid="analysis-confirm" @click="handleConfirm">
            {{ $t("page.analysis.confirm") }}
          </n-button>
        </div>
      </template>
    </n-modal>

    <n-modal v-model:show="saveModal" preset="card" class="aira-dialog" style="--aira-dialog-width: 32rem" :title="$t('page.analysis.saveMethod')" :mask-closable="false" :closable="!busy">
      <n-alert type="info" class="mb-4">
        {{ $t("page.analysis.saveMethodHint") }}
      </n-alert>
      <n-alert v-if="loadError" type="error" class="mb-4">
        {{ loadError }}
      </n-alert>
      <n-input v-model:value="pipelineTitle" :maxlength="255" :placeholder="$t('page.analysis.methodTitle')" data-testid="analysis-method-title" />
      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button :disabled="busy" @click="saveModal = false">
            {{ $t("common.cancel") }}
          </n-button>
          <n-button type="primary" :disabled="!pipelineTitle.trim()" :loading="busy" data-testid="analysis-confirm-save-method" @click="saveMethod">
            {{ $t("common.save") }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import type { AnalysisAIRequest, AnalysisContext, AnalysisField, AnalysisFilter, AnalysisPipeline, AnalysisPreview, AnalysisRecipe, AnalysisRun, AnalysisScalar, AnalysisSelection, AnalysisSource, AnalysisWarning } from "@/service/api/analysis"
import type { AnalysisComputeSeed } from "@/service/api/analysis-compute"
import type { ProtocolModels } from "@airalogy/shared/types"
import { cancelAnalysis, consumeAnalysisSelectionTransfer, createAnalysis, createAnalysisPipeline, createAnalysisPipelineRevision, downloadAnalysis, fetchAnalysis, fetchAnalysisContext, fetchAnalysisPipeline, fetchProjectAnalyses, fetchProjectAnalysisPipelines, previewAnalysis } from "@/service/api/analysis"
import { fetchAnalysisComputeApprovals } from "@/service/api/analysis-compute"
import { fetchProtocols, getProtocolInfo } from "@/service/api/project-protocols"
import { useAuthStore } from "@/store/modules/auth"
import { canAdoptAnalysisDraft } from "@/utils/analysis-ai"
import { isBuiltinAnalysisRun, isComputeAnalysisRecipe } from "@/utils/analysis-compute"
import { analysisFieldType, parseAnalysisFieldOperand } from "@/utils/analysis-context"
import { isProjectAnalysis } from "@/utils/project-analysis"
import { useProjectInfoStore } from "@/views/project-protocols/hooks/useProjectInfoStore"
import { downloadAs } from "@airalogy/shared/utils"
import { useDialog, useMessage } from "naive-ui"
import { useI18n } from "vue-i18n"
import AnalysisAiPanel from "./components/analysis-ai-panel.vue"
import AnalysisComputeForm from "./components/analysis-compute-form.vue"
import AnalysisComputeReport from "./components/analysis-compute-report.vue"
import AnalysisMethodPublishModal from "./components/analysis-method-publish-modal.vue"
import AnalysisPublicationPanel from "./components/analysis-publication-panel.vue"
import AnalysisResultCharts from "./components/analysis-result-charts.vue"
import AnalysisResultTable from "./components/analysis-result-table.vue"
import ProjectAnalysisWorkbench from "./components/project-analysis-workbench.vue"

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const { projectInfo } = useProjectInfoStore()
const projectScope = computed(() => route.query.scope === "project")
async function changeAnalysisScope(project: boolean) {
  await router.replace({ name: "project-analysis", params: { labUid: route.params.labUid, projectUid: route.params.projectUid }, query: project ? { scope: "project" } : {} })
}
const message = useMessage()
const dialog = useDialog()
const protocols = ref<ProtocolModels.ProjectProtocolInfo[]>([])
const protocolId = ref<string | null>(null)
const context = ref<AnalysisContext | null>(null)
const contextLoading = ref(false)
const requestedSelection = ref<AnalysisSelection | null>(null)
const selection = ref<AnalysisSelection | null>(null)
const selectionError = ref(false)
const loading = ref(false)
const busy = ref(false)
const loadError = ref("")
const question = ref("")
const numericFields = ref<string[]>([])
const groupBy = ref<string[]>([])
const missingPolicy = ref<AnalysisRecipe["missing_policy"]>("exclude")
const chartType = ref<AnalysisRecipe["chart"]>("none")
const filters = ref<Array<{ key: number, field: string, op: AnalysisFilter["op"], valueText: string }>>([])
let filterCounter = 0
const preview = ref<AnalysisPreview | null>(null)
const previewVisible = ref(false)
const run = ref<AnalysisRun | null>(null)
const builtinRun = computed(() => run.value && isBuiltinAnalysisRun(run.value) ? run.value : null)
const analysisMode = ref<"builtin" | "compute">("builtin")
const analysisModeOptions = computed(() => (["builtin", "compute"] as const).map(value => ({ value, label: t(`page.analysis.compute.modes.${value}`) })))
const computeSeed = ref<AnalysisComputeSeed | null>(null)
const computeApprovals = ref<Awaited<ReturnType<typeof fetchAnalysisComputeApprovals>>["items"]>([])
const computeApprovalId = computed(() => typeof route.query.computeApproval === "string" ? route.query.computeApproval : "")
const runs = ref<AnalysisRun[]>([])
const pipelines = ref<AnalysisPipeline[]>([])
const publishMethodVisible = ref(false)
const publishPipelineId = ref<string | undefined>()
function openMethodPublication(id: string) {
  publishPipelineId.value = id
  publishMethodVisible.value = true
}
const activePipeline = ref<AnalysisPipeline | null>(null)
const pipelineRevisionId = ref<string | undefined>()
const activeAIDraftId = ref<string | undefined>()
const rerunOfId = ref<string | undefined>()
const saveModal = ref(false)
const pipelineTitle = ref("")
let sequence = 0
let initializationSequence = 0
let reportSequence = 0
let protocolSearchSequence = 0
let pollTimer: ReturnType<typeof setTimeout> | undefined
let confirmationKey = ""
let consumedSelectionToken = ""

const protocolOptions = computed(() => protocols.value.map(item => ({ label: item.name || item.uid, value: item.id })))
function scalarType(field?: AnalysisField) {
  return analysisFieldType(field)
}
function fieldLabel(field: AnalysisField) {
  return `${field.title || field.key}${field.unit ? ` (${field.unit})` : ""}`
}
const scalarFields = computed(() => context.value?.fields.filter(field => ["number", "integer", "string", "boolean"].includes(scalarType(field))) || [])
const scalarOptions = computed(() => scalarFields.value.map(field => ({ label: fieldLabel(field), value: field.key })))
const numericOptions = computed(() => scalarFields.value.filter(field => ["number", "integer"].includes(scalarType(field))).map(field => ({ label: fieldLabel(field), value: field.key })))
const missingOptions = computed(() => ["exclude", "error"].map(value => ({ value, label: t(`page.analysis.missing.${value}`) })))
const chartOptions = computed(() => (["bar", "line", "none"] as const).map(value => ({ value, label: t(`page.analysis.charts.types.${value}`) })))
function operatorOptions(field: string) {
  const numeric = ["number", "integer"].includes(scalarType(scalarFields.value.find(item => item.key === field)))
  return (numeric ? ["eq", "ne", "gt", "gte", "lt", "lte", "in", "missing", "present"] : ["eq", "ne", "in", "missing", "present"]).map(value => ({ value, label: t(`page.analysis.operators.${value}`) }))
}
function parseOperand(value: string, field: string): AnalysisScalar {
  try {
    return parseAnalysisFieldOperand(value, scalarFields.value.find(item => item.key === field))
  }
  catch (error) {
    throw new Error(t(error instanceof Error && error.message === "invalid_boolean_value" ? "page.analysis.booleanHint" : "page.analysis.invalidFilterValue"))
  }
}
const recipeState = computed<{ value: AnalysisRecipe | null, error: string }>(() => {
  if (!context.value || !selection.value || contextLoading.value || !numericFields.value.length)
    return { value: null, error: "" }
  try {
    if (numericFields.value.some(key => !numericOptions.value.some(field => field.value === key)) || groupBy.value.some(key => !scalarOptions.value.some(field => field.value === key)))
      throw new Error(t("page.analysis.invalidFilterValue"))
    const typedFilters = filters.value.map((filter): AnalysisFilter => {
      if (!filter.field || !scalarFields.value.some(field => field.key === filter.field) || !operatorOptions(filter.field).some(option => option.value === filter.op))
        throw new Error(t("page.analysis.invalidFilterValue"))
      const value = ["missing", "present"].includes(filter.op)
        ? null
        : filter.op === "in"
          ? filter.valueText.split("\n").map(item => parseOperand(item, filter.field))
          : parseOperand(filter.valueText, filter.field)
      return { field: filter.field, op: filter.op, value }
    })
    return { value: { schema_version: 1, numeric_fields: [...numericFields.value], group_by: [...groupBy.value], filters: typedFilters, missing_policy: missingPolicy.value, chart: chartType.value }, error: "" }
  }
  catch (error) {
    return { value: null, error: error instanceof Error ? error.message : t("page.analysis.invalidFilterValue") }
  }
})
const recipe = computed(() => recipeState.value.value)
const recipeError = computed(() => recipeState.value.error)
function recipeIdentity(value: AnalysisRecipe) {
  return JSON.stringify([value.schema_version, value.numeric_fields, value.group_by, value.filters.map(filter => [filter.field, filter.op, filter.value]), value.missing_policy, value.chart])
}
const methodChanged = computed(() => Boolean(activePipeline.value && !isComputeAnalysisRecipe(activePipeline.value.current_recipe) && recipe.value && recipeIdentity(activePipeline.value.current_recipe) !== recipeIdentity(recipe.value)))
function addFilter() {
  filters.value.push({ key: ++filterCounter, field: scalarFields.value[0]?.key || "", op: "eq", valueText: "" })
}
function errorText(error: unknown) {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === "string" ? detail : t("page.analysis.requestError")
}
function sourceFilterLabel(key: string) {
  return t(`page.analysis.sourceFilters.${key}`)
}
function statusLabel(status: AnalysisRun["status"]) {
  return t(`page.analysis.status.${status}`)
}
function formatTime(value: string) {
  return new Date(value).toLocaleString(locale.value)
}
function warningLabel(warning: AnalysisWarning) {
  return t(`page.analysis.warnings.${warning.code}`, { field: warning.field || "", count: warning.count })
}
async function useLatestRecords() {
  if (protocolId.value)
    await loadSelectionContext(protocolId.value, { mode: "latest", filters: {} })
}
async function retrySelectionContext() {
  if (protocolId.value && requestedSelection.value)
    await loadSelectionContext(protocolId.value, requestedSelection.value)
}
function applyRecipe(value: AnalysisRecipe) {
  numericFields.value = [...value.numeric_fields]
  groupBy.value = [...value.group_by]
  missingPolicy.value = value.missing_policy
  chartType.value = value.chart
  filters.value = value.filters.map(filter => ({ key: ++filterCounter, field: filter.field, op: filter.op, valueText: Array.isArray(filter.value) ? filter.value.map(String).join("\n") : filter.value === null ? "" : String(filter.value) }))
}
function adoptAIDraft(request: AnalysisAIRequest) {
  if (!protocolId.value || !projectInfo.value || !canAdoptAnalysisDraft(request, protocolId.value, projectInfo.value.id, selection.value) || !request.output || !("mode" in request.output) || request.output.mode !== "builtin" || !request.output.recipe)
    return
  applyRecipe(request.output.recipe)
  analysisMode.value = "builtin"
  question.value = request.question
  activePipeline.value = null
  pipelineRevisionId.value = undefined
  rerunOfId.value = undefined
  activeAIDraftId.value = request.id
  preview.value = null
  previewVisible.value = false
  message.info(t("page.analysis.ai.adoptedHint"))
}
function startManualAnalysis() {
  analysisMode.value = "builtin"
  activeAIDraftId.value = undefined
  activePipeline.value = null
  pipelineRevisionId.value = undefined
  rerunOfId.value = undefined
  applyRecipe({ schema_version: 1, numeric_fields: [], group_by: [], filters: [], missing_policy: "exclude", chart: "none" })
  preview.value = null
  previewVisible.value = false
}
function openAdvancedAnalysis() {
  // A capability request is not source code and never executes automatically.
  activeAIDraftId.value = undefined
  computeSeed.value = null
  analysisMode.value = "compute"
}
async function handleComputeCreated(id: string) {
  await openRun(id)
  await loadLists()
}
function handleComputeUpdated(updated: AnalysisRun) {
  if (run.value?.id === updated.id) {
    const changed = run.value.status !== updated.status
    run.value = updated
    if (changed)
      void loadLists()
  }
}
async function openComputeApproval(id: string) {
  await router.replace({ name: "project-analysis", params: { labUid: route.params.labUid, projectUid: route.params.projectUid }, query: { computeApproval: id } })
}
async function closeComputeApproval() {
  await router.replace({ name: "project-analysis", params: { labUid: route.params.labUid, projectUid: route.params.projectUid }, query: {} })
  await initialize()
}
async function loadLists() {
  if (!projectInfo.value)
    return
  const projectId = projectInfo.value.id
  const [history, methods] = await Promise.all([fetchProjectAnalyses(projectId), fetchProjectAnalysisPipelines(projectId)])
  if (projectInfo.value?.id !== projectId)
    return
  runs.value = history.items
  pipelines.value = methods.items
  try {
    const approvals = await fetchAnalysisComputeApprovals(projectId)
    if (projectInfo.value?.id === projectId)
      computeApprovals.value = approvals.items
  }
  catch {
    // Optional compute approvals must not block ordinary manual analysis.
    if (projectInfo.value?.id === projectId)
      computeApprovals.value = []
  }
}
async function refreshWorkspace() {
  loading.value = true
  loadError.value = ""
  try {
    await loadLists()
    if (run.value)
      await openRun(run.value.id, false)
  }
  catch (error) {
    loadError.value = errorText(error)
  }
  finally {
    loading.value = false
  }
}
function resetEditor() {
  analysisMode.value = "builtin"
  computeSeed.value = null
  sequence += 1
  context.value = null
  contextLoading.value = false
  requestedSelection.value = null
  selection.value = null
  preview.value = null
  selectionError.value = false
  activePipeline.value = null
  pipelineRevisionId.value = undefined
  activeAIDraftId.value = undefined
  rerunOfId.value = undefined
  numericFields.value = []
  groupBy.value = []
  filters.value = []
  question.value = ""
  missingPolicy.value = "exclude"
  chartType.value = "none"
  loadError.value = ""
}
async function selectProtocol(id: string | null, source: AnalysisSelection | null = { mode: "latest", filters: {} }) {
  resetEditor()
  if (!id || !source)
    return false
  return loadSelectionContext(id, source)
}
async function loadSelectionContext(id: string, source: AnalysisSelection) {
  const requestSequence = ++sequence
  const projectId = projectInfo.value?.id
  const snapshot = JSON.parse(JSON.stringify(source)) as AnalysisSelection
  requestedSelection.value = snapshot
  activeAIDraftId.value = undefined
  context.value = null
  selection.value = null
  preview.value = null
  previewVisible.value = false
  selectionError.value = false
  contextLoading.value = true
  loadError.value = ""
  try {
    const result = await fetchAnalysisContext(id, snapshot)
    if (requestSequence !== sequence || projectId !== projectInfo.value?.id || id !== protocolId.value)
      return false
    if (result.project_id !== projectId || result.protocol_id !== id)
      throw new Error("Analysis context scope mismatch")
    context.value = result
    selection.value = snapshot
    return true
  }
  catch (error) {
    if (requestSequence === sequence)
      loadError.value = errorText(error)
    return false
  }
  finally {
    if (requestSequence === sequence)
      contextLoading.value = false
  }
}
async function searchProtocols(name: string) {
  if (!projectInfo.value)
    return
  const querySequence = ++protocolSearchSequence
  const projectId = projectInfo.value.id
  try {
    const result = await fetchProtocols({ projectId, name: name.trim() || undefined, page: 1, pageSize: 100 })
    if (querySequence !== protocolSearchSequence || projectId !== projectInfo.value?.id)
      return
    if (result.error)
      throw result.error
    const selected = protocols.value.find(item => item.id === protocolId.value)
    const next = result.data?.protocols || []
    protocols.value = selected && !next.some(item => item.id === selected.id) ? [selected, ...next] : next
  }
  catch (error) {
    if (querySequence === protocolSearchSequence)
      loadError.value = errorText(error)
  }
}
async function initialize() {
  if (projectScope.value) {
    initializationSequence += 1
    reportSequence += 1
    sequence += 1
    if (pollTimer)
      clearTimeout(pollTimer)
    return
  }
  if (!projectInfo.value)
    return
  loading.value = true
  loadError.value = ""
  const initSequence = ++initializationSequence
  const projectId = projectInfo.value.id
  reportSequence += 1
  run.value = null
  runs.value = []
  pipelines.value = []
  context.value = null
  selection.value = null
  requestedSelection.value = null
  contextLoading.value = false
  sequence += 1
  if (pollTimer)
    clearTimeout(pollTimer)
  try {
    if (computeApprovalId.value)
      return
    const result = await fetchProtocols({ projectId, page: 1, pageSize: 100 })
    if (initSequence !== initializationSequence || projectId !== projectInfo.value?.id)
      return
    if (result.error)
      throw result.error
    protocols.value = result.data?.protocols || []
    await loadLists()
    if (initSequence !== initializationSequence)
      return
    const requested = typeof route.query.protocolId === "string" ? route.query.protocolId : protocols.value.length === 1 ? protocols.value[0].id : null
    protocolId.value = requested
    const token = typeof route.query.selectionToken === "string" ? route.query.selectionToken : ""
    const inheritedSelection = token
      ? requested && consumedSelectionToken !== token
        ? consumeAnalysisSelectionTransfer(token, { userId: auth.userInfo.id, projectId, protocolId: requested })
        : null
      : { mode: "latest" as const, filters: {} }
    if (token)
      consumedSelectionToken = token
    // Resolve scope before requesting fields: an expired selection must never
    // load the all-Records catalogue or trigger an unrequested scope expansion.
    await selectProtocol(requested, inheritedSelection)
    if (initSequence !== initializationSequence)
      return
    selectionError.value = Boolean(token && !inheritedSelection)
    if (typeof route.query.runId === "string")
      await openRun(route.query.runId, false)
  }
  catch (error) {
    if (initSequence === initializationSequence)
      loadError.value = errorText(error)
  }
  finally {
    if (initSequence === initializationSequence)
      loading.value = false
  }
}
async function handlePreview() {
  if (!protocolId.value || !recipe.value || !selection.value || busy.value || methodChanged.value)
    return
  busy.value = true
  loadError.value = ""
  try {
    preview.value = await previewAnalysis({ protocol_id: protocolId.value, selection: selection.value, recipe: recipe.value, question: question.value, pipeline_revision_id: pipelineRevisionId.value, rerun_of_id: rerunOfId.value, ai_draft_id: activeAIDraftId.value })
    confirmationKey = `analysis-${Date.now()}-${Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, "0")).join("")}`
    previewVisible.value = true
  }
  catch (error) {
    loadError.value = errorText(error)
  }
  finally {
    busy.value = false
  }
}
async function handleConfirm() {
  if (!preview.value || busy.value)
    return
  busy.value = true
  try {
    const created = await createAnalysis({ preview_id: preview.value.id, preview_digest: preview.value.preview_digest, client_idempotency_key: confirmationKey })
    previewVisible.value = false
    await openRun(created.id)
    await loadLists()
  }
  catch (error) {
    loadError.value = errorText(error)
    if ((error as { response?: { status?: number } })?.response?.status === 409) {
      previewVisible.value = false
      preview.value = null
      message.warning(t("page.analysis.stalePreview"))
    }
  }
  finally {
    busy.value = false
  }
}
async function openRun(id: string, updateRoute = true) {
  const requestSequence = ++reportSequence
  const projectId = projectInfo.value?.id
  if (pollTimer)
    clearTimeout(pollTimer)
  try {
    const fetched = await fetchAnalysis(id)
    if (requestSequence !== reportSequence || projectId !== projectInfo.value?.id)
      return
    if (fetched.project_id !== projectId)
      throw new Error("Analysis report scope mismatch")
    if (isProjectAnalysis(fetched)) {
      run.value = null
      await router.replace({ name: "project-analysis", params: { labUid: route.params.labUid, projectUid: route.params.projectUid }, query: { scope: "project", runId: fetched.id } })
      return
    }
    run.value = fetched
    if (updateRoute)
      await router.replace({ name: "project-analysis", params: { labUid: route.params.labUid, projectUid: route.params.projectUid }, query: { protocolId: fetched.protocol_id, runId: fetched.id } })
    if (isBuiltinAnalysisRun(fetched) && ["pending", "running"].includes(fetched.status)) {
      pollTimer = setTimeout(() => {
        if (run.value?.id === id)
          void openRun(id, false)
      }, 2000)
    }
  }
  catch (error) {
    if (requestSequence === reportSequence) {
      run.value = null
      loadError.value = errorText(error)
    }
  }
}
async function prepareRerun() {
  if (!run.value)
    return
  const source = run.value
  protocolId.value = source.protocol_id
  resetEditor()
  if (isComputeAnalysisRecipe(source.recipe)) {
    analysisMode.value = "compute"
    computeSeed.value = { recipe: source.recipe, rerunOfId: source.id }
  }
  else {
    applyRecipe(source.recipe)
  }
  question.value = source.question
  rerunOfId.value = source.id
  // Preserve the saved selection rules; only explicit user action may broaden them.
  if (await loadSelectionContext(source.protocol_id, source.source_selection))
    message.info(t("page.analysis.rerunHint"))
}
async function loadPipeline(id: string) {
  const requestSequence = ++sequence
  const projectId = projectInfo.value?.id
  context.value = null
  selection.value = null
  requestedSelection.value = null
  preview.value = null
  previewVisible.value = false
  activePipeline.value = null
  pipelineRevisionId.value = undefined
  contextLoading.value = true
  try {
    const saved = await fetchAnalysisPipeline(id)
    if (requestSequence !== sequence || projectId !== projectInfo.value?.id)
      return
    if (saved.project_id !== projectId)
      throw new Error("Analysis method scope mismatch")
    protocolId.value = saved.protocol_id
    resetEditor()
    activePipeline.value = saved
    const currentRevision = saved.revisions?.find(item => item.revision === saved.current_revision)
    pipelineRevisionId.value = currentRevision?.id
    if (isComputeAnalysisRecipe(saved.current_recipe)) {
      analysisMode.value = "compute"
      computeSeed.value = { recipe: saved.current_recipe, pipeline: saved, pipelineRevisionId: currentRevision?.id }
      activePipeline.value = null
    }
    else {
      applyRecipe(saved.current_recipe)
    }
    if (!currentRevision) {
      selectionError.value = true
      return
    }
    if (await loadSelectionContext(saved.protocol_id, currentRevision.source_selection))
      message.info(t("page.analysis.rerunHint"))
  }
  catch (error) {
    if (requestSequence === sequence)
      loadError.value = errorText(error)
  }
  finally {
    if (requestSequence === sequence)
      contextLoading.value = false
  }
}
async function saveMethod() {
  if (!run.value || run.value.status !== "succeeded" || !pipelineTitle.value.trim() || busy.value)
    return
  busy.value = true
  try {
    await createAnalysisPipeline({ run_id: run.value.id, title: pipelineTitle.value.trim() })
    saveModal.value = false
    pipelineTitle.value = ""
    await loadLists()
    message.success(t("page.analysis.methodSaved"))
  }
  catch (error) {
    loadError.value = errorText(error)
  }
  finally {
    busy.value = false
  }
}
function confirmSaveRevision() {
  const pipeline = activePipeline.value
  const updated = recipe.value
  if (!pipeline || !updated)
    return
  dialog.warning({ title: t("page.analysis.saveRevision", { number: pipeline.current_revision + 1 }), content: t("page.analysis.revisionHint"), positiveText: t("common.confirm"), negativeText: t("common.cancel"), onPositiveClick: async () => {
    try {
      await createAnalysisPipelineRevision(pipeline.id, { recipe: updated, expected_revision: pipeline.current_revision, source_selection: selection.value || undefined })
      await loadPipeline(pipeline.id)
      await loadLists()
      message.success(t("page.analysis.methodSaved"))
    }
    catch (error) {
      loadError.value = errorText(error)
    }
  } })
}
function confirmCancel() {
  const current = run.value
  if (!current)
    return
  dialog.warning({ title: t("page.analysis.cancelTitle"), content: t("page.analysis.cancelHint"), positiveText: t("common.confirm"), negativeText: t("common.cancel"), onPositiveClick: async () => {
    try {
      await cancelAnalysis(current.id)
      await openRun(current.id)
      await loadLists()
    }
    catch (error) {
      loadError.value = errorText(error)
    }
  } })
}
async function downloadReport() {
  if (!run.value)
    return
  try {
    // Reauthorize immediately before export; do not export stale cached data.
    const fresh = await downloadAnalysis(run.value.id)
    downloadAs(JSON.stringify(fresh, null, 2), `analysis-${fresh.id}.json`, "application/json")
  }
  catch (error) {
    loadError.value = errorText(error)
  }
}
async function openSource(source: AnalysisSource) {
  const currentRun = run.value
  const currentProject = projectInfo.value
  if (!currentRun || !currentProject)
    return
  try {
    let protocol = protocols.value.find(item => item.id === currentRun.protocol_id)
    if (!protocol) {
      const result = await getProtocolInfo(currentRun.protocol_id)
      if (result.error || !result.data)
        throw result.error || new Error("Protocol unavailable")
      protocol = result.data
    }
    if (currentProject.id !== projectInfo.value?.id)
      return
    await router.push({ name: "protocol-record-report", params: { labUid: route.params.labUid, projectUid: route.params.projectUid, protocolUid: protocol.uid, protocolVersion: source.protocol_version, recordId: source.record_id, recordVersion: String(source.record_version) } })
  }
  catch (error) {
    loadError.value = errorText(error)
  }
}
watch(() => [projectInfo.value?.id, projectScope.value], () => void initialize(), { immediate: true })
onBeforeUnmount(() => {
  sequence += 1
  initializationSequence += 1
  reportSequence += 1
  protocolSearchSequence += 1
  if (pollTimer)
    clearTimeout(pollTimer)
})
</script>

<style scoped>
.analysis-grid { display: grid; grid-template-columns: minmax(0, 23rem) minmax(0, 1fr); gap: 1.25rem; align-items: start; }
.analysis-panel { min-width: 0; padding: 1.25rem; border: 1px solid #e5e7eb; border-radius: 1rem; background: white; }
.analysis-scope { padding: 1rem; border-radius: .75rem; background: #f7f9fc; overflow-wrap: anywhere; }
.analysis-filter { display: grid; gap: .5rem; padding: .75rem; border: 1px solid #e5e7eb; border-radius: .5rem; }
.analysis-table-scroll { max-width: 100%; overflow: auto; }
.analysis-table { width: 100%; border-collapse: collapse; font-size: .8125rem; text-align: left; }
.analysis-table th, .analysis-table td { padding: .65rem .75rem; border-bottom: 1px solid #e5e7eb; white-space: nowrap; }
.analysis-table th { font-weight: 600; }
.analysis-history-item { display: flex; width: 100%; gap: .4rem; flex-direction: column; text-align: left; padding: .75rem; border: 1px solid #e5e7eb; border-radius: .5rem; background: #fff; overflow-wrap: anywhere; cursor: pointer; }
.analysis-history-item:hover { background: #f7f9fc; }
.analysis-history-item:focus-visible { outline: 2px solid #0084e2; outline-offset: 2px; }
.analysis-digests { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: .5rem; }
.analysis-digests dd { margin: 0; overflow-wrap: anywhere; }
@media (max-width: 1100px) { .analysis-grid { grid-template-columns: minmax(0, 1fr); } }
@media (max-width: 600px) { .analysis-panel { padding: 1rem; } .analysis-digests { grid-template-columns: minmax(0, 1fr); } }
</style>
