<template>
  <section class="analysis-compute-form" data-testid="analysis-compute-form">
    <n-alert type="info" class="mb-4">
      {{ t("page.analysis.compute.privateHint") }}
    </n-alert>
    <n-alert v-if="errorMessage" type="error" class="mb-4">
      {{ errorMessage }}
    </n-alert>
    <n-spin :show="loading">
      <n-button v-if="!context && !loading" @click="loadContext">
        {{ t("common.retry") }}
      </n-button>
      <template v-if="context">
        <n-alert v-if="!context.environments.length" type="warning" class="mb-4">
          {{ t("page.analysis.compute.noEnvironments") }}
        </n-alert>
        <n-alert v-if="!context.approvers.length" type="warning" class="mb-4">
          {{ t("page.analysis.compute.noApprovers") }}
        </n-alert>
        <n-form label-placement="top" :disabled="busy">
          <n-form-item :label="t('page.analysis.compute.environment')" required>
            <n-select v-model:value="environmentId" :options="environmentOptions" filterable data-testid="analysis-compute-environment" @update:value="onEnvironmentChange" />
          </n-form-item>
          <template v-if="environment">
            <p class="aira-type-meta">
              {{ t("page.analysis.compute.runnerCounts", { authorized: environment.authorized_runner_count, ready: environment.ready_runner_count }) }}
            </p>
            <n-alert v-if="!environment.authorized_runner_count" type="warning" class="mb-4">
              {{ t("page.analysis.compute.noAuthorizedRunner") }}
            </n-alert>
            <n-alert v-else-if="!environment.ready_runner_count" type="warning" class="mb-4">
              {{ t("page.analysis.compute.noReadyRunner") }}
            </n-alert>
            <n-form-item :label="t('page.analysis.compute.language')" required>
              <n-select v-model:value="language" :options="languageOptions" data-testid="analysis-compute-language" />
            </n-form-item>
          </template>
          <analysis-ai-panel
            kind="compute_draft" :protocol-id="protocolId" :project-id="projectId" :selection="selection" :question="question"
            :available="Boolean(aiAvailable && environment)" :environment-revision-id="environment?.revision_id" :language="language"
            @adopt="adoptDraft"
          />
          <n-alert v-if="adoptedDraftId" type="info" class="mb-4" data-testid="analysis-ai-compute-adopted">
            {{ t('page.analysis.ai.computeAdoptedHint') }}
            <div class="mt-3">
              <n-button size="small" :disabled="busy" data-testid="analysis-ai-compute-manual" @click="continueManually">
                {{ t('page.analysis.ai.continueManually') }}
              </n-button>
            </div>
          </n-alert>
          <n-form-item :label="t('page.analysis.compute.source')" required>
            <n-input v-model:value="sourceCode" type="textarea" :autosize="{ minRows: 10, maxRows: 24 }" class="font-mono" data-testid="analysis-compute-source" />
            <template #feedback>
              {{ t("page.analysis.compute.sourceHint", { count: context.max_source_bytes }) }}
            </template>
          </n-form-item>
          <n-alert type="info" class="mb-4">
            {{ t("page.analysis.compute.inputContract") }}
          </n-alert>
          <n-form-item :label="t('page.analysis.compute.parameters')">
            <n-input v-model:value="parameterText" type="textarea" :autosize="{ minRows: 3, maxRows: 10 }" class="font-mono" data-testid="analysis-compute-parameters" />
          </n-form-item>
          <section class="mb-5" data-testid="analysis-compute-inputs">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <h3 class="aira-type-label">
                {{ t('page.analysis.compute.inputFiles') }}
              </h3>
              <n-button size="small" :disabled="!context.input_file_limits || !context.input_file_fields?.length || inputFiles.length >= 16" data-testid="analysis-compute-add-input" @click="addInputFile">
                {{ t('page.analysis.compute.addInputFile') }}
              </n-button>
            </div>
            <p class="aira-type-meta">
              {{ t('page.analysis.compute.inputFilesHint') }}
            </p>
            <p v-if="!inputFiles.length" class="aira-type-meta" data-testid="analysis-compute-no-inputs">
              {{ t('page.analysis.compute.inputFilesNone') }}
            </p>
            <p v-if="!context.input_file_fields?.length" class="aira-type-meta">
              {{ t('page.analysis.compute.inputFilesNoFields') }}
            </p>
            <article v-for="(input, index) in inputFiles" :key="index" class="compute-input mb-3" data-testid="analysis-compute-input-declaration">
              <div class="mb-2 flex justify-end">
                <n-button size="small" :disabled="busy" data-testid="analysis-compute-remove-input" @click="inputFiles.splice(index, 1)">
                  {{ t('common.delete') }}
                </n-button>
              </div>
              <n-form-item :label="t('page.analysis.compute.inputFileId')" required>
                <n-input v-model:value="input.input_id" :maxlength="24" data-testid="analysis-compute-input-id" />
                <template #feedback>
                  {{ t('page.analysis.compute.inputFileIdHint') }}
                </template>
              </n-form-item>
              <n-form-item :label="t('page.analysis.compute.inputFileField')" required>
                <n-select :value="input.field_path[1] ? JSON.stringify(input.field_path) : null" :options="inputFileOptions(index)" data-testid="analysis-compute-input-field" @update:value="value => selectInputFileField(index, value)" />
              </n-form-item>
            </article>
            <p v-if="context.input_file_limits" class="aira-type-meta">
              {{ t('page.analysis.compute.inputFileLimits', { count: context.input_file_limits.max_files, fileBytes: context.input_file_limits.max_file_bytes, totalBytes: context.input_file_limits.max_total_bytes }) }}
            </p>
            <p v-if="inputFiles.length" class="aira-type-meta" data-testid="analysis-compute-input-count">
              {{ t('page.analysis.compute.inputFilesEstimate', { records: context.source.record_count, fields: inputFiles.length, files: context.source.record_count * inputFiles.length }) }}
            </p>
            <p v-if="aiAvailable || adoptedDraftId" class="aira-type-meta">
              {{ t('page.analysis.compute.inputFilesAiHint') }}
            </p>
          </section>
          <n-collapse v-if="environment" class="mb-4">
            <n-collapse-item :title="t('page.analysis.compute.schemas')" name="schemas">
              <pre tabindex="0">{{ JSON.stringify({ input: environment.input_schema, result: environment.result_schema }, null, 2) }}</pre>
            </n-collapse-item>
          </n-collapse>
          <section class="mb-4">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <h3 class="aira-type-label">
                {{ t("page.analysis.compute.outputs") }}
              </h3><n-button size="small" :disabled="outputFiles.length >= 16" @click="addOutput">
                {{ t("page.analysis.compute.addOutput") }}
              </n-button>
            </div>
            <p class="aira-type-meta">
              {{ t("page.analysis.compute.outputHint") }}
            </p>
            <div v-for="(output, index) in outputFiles" :key="index" class="compute-output mb-3">
              <div class="flex justify-end">
                <n-button size="small" @click="outputFiles.splice(index, 1)">
                  {{ t("common.delete") }}
                </n-button>
              </div>
              <n-form-item :label="t('page.analysis.compute.filename')" required>
                <n-input v-model:value="output.mount_name" placeholder="analysis.csv" />
              </n-form-item>
              <n-form-item :label="t('page.analysis.compute.outputName')" required>
                <n-input v-model:value="output.asset_name" />
              </n-form-item>
              <n-form-item :label="t('page.analysis.compute.outputKind')" required>
                <n-select v-model:value="output.kind" :options="outputKindOptions" />
              </n-form-item>
              <n-form-item :label="t('page.analysis.compute.mediaType')" required>
                <n-input v-model:value="output.media_type" placeholder="text/csv" />
              </n-form-item>
              <n-form-item :label="t('page.analysis.compute.maxBytes')" required>
                <n-input-number v-model:value="output.max_bytes" :min="1" :max="environment?.resource_limits.max_output_bytes || 2147483647" class="w-full" />
              </n-form-item>
              <n-checkbox v-model:checked="output.required">
                {{ t("page.analysis.compute.requiredOutput") }}
              </n-checkbox>
            </div>
          </section>
          <n-form-item :label="t('page.analysis.compute.approver')" required>
            <n-select v-model:value="approverId" :options="context.approvers.map(item => ({ value: item.id, label: item.name }))" filterable data-testid="analysis-compute-approver" /><template #feedback>
              {{ t("page.analysis.compute.approverHint") }}
            </template>
          </n-form-item>
          <p v-if="environment" class="aira-type-meta">
            {{ t("page.analysis.compute.estimatedCost") }}: {{ environment.estimated_cost === null ? t("page.analysis.compute.unpriced") : `${environment.estimated_cost} ${environment.currency || ''}` }}
          </p>
          <n-form-item :label="t('page.analysis.compute.maxCost')">
            <n-input v-model:value="maxCost" inputmode="decimal" data-testid="analysis-compute-max-cost" />
          </n-form-item>
          <n-form-item :label="t('page.analysis.compute.currency')">
            <n-input v-model:value="budgetCurrency" :maxlength="3" />
          </n-form-item>
          <n-form-item :label="t('page.analysis.compute.deadline')">
            <n-date-picker v-model:value="deadline" type="datetime" clearable class="w-full" />
          </n-form-item>
        </n-form>
        <n-alert v-if="validationError" type="warning" class="mb-4">
          {{ validationError }}
        </n-alert>
        <n-alert v-if="methodChanged" type="info" class="mb-4">
          {{ t("page.analysis.methodChanged") }}
        </n-alert>
        <div class="flex flex-wrap gap-2">
          <n-button type="primary" :disabled="!valid || methodChanged" :loading="busy" data-testid="analysis-compute-preview" @click="handlePreview">
            {{ t("page.analysis.compute.preview") }}
          </n-button>
          <n-button v-if="seed?.pipeline" :disabled="!recipe || Boolean(recipeError)" data-testid="analysis-compute-save-revision" @click="saveRevision">
            {{ t("page.analysis.saveRevision", { number: seed.pipeline.current_revision + 1 }) }}
          </n-button>
        </div>
      </template>
    </n-spin>
    <n-modal v-model:show="previewVisible" preset="card" class="aira-dialog" style="--aira-dialog-width: 54rem" :title="t('page.analysis.compute.preview')" :mask-closable="false" :closable="!busy" data-testid="analysis-compute-preview-dialog">
      <template v-if="preview">
        <n-alert type="info" class="mb-3">
          {{ t("page.analysis.destination", { project: preview.summary.project_name, protocol: preview.summary.protocol_name }) }}
        </n-alert>
        <p class="aira-type-body">
          {{ preview.question }}
        </p>
        <n-alert v-if="errorMessage" type="error" class="mb-3">
          {{ errorMessage }}
        </n-alert>
        <analysis-compute-contract :contract="preview.summary.compute" />
        <p class="aira-type-meta">
          {{ t("page.analysis.expiresAt", { time: new Date(preview.expires_at).toLocaleString(locale) }) }}
        </p>
      </template>
      <template #footer>
        <div class="flex flex-wrap justify-end gap-2">
          <n-button :disabled="busy" @click="previewVisible = false">
            {{ t("page.analysis.backToEdit") }}
          </n-button><n-button type="primary" :loading="busy" data-testid="analysis-compute-confirm" @click="handleConfirm">
            {{ t("page.analysis.compute.confirm") }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </section>
</template>

<script setup lang="ts">
import type { AnalysisAIRequest, AnalysisSelection } from "@/service/api/analysis"
import type { AnalysisComputeContext, AnalysisComputeInputFile, AnalysisComputePreview, AnalysisComputeRecipe, AnalysisComputeSeed } from "@/service/api/analysis-compute"
import type { ComputeOutputDraft } from "@/service/api/research-compute-jobs"
import { createAnalysisPipelineRevision } from "@/service/api/analysis"
import { confirmAnalysisCompute, fetchAnalysisComputeContext, previewAnalysisCompute } from "@/service/api/analysis-compute"
import { analysisSelectionIdentity, canAdoptAnalysisComputeDraft, createAnalysisAIRequestId } from "@/utils/analysis-ai"
import { analysisComputeEnvironmentLabel, analysisComputeGovernance, analysisComputeInputFileFieldLabel, analysisComputeRecipeIdentity, parseAnalysisComputeParameters, validateAnalysisComputeRecipe, withAnalysisComputeInputFiles } from "@/utils/analysis-compute"
import { useDialog } from "naive-ui"
import { useI18n } from "vue-i18n"
import AnalysisAiPanel from "./analysis-ai-panel.vue"
import AnalysisComputeContract from "./analysis-compute-contract.vue"

const props = defineProps<{ protocolId: string, projectId: string, selection: AnalysisSelection, question: string, seed: AnalysisComputeSeed | null, aiAvailable: boolean }>()
const emit = defineEmits<{ created: [id: string], revisionSaved: [pipelineId: string] }>()
const { t, locale } = useI18n()
const dialog = useDialog()
const context = ref<AnalysisComputeContext | null>(null)
const loading = ref(false)
const busy = ref(false)
const errorMessage = ref("")
const environmentId = ref("")
const language = ref<"python" | "r">("python")
const sourceCode = ref("")
const parameterText = ref("{}")
const outputFiles = ref<ComputeOutputDraft[]>([])
const inputFiles = ref<AnalysisComputeInputFile[]>([])
const adoptedDraftId = ref<string | undefined>()
const approverId = ref("")
const maxCost = ref("")
const budgetCurrency = ref("")
const deadline = ref<number | null>(null)
const preview = ref<AnalysisComputePreview | null>(null)
const previewVisible = ref(false)
let sequence = 0
let confirmationKey = ""
const environment = computed(() => context.value?.environments.find(item => item.revision_id === environmentId.value))
const environmentOptions = computed(() => context.value?.environments.map(item => ({ label: analysisComputeEnvironmentLabel(item), value: item.revision_id })) || [])
const languageOptions = computed(() => environment.value?.allowed_languages.map(value => ({ value, label: value === "python" ? "Python" : "R" })) || [])
const outputKindOptions = computed(() => (["file", "table", "image", "model", "archive"] as const).map(value => ({ value, label: t(`page.analysis.compute.kinds.${value}`) })))
const recipe = computed<AnalysisComputeRecipe | null>(() => {
  try {
    return withAnalysisComputeInputFiles({ kind: "compute", environment_revision_id: environmentId.value, language: language.value, source_code: sourceCode.value, parameters: parseAnalysisComputeParameters(parameterText.value), output_files: JSON.parse(JSON.stringify(outputFiles.value)) as ComputeOutputDraft[] }, inputFiles.value)
  }
  catch { return null }
})
const recipeError = computed(() => !recipe.value ? "invalidParameters" : context.value ? validateAnalysisComputeRecipe(recipe.value, context.value) : "environmentUnavailable")
const validationError = computed(() => {
  if (recipeError.value)
    return t(`page.analysis.compute.${recipeError.value}`)
  try {
    analysisComputeGovernance(maxCost.value, budgetCurrency.value, deadline.value)
  }
  catch (error) {
    return t(`page.analysis.compute.${(error as Error).message}`)
  }
  return ""
})
const valid = computed(() => Boolean(context.value && recipe.value && !validationError.value && context.value.approvers.some(item => item.id === approverId.value) && !loading.value))
const methodChanged = computed(() => Boolean(props.seed?.pipeline && recipe.value && analysisComputeRecipeIdentity(props.seed.recipe) !== analysisComputeRecipeIdentity(recipe.value)))
function errorText(error: unknown) {
  const status = (error as { response?: { status?: number } })?.response?.status
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if ((status === 422 || status === 413) && typeof detail === "string")
    return detail
  return t(status === 409 ? "page.analysis.stalePreview" : status === 403 || status === 404 ? "page.analysis.compute.accessChanged" : "page.analysis.requestError")
}
function onEnvironmentChange() {
  if (environment.value && !environment.value.allowed_languages.includes(language.value))
    language.value = environment.value.allowed_languages[0] || "python"
  if (!budgetCurrency.value)
    budgetCurrency.value = environment.value?.currency || ""
}
function adoptDraft(request: AnalysisAIRequest) {
  const output = request.output
  if (!canAdoptAnalysisComputeDraft(request, props.protocolId, props.projectId, props.selection, environment.value?.revision_id, language.value) || !output || !("mode" in output) || output.mode !== "compute" || !output.recipe)
    return
  // Keep only attachment fields already selected by the user, never model declarations.
  const adopted = withAnalysisComputeInputFiles(output.recipe, inputFiles.value)
  sourceCode.value = adopted.source_code
  parameterText.value = JSON.stringify(adopted.parameters, null, 2)
  outputFiles.value = JSON.parse(JSON.stringify(adopted.output_files)) as ComputeOutputDraft[]
  adoptedDraftId.value = request.id
  preview.value = null
  previewVisible.value = false
}
function continueManually() {
  dialog.warning({ title: t("page.analysis.ai.continueManually"), content: t("page.analysis.ai.computeManualHint"), positiveText: t("common.confirm"), negativeText: t("common.cancel"), onPositiveClick: () => {
    adoptedDraftId.value = undefined
    preview.value = null
    previewVisible.value = false
    errorMessage.value = ""
  } })
}
function addOutput() {
  outputFiles.value.push({ mount_name: `output-${outputFiles.value.length + 1}.json`, asset_name: t("page.analysis.compute.outputName"), description: "", kind: "file", media_type: "application/json", max_bytes: Math.min(1024 * 1024, Math.max(1, (environment.value?.resource_limits.max_output_bytes || 2048) - 1024)), required: true, data_schema: {}, metadata: {} })
}
function inputFileOptions(index: number) {
  return (context.value?.input_file_fields ?? []).map(field => ({
    label: analysisComputeInputFileFieldLabel(field),
    value: JSON.stringify(field.field_path),
    disabled: inputFiles.value.some((input, otherIndex) => otherIndex !== index && JSON.stringify(input.field_path) === JSON.stringify(field.field_path)),
  }))
}
function selectInputFileField(index: number, value: string) {
  const field = context.value?.input_file_fields?.find(field => JSON.stringify(field.field_path) === value)
  if (field && inputFiles.value[index])
    inputFiles.value[index].field_path = [...field.field_path]
}
function addInputFile() {
  if (busy.value || inputFiles.value.length >= 16 || !context.value?.input_file_fields?.length || !context.value.input_file_limits)
    return
  let number = 1
  while (inputFiles.value.some(input => input.input_id === `input_${number}`))
    number++
  inputFiles.value.push({ input_id: `input_${number}`, field_path: ["var", ""] })
}
async function loadContext() {
  const version = ++sequence
  loading.value = true
  context.value = null
  previewVisible.value = false
  preview.value = null
  errorMessage.value = ""
  try {
    const result = await fetchAnalysisComputeContext(props.protocolId, props.selection)
    if (version !== sequence)
      return
    context.value = result
    if (!environmentId.value && result.environments.length === 1)
      environmentId.value = result.environments[0].revision_id
    if (!approverId.value && result.approvers.length === 1)
      approverId.value = result.approvers[0].id
    onEnvironmentChange()
  }
  catch (error) {
    if (version === sequence)
      errorMessage.value = errorText(error)
  }
  finally {
    if (version === sequence)
      loading.value = false
  }
}
async function handlePreview() {
  if (!valid.value || !recipe.value || busy.value || methodChanged.value)
    return
  const version = sequence
  busy.value = true
  errorMessage.value = ""
  try {
    const result = await previewAnalysisCompute({ protocol_id: props.protocolId, selection: props.selection, question: props.question, recipe: recipe.value, approver_user_id: approverId.value, ...analysisComputeGovernance(maxCost.value, budgetCurrency.value, deadline.value), pipeline_revision_id: props.seed?.pipelineRevisionId, rerun_of_id: props.seed?.rerunOfId, ai_draft_id: adoptedDraftId.value })
    if (version !== sequence)
      return
    preview.value = result
    confirmationKey = createAnalysisAIRequestId()
    previewVisible.value = true
  }
  catch (error) {
    if (version === sequence)
      errorMessage.value = errorText(error)
  }
  finally { busy.value = false }
}
async function handleConfirm() {
  if (!preview.value || busy.value)
    return
  const version = sequence
  busy.value = true
  try {
    const result = await confirmAnalysisCompute({ preview_id: preview.value.id, preview_digest: preview.value.preview_digest, client_idempotency_key: confirmationKey })
    if (version !== sequence)
      return
    previewVisible.value = false
    emit("created", result.id)
  }
  catch (error) {
    if (version === sequence) {
      errorMessage.value = errorText(error)
      if ((error as { response?: { status?: number } })?.response?.status === 409) {
        preview.value = null
        previewVisible.value = false
      }
    }
  }
  finally { busy.value = false }
}
function saveRevision() {
  const pipeline = props.seed?.pipeline
  const value = recipe.value
  if (!pipeline || !value)
    return
  dialog.warning({ title: t("page.analysis.saveRevision", { number: pipeline.current_revision + 1 }), content: t("page.analysis.revisionHint"), positiveText: t("common.confirm"), negativeText: t("common.cancel"), onPositiveClick: async () => {
    try {
      await createAnalysisPipelineRevision(pipeline.id, { recipe: value, expected_revision: pipeline.current_revision, source_selection: props.selection })
      emit("revisionSaved", pipeline.id)
    }
    catch (error) { errorMessage.value = errorText(error) }
  } })
}
watch(() => props.seed, (seed) => {
  adoptedDraftId.value = undefined
  environmentId.value = seed?.recipe.environment_revision_id || ""
  language.value = seed?.recipe.language || "python"
  sourceCode.value = seed?.recipe.source_code || ""
  parameterText.value = JSON.stringify(seed?.recipe.parameters || {}, null, 2)
  outputFiles.value = JSON.parse(JSON.stringify(seed?.recipe.output_files || [])) as ComputeOutputDraft[]
  inputFiles.value = JSON.parse(JSON.stringify(seed?.recipe.input_files || [])) as AnalysisComputeInputFile[]
  preview.value = null
  previewVisible.value = false
}, { immediate: true })
watch(() => [props.protocolId, analysisSelectionIdentity(props.selection)], () => void loadContext(), { immediate: true })
watch(() => [props.protocolId, props.projectId, analysisSelectionIdentity(props.selection), environmentId.value, language.value], () => {
  adoptedDraftId.value = undefined
  preview.value = null
  previewVisible.value = false
})
onBeforeUnmount(() => {
  sequence += 1
})
</script>

<style scoped>
.analysis-compute-form { min-width: 0; }
.compute-output, .compute-input { min-width: 0; border: 1px solid #e5e7eb; border-radius: .75rem; padding: .75rem; overflow-wrap: anywhere; }
pre { overflow: auto; max-height: 18rem; padding: .75rem; background: #f7f9fc; border-radius: .5rem; font-size: .75rem; }
</style>
