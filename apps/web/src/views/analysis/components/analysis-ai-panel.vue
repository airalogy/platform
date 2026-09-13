<template>
  <section v-if="available || history.length || current || pending" class="analysis-ai-panel" :data-testid="`analysis-ai-${kind}`">
    <h3 class="aira-type-label mt-0">
      {{ t(`page.analysis.ai.${labelKind}Title`) }}
    </h3>
    <template v-if="available && !disabledByServer">
      <n-input v-if="kind === 'interpretation'" v-model:value="interpretationQuestion" type="textarea" :maxlength="4000" :autosize="{ minRows: 2, maxRows: 4 }" :placeholder="t('page.analysis.ai.interpretationQuestion')" :aria-label="t('page.analysis.ai.interpretationQuestion')" data-testid="analysis-ai-interpretation-question" />
      <n-alert v-if="previousId" type="info" class="my-3">
        {{ t("page.analysis.ai.followupHint") }}
      </n-alert>
      <label class="analysis-ai-consent my-3">
        <n-checkbox v-model:checked="consent" :disabled="working" :aria-label="t(`page.analysis.ai.${labelKind}Disclosure`)" :data-testid="`analysis-ai-${kind}-consent`" />
        <span class="aira-type-meta">{{ t(`page.analysis.ai.${labelKind}Disclosure`) }}</span>
      </label>
      <div class="flex flex-wrap gap-2">
        <n-button :disabled="!canGenerate" :loading="busy" :data-testid="`analysis-ai-${kind}-generate`" @click="generate">
          {{ t(`page.analysis.ai.${labelKind}Generate`) }}
        </n-button>
        <n-button v-if="kind === 'draft'" size="small" :disabled="busy" @click="startManual">
          {{ t("page.analysis.ai.startManual") }}
        </n-button>
      </div>
    </template>
    <p v-if="working" class="aira-type-meta" role="status">
      {{ t("page.analysis.ai.generating") }}
    </p>
    <n-alert v-if="errorMessage" type="warning" class="mt-3" :data-testid="`analysis-ai-${kind}-error`">
      {{ errorMessage }}
    </n-alert>
    <div v-if="uncertain && recoveryId" class="mt-3 flex flex-wrap gap-2">
      <n-button size="small" :disabled="busy" :data-testid="`analysis-ai-${kind}-recover`" @click="recover">
        {{ t("page.analysis.ai.recover") }}
      </n-button>
      <n-button v-if="pending && available && !disabledByServer" size="small" :disabled="busy || !consent" @click="submitPending">
        {{ t("page.analysis.ai.retrySame") }}
      </n-button>
    </div>
    <article v-if="current" class="analysis-ai-output mt-3" :data-testid="`analysis-ai-${kind}-output`">
      <div class="aira-type-meta">
        {{ formatTime(current.created_at) }} · {{ current.model }} · {{ t(`page.analysis.ai.states.${current.state}`) }}
      </div>
      <p v-if="current.question" class="aira-type-body analysis-ai-prose">
        {{ current.question }}
      </p>
      <n-alert v-if="current.state === 'failed'" type="warning">
        {{ safeError(current.error) }}
      </n-alert>
      <template v-if="draft">
        <h4 class="aira-type-label">
          {{ draft.title }}
        </h4>
        <p class="aira-type-body analysis-ai-prose">
          {{ draft.explanation }}
        </p>
        <n-alert type="info" class="mb-3">
          {{ t("page.analysis.ai.draftNotExecuted") }}
        </n-alert>
        <template v-if="draft.assumptions.length">
          <h4 class="aira-type-label">
            {{ t("page.analysis.ai.assumptions") }}
          </h4>
          <ul class="aira-type-body">
            <li v-for="(item, index) in draft.assumptions" :key="index">
              {{ item }}
            </li>
          </ul>
        </template>
        <template v-if="draft.mode === 'compute' && draft.recipe">
          <dl class="analysis-ai-recipe aira-type-meta">
            <dt>{{ t('page.analysis.compute.environment') }}</dt><dd>{{ draft.recipe.environment_revision_id }}</dd><dt>{{ t('page.analysis.compute.language') }}</dt><dd>{{ draft.recipe.language }}</dd>
          </dl>
          <pre tabindex="0" :aria-label="t('page.analysis.compute.source')">{{ draft.recipe.source_code }}</pre>
          <details>
            <summary class="aira-type-meta">
              {{ t('page.analysis.ai.computeDraftDetails') }}
            </summary><pre tabindex="0">{{ JSON.stringify({ parameters: draft.recipe.parameters, output_files: draft.recipe.output_files }, null, 2) }}</pre>
          </details>
          <n-button :disabled="!canAdopt || working" class="mt-3" data-testid="analysis-ai-compute-adopt" @click="$emit('adopt', current)">
            {{ t('page.analysis.ai.adopt') }}
          </n-button>
          <p v-if="!canAdopt" class="aira-type-meta">
            {{ t('page.analysis.ai.computeScopeMismatch') }}
          </p>
        </template>
        <template v-if="draft.mode === 'builtin' && draft.recipe">
          <dl class="analysis-ai-recipe aira-type-meta">
            <dt>{{ t("page.analysis.numericFields") }}</dt><dd>{{ draft.recipe.numeric_fields.join(" · ") }}</dd>
            <dt>{{ t("page.analysis.groupBy") }}</dt><dd>{{ draft.recipe.group_by.join(" · ") || t("page.analysis.allRecords") }}</dd>
            <dt>{{ t("page.analysis.missingPolicy") }}</dt><dd>{{ t(`page.analysis.missing.${draft.recipe.missing_policy}`) }}</dd>
            <dt>{{ t("page.analysis.charts.selector") }}</dt><dd>{{ t(`page.analysis.charts.types.${draft.recipe.chart}`) }}</dd>
          </dl>
          <ul v-if="draft.recipe.filters.length" class="aira-type-meta">
            <li v-for="(filter, index) in draft.recipe.filters" :key="index">
              {{ filter.field }} · {{ t(`page.analysis.operators.${filter.op}`) }} {{ filter.value === null ? "" : Array.isArray(filter.value) ? filter.value.join(" · ") : String(filter.value) }}
            </li>
          </ul>
          <n-button :disabled="!canAdopt || working" data-testid="analysis-ai-adopt" @click="$emit('adopt', current)">
            {{ t("page.analysis.ai.adopt") }}
          </n-button>
          <p v-if="!canAdopt" class="aira-type-meta">
            {{ t("page.analysis.ai.scopeMismatch") }}
          </p>
        </template>
        <template v-if="draft.mode === 'clarification_required'">
          <h4 class="aira-type-label">
            {{ t("page.analysis.ai.clarification") }}
          </h4>
          <ul class="aira-type-body">
            <li v-for="(item, index) in draft.clarification_questions" :key="index">
              {{ item }}
            </li>
          </ul>
        </template>
        <template v-if="draft.mode === 'compute_required'">
          <n-alert type="warning" class="mb-3">
            {{ t("page.analysis.ai.computeRequired") }}
          </n-alert>
          <ul v-if="'compute_requirements' in draft" class="aira-type-body">
            <li v-for="(item, index) in draft.compute_requirements" :key="index">
              {{ item }}
            </li>
          </ul>
          <n-button size="small" @click="$emit('researchTask')">
            {{ t("page.analysis.compute.openAdvanced") }}
          </n-button>
        </template>
        <n-button v-if="available && !disabledByServer" class="mt-3" size="small" :disabled="working" data-testid="analysis-ai-followup" @click="previousId = current.id">
          {{ t("page.analysis.ai.followup") }}
        </n-button>
      </template>
      <n-alert v-if="groundingRejected" type="error" class="my-3" data-testid="analysis-ai-grounding-rejected">
        {{ t('page.analysis.ai.groundingRejected') }}
      </n-alert>
      <template v-if="interpretation && run?.result">
        <n-alert type="info" class="my-3">
          {{ t("page.analysis.ai.interpretationDisclaimer") }}
        </n-alert>
        <p class="aira-type-body analysis-ai-prose">
          {{ interpretation.summary }}
        </p>
        <article v-for="(observation, index) in interpretation.observations" :key="index" class="mb-3">
          <p class="aira-type-body analysis-ai-prose">
            {{ observation.text }}
          </p>
          <ul class="aira-type-meta">
            <li v-for="(metric, metricIndex) in observation.metrics" :key="metricIndex" data-testid="analysis-ai-metric">
              {{ metricLabel(metric) }}
            </li>
          </ul>
        </article>
        <h4 v-if="interpretation.limitations.length" class="aira-type-label">
          {{ t("page.analysis.ai.limitations") }}
        </h4>
        <ul class="aira-type-body">
          <li v-for="(item, index) in interpretation.limitations" :key="index">
            {{ item }}
          </li>
        </ul>
        <h4 v-if="interpretation.next_steps.length" class="aira-type-label">
          {{ t("page.analysis.ai.nextSteps") }}
        </h4>
        <ul class="aira-type-body">
          <li v-for="(item, index) in interpretation.next_steps" :key="index">
            {{ item }}
          </li>
        </ul>
      </template>
      <details class="mt-3">
        <summary class="aira-type-meta">
          {{ t("page.analysis.ai.provenance") }}
        </summary>
        <dl class="analysis-ai-recipe aira-type-meta">
          <dt>ID</dt><dd>{{ current.id }}</dd><dt>{{ t("page.analysis.ai.inputDigest") }}</dt><dd>{{ current.input_digest }}</dd><dt>{{ t("page.analysis.ai.outputDigest") }}</dt><dd>{{ current.output_digest || "—" }}</dd>
        </dl>
      </details>
    </article>
    <details v-if="history.length" class="mt-3" :open="!current">
      <summary class="aira-type-meta">
        {{ t("page.analysis.ai.history", { count: history.length }) }}
      </summary>
      <div class="analysis-ai-history mt-2">
        <button v-for="item in history" :key="item.id" type="button" :disabled="busy || Boolean(pending)" @click="openHistory(item.id)">
          <span class="aira-type-meta">{{ formatTime(item.created_at) }} · {{ t(`page.analysis.ai.states.${item.state}`) }}</span><span>{{ item.question || t("page.analysis.ai.interpretationTitle") }}</span>
        </button>
      </div>
    </details>
  </section>
</template>

<script setup lang="ts">
import type { AnalysisAIComputeDraftRequest, AnalysisAIDraftRequest, AnalysisAIInterpretationRequest, AnalysisAIRequest, AnalysisComputeMetric, AnalysisGroundedMetric, AnalysisRun, AnalysisSelection } from "@/service/api/analysis"
import { createAnalysisAIComputeDraft, createAnalysisAIDraft, createAnalysisAIInterpretation, fetchAnalysisAIComputeDrafts, fetchAnalysisAIDrafts, fetchAnalysisAIInterpretations, fetchAnalysisAIRequest } from "@/service/api/analysis"
import { analysisSelectionIdentity, canAdoptAnalysisComputeDraft, canAdoptAnalysisDraft, createAnalysisAIRequestId, resolveAnalysisComputeMetric, resolveAnalysisMetric, shouldRecoverAnalysisAIRequest } from "@/utils/analysis-ai"
import { useI18n } from "vue-i18n"

const props = defineProps<{ kind: "draft" | "compute_draft" | "interpretation", protocolId: string, projectId: string, selection: AnalysisSelection | null, question?: string, available: boolean, run?: AnalysisRun, environmentRevisionId?: string, language?: "python" | "r" }>()
const emit = defineEmits<{ adopt: [request: AnalysisAIRequest], manual: [], researchTask: [] }>()
const { t, locale } = useI18n()
const consent = ref(false)
const busy = ref(false)
const uncertain = ref(false)
const disabledByServer = ref(false)
const errorMessage = ref("")
const current = ref<AnalysisAIRequest | null>(null)
const history = ref<AnalysisAIRequest[]>([])
const previousId = ref<string | undefined>()
const interpretationQuestion = ref("")
type PendingRequest = { kind: "draft", payload: AnalysisAIDraftRequest } | { kind: "compute_draft", payload: AnalysisAIComputeDraftRequest } | { kind: "interpretation", runId: string, payload: AnalysisAIInterpretationRequest }
const pending = ref<PendingRequest | null>(null)
let scopeVersion = 0
let requestVersion = 0
let pollTimer: ReturnType<typeof setTimeout> | undefined
const working = computed(() => busy.value || Boolean(pending.value) || current.value?.state === "generating")
const labelKind = computed(() => props.kind === "compute_draft" ? "computeDraft" : props.kind === "interpretation" && props.run?.result && "computed_result" in props.run.result ? "computeInterpretation" : props.kind)
const recoveryId = computed(() => pending.value?.payload.id || (current.value?.state === "generating" ? current.value.id : ""))
const canGenerate = computed(() => props.available && !disabledByServer.value && consent.value && !working.value && (props.kind === "interpretation" ? props.run?.status === "succeeded" : Boolean(props.selection && props.question?.trim() && (props.kind !== "compute_draft" || (props.environmentRevisionId && props.language)))))
const draft = computed(() => current.value?.state === "generated" && current.value.output && "mode" in current.value.output ? current.value.output : null)
const rawInterpretation = computed(() => current.value?.state === "generated" && current.value.output && "summary" in current.value.output ? current.value.output : null)
const groundingRejected = computed(() => {
  const output = rawInterpretation.value
  const result = props.run?.result
  if (!output || !result)
    return false
  if (output.result_kind === "compute")
    return !("computed_result" in result) || output.observations.some(item => item.metrics.some(metric => !resolveAnalysisComputeMetric(metric, result.computed_result)))
  return !("groups" in result) || output.observations.some(item => item.metrics.some(metric => !resolveAnalysisMetric(metric, result)))
})
const interpretation = computed(() => groundingRejected.value ? null : rawInterpretation.value)
const canAdopt = computed(() => Boolean(current.value && (props.kind === "compute_draft" ? canAdoptAnalysisComputeDraft(current.value, props.protocolId, props.projectId, props.selection, props.environmentRevisionId, props.language) : canAdoptAnalysisDraft(current.value, props.protocolId, props.projectId, props.selection))))

function formatTime(value: string) {
  return new Date(value).toLocaleString(locale.value)
}
function safeError(code: AnalysisAIRequest["error"]) {
  return t(`page.analysis.ai.errors.${code || "generation_interrupted"}`)
}
function httpError(error: unknown) {
  const status = (error as { response?: { status?: number } })?.response?.status
  if (status === 403 || status === 404)
    return safeError("source_access_changed")
  if (status === 409)
    return safeError("context_changed")
  if (status === 422)
    return t("page.analysis.ai.invalidRequest")
  if (status === 503)
    return safeError("model_unavailable")
  return t("page.analysis.ai.uncertain")
}
function clearTimer() {
  if (pollTimer)
    clearTimeout(pollTimer)
  pollTimer = undefined
}
function storeResponse(value: AnalysisAIRequest) {
  if (value.project_id !== props.projectId || value.protocol_id !== props.protocolId || value.kind !== props.kind || (props.kind === "interpretation" && value.analysis_run_id !== props.run?.id))
    throw new Error("Analysis AI scope mismatch")
  current.value = value
  history.value = [value, ...history.value.filter(item => item.id !== value.id)]
  pending.value = null
  uncertain.value = false
  errorMessage.value = ""
  if (value.error === "ai_disabled" || value.error === "model_unavailable")
    disabledByServer.value = true
  clearTimer()
  if (value.state === "generating")
    pollTimer = setTimeout(() => void recover(), 2500)
}
async function recover() {
  const id = recoveryId.value
  if (!id || busy.value)
    return
  const version = scopeVersion
  busy.value = true
  try {
    const response = await fetchAnalysisAIRequest(id)
    if (version === scopeVersion)
      storeResponse(response)
  }
  catch (error) {
    if (version === scopeVersion) {
      uncertain.value = true
      errorMessage.value = (error as { response?: { status?: number } })?.response?.status === 404 ? t("page.analysis.ai.notFoundYet") : httpError(error)
    }
  }
  finally {
    if (version === scopeVersion)
      busy.value = false
  }
}
async function generate() {
  if (!canGenerate.value)
    return
  previousId.value = props.kind !== "interpretation" ? previousId.value : undefined
  const language: "zh-CN" | "en-US" = locale.value.toLowerCase().startsWith("zh") ? "zh-CN" : "en-US"
  const id = createAnalysisAIRequestId()
  const draftPayload = { id, protocol_id: props.protocolId, selection: JSON.parse(JSON.stringify(props.selection)) as AnalysisSelection, question: props.question?.trim() || "", locale: language, previous_request_id: previousId.value }
  pending.value = props.kind === "draft"
    ? { kind: "draft", payload: draftPayload }
    : props.kind === "compute_draft"
      ? { kind: "compute_draft", payload: { ...draftPayload, environment_revision_id: props.environmentRevisionId!, language: props.language! } }
      : { kind: "interpretation", runId: props.run!.id, payload: { id, question: interpretationQuestion.value.trim() || undefined, locale: language } }
  await submitPending()
}
async function submitPending() {
  const attempt = pending.value
  if (!attempt || busy.value)
    return
  const version = scopeVersion
  clearTimer()
  busy.value = true
  errorMessage.value = ""
  current.value = null
  try {
    const response = attempt.kind === "draft" ? await createAnalysisAIDraft(attempt.payload) : attempt.kind === "compute_draft" ? await createAnalysisAIComputeDraft(attempt.payload) : await createAnalysisAIInterpretation(attempt.runId, attempt.payload)
    if (version === scopeVersion)
      storeResponse(response)
  }
  catch (error) {
    if (version === scopeVersion) {
      errorMessage.value = httpError(error)
      if ((error as { response?: { status?: number } })?.response?.status === 503)
        disabledByServer.value = true
      uncertain.value = shouldRecoverAnalysisAIRequest(error)
      if (!uncertain.value) {
        // An explicit rejection permits an edited question and a new, user-led
        // attempt. Do not poll an id that was rejected before generation.
        pending.value = null
        current.value = null
      }
      // Otherwise retain the same id: a timed-out request may still be working.
    }
  }
  finally {
    if (version === scopeVersion) {
      busy.value = false
      if (uncertain.value)
        void recover()
    }
  }
}
async function openHistory(id: string) {
  const version = scopeVersion
  const request = ++requestVersion
  clearTimer()
  current.value = null
  busy.value = true
  try {
    const response = await fetchAnalysisAIRequest(id)
    if (version === scopeVersion && request === requestVersion)
      storeResponse(response)
  }
  catch (error) {
    if (version === scopeVersion && request === requestVersion) {
      history.value = history.value.filter(item => item.id !== id)
      errorMessage.value = httpError(error)
    }
  }
  finally {
    if (version === scopeVersion && request === requestVersion)
      busy.value = false
  }
}
function startManual() {
  previousId.value = undefined
  emit("manual")
}
function metricLabel(metric: AnalysisGroundedMetric | AnalysisComputeMetric) {
  const result = props.run?.result
  if ("pointer" in metric) {
    const resolved = result && "computed_result" in result && resolveAnalysisComputeMetric(metric, result.computed_result)
    if (!resolved)
      return t("page.analysis.ai.metricUnavailable")
    // No inferred measurement units, sample sizes, rounding or model numbers.
    return `${resolved.pointer}: ${JSON.stringify(resolved.value)}`
  }
  const resolved = result && "groups" in result && resolveAnalysisMetric(metric, result)
  if (!resolved)
    return t("page.analysis.ai.metricUnavailable")
  const group = resolved.group.length ? resolved.group.map(item => `${item.field}: ${item.value === null ? t("page.analysis.missingGroup") : String(item.value)}`).join(" · ") : t("page.analysis.allRecords")
  const value = resolved.value === null ? "—" : resolved.value.toLocaleString(locale.value, { maximumSignificantDigits: 8 })
  const statistic = resolved.statistic === "sum" ? t("page.analysis.ai.sum") : t(`page.analysis.statistics.${resolved.statistic}`)
  return `${group} · ${resolved.field} · ${statistic}: ${value}${resolved.unit ? ` ${resolved.unit}` : ""} · n = ${resolved.n}`
}
watch(() => [props.kind, props.protocolId, props.projectId, props.run?.id, props.environmentRevisionId, props.language, analysisSelectionIdentity(props.selection)], async () => {
  const version = ++scopeVersion
  requestVersion += 1
  clearTimer()
  busy.value = false
  uncertain.value = false
  consent.value = false
  disabledByServer.value = false
  pending.value = null
  current.value = null
  history.value = []
  previousId.value = undefined
  errorMessage.value = ""
  try {
    const response = props.kind === "draft" ? await fetchAnalysisAIDrafts(props.protocolId) : props.kind === "compute_draft" ? await fetchAnalysisAIComputeDrafts(props.protocolId) : props.run ? await fetchAnalysisAIInterpretations(props.run.id) : { items: [] }
    if (version !== scopeVersion)
      return
    history.value = current.value && !response.items.some(item => item.id === current.value?.id) ? [current.value, ...response.items] : response.items
    // A pending advanced draft has no public output recipe yet, so its exact
    // environment/language cannot be established from a history row. Keep it in
    // history for explicit recovery instead of attaching an old scope to a new
    // environment. The current live request still polls its captured identity.
    const active = props.kind === "compute_draft" ? undefined : response.items.find(item => item.state === "generating" && (props.kind === "interpretation" || analysisSelectionIdentity(item.source_selection) === analysisSelectionIdentity(props.selection)))
    if (active && !current.value && !pending.value)
      storeResponse(active)
  }
  catch (error) {
    if (version === scopeVersion)
      errorMessage.value = httpError(error)
  }
}, { immediate: true })
watch(() => props.available, () => {
  disabledByServer.value = false
})
onBeforeUnmount(() => {
  scopeVersion += 1
  requestVersion += 1
  clearTimer()
})
</script>

<style scoped>
.analysis-ai-panel { min-width: 0; padding: 1rem; margin: 1rem 0; border: 1px solid #d8e8f5; border-radius: .75rem; background: #f8fbff; }
.analysis-ai-consent { display: flex; align-items: flex-start; gap: .5rem; }
.analysis-ai-consent :deep(.n-checkbox) { flex-shrink: 0; margin-top: .15rem; }
.analysis-ai-output, .analysis-ai-prose { overflow-wrap: anywhere; white-space: pre-wrap; }
.analysis-ai-recipe { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: .4rem .75rem; }
.analysis-ai-recipe dd { margin: 0; overflow-wrap: anywhere; }
.analysis-ai-panel ul { padding-left: 1.25rem; }
.analysis-ai-panel li { margin: .3rem 0; overflow-wrap: anywhere; }
.analysis-ai-panel summary { cursor: pointer; }
.analysis-ai-panel pre { overflow: auto; max-width: 100%; max-height: 20rem; padding: .75rem; background: #f1f5f9; border-radius: .5rem; white-space: pre; font-size: .75rem; }
.analysis-ai-panel pre:focus-visible { outline: 2px solid #0084e2; outline-offset: 2px; }
.analysis-ai-history { display: grid; max-height: 16rem; overflow: auto; gap: .5rem; }
.analysis-ai-history button { display: flex; flex-direction: column; gap: .25rem; padding: .65rem; text-align: left; background: white; border: 1px solid #e5e7eb; border-radius: .5rem; cursor: pointer; overflow-wrap: anywhere; }
.analysis-ai-history button:focus-visible, .analysis-ai-panel summary:focus-visible { outline: 2px solid #0084e2; outline-offset: 2px; }
@media (max-width: 600px) { .analysis-ai-panel { padding: .75rem; } .analysis-ai-recipe { grid-template-columns: minmax(0, 1fr); } }
</style>
