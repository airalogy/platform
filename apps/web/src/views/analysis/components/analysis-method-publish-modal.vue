<template>
  <n-modal :show="show" preset="card" class="aira-dialog" style="--aira-dialog-width: 46rem" :title="t('page.workflowAnalysis.publishTitle')" :mask-closable="false" :closable="!busy && !uncertain" :close-on-esc="!busy && !uncertain" data-testid="analysis-method-publish-dialog" @update:show="emit('update:show', $event)">
    <n-spin :show="loading">
      <n-alert v-if="error" type="error" class="mb-4">
        {{ error }}
      </n-alert>
      <n-alert v-if="uncertain" type="warning" class="mb-4">
        {{ t('page.workflowDefinitions.confirmationUncertain') }}
      </n-alert>
      <template v-if="published">
        <n-alert type="success" data-testid="analysis-method-published">
          {{ t('page.workflowAnalysis.published', { title: published.title, project: projectName }) }}
        </n-alert>
        <p class="aira-type-meta">
          {{ t('page.workflowAnalysis.immutableHint') }}
        </p>
        <code class="method-digest">{{ published.digest }}</code>
      </template>
      <template v-else-if="preview">
        <n-alert type="warning" class="mb-4">
          {{ t('page.workflowAnalysis.audience', { project: projectName }) }}
        </n-alert>
        <h3 class="aira-type-card-title">
          {{ preview.publication.title }}
        </h3>
        <p>{{ t('page.workflowDefinitions.revision', { number: preview.source.revision }) }} · {{ selectedProtocol?.name }} · {{ versionLabel }}</p>
        <p class="aira-type-meta">
          {{ t(preview.publication.compute_contract ? 'page.workflowAnalysis.computeExcluded' : 'page.workflowAnalysis.excluded') }}
        </p>
        <n-checkbox v-model:checked="reviewed" :disabled="busy || uncertain" data-testid="analysis-method-publish-reviewed">
          {{ t('page.workflowAnalysis.reviewDisclosure') }}
        </n-checkbox>
        <workflow-method-summary v-if="preview.publication.compute_contract" :method="preview.publication" />
        <h4 class="aira-type-label">
          {{ t('page.workflowAnalysis.recipe') }}
        </h4>
        <pre class="method-json" tabindex="0" data-testid="analysis-method-publish-recipe">{{ JSON.stringify(preview.publication.recipe, null, 2) }}</pre>
        <h4 class="aira-type-label">
          {{ t('page.workflowAnalysis.inputContract') }}
        </h4>
        <pre class="method-json" tabindex="0">{{ JSON.stringify(preview.publication.input_fields, null, 2) }}</pre>
        <p class="aira-type-meta">
          {{ t('page.workflowAnalysis.immutableHint') }}
        </p>
        <code class="method-digest">{{ preview.preview_digest }}</code>
      </template>
      <template v-else>
        <n-alert type="info" class="mb-4">
          {{ t('page.workflowAnalysis.publishHint') }}
        </n-alert>
        <n-form label-placement="top" :disabled="busy || loading">
          <n-form-item :label="t('page.workflowAnalysis.privateMethod')" required>
            <n-select v-model:value="methodId" :options="methodOptions" filterable data-testid="analysis-method-private-select" />
          </n-form-item>
          <p class="aira-type-meta">
            {{ t('page.workflowAnalysis.computeSupported') }}
          </p>
          <n-form-item :label="t('page.workflowDefinitions.savedRevision')" required>
            <n-select v-model:value="revisionId" :options="revisionOptions" data-testid="analysis-method-private-revision" />
          </n-form-item>
          <n-form-item :label="t('page.workflowDefinitions.protocolVersion')" required>
            <n-select v-model:value="versionId" :options="versionOptions" data-testid="analysis-method-protocol-version" />
          </n-form-item>
          <n-form-item :label="t('page.analysis.methodTitle')" required>
            <n-input v-model:value="title" :maxlength="255" data-testid="analysis-method-publish-title" />
          </n-form-item>
          <n-form-item v-if="selectedRecipe && isComputeAnalysisRecipe(selectedRecipe)" :label="t('page.workflowAnalysis.computeResultContract')" :feedback="t('page.workflowAnalysis.computeSchemaHint')" :validation-status="schemaError ? 'error' : undefined">
            <n-input v-model:value="resultSchemaText" type="textarea" :autosize="{ minRows: 4, maxRows: 14 }" data-testid="analysis-method-result-schema" />
          </n-form-item>
        </n-form>
        <p class="aira-type-meta">
          {{ t('page.workflowAnalysis.destination', { project: projectName }) }}
        </p>
      </template>
    </n-spin>
    <template #footer>
      <div class="flex flex-wrap justify-end gap-2">
        <n-button :disabled="busy || uncertain" @click="preview && !published ? backToEdit() : emit('update:show', false)">
          {{ t(published ? 'common.close' : preview ? 'page.workflowDefinitions.backToEdit' : 'common.cancel') }}
        </n-button>
        <n-button v-if="!published && !preview" type="primary" :loading="busy" :disabled="!revisionId || !versionId || !title.trim() || loading || !!schemaError" data-testid="analysis-method-preview-publication" @click="previewPublication">
          {{ t('page.workflowAnalysis.previewPublication') }}
        </n-button>
        <n-button v-else-if="preview && !published" type="primary" :loading="busy" :disabled="!reviewed" data-testid="analysis-method-confirm-publication" @click="confirmPublication">
          {{ t('page.workflowAnalysis.confirmPublication') }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type { AnalysisPipeline } from "@/service/api/analysis"
import type { WorkflowAnalysisPublication, WorkflowAnalysisPublicationPreview, WorkflowAnalysisPublicationRequest } from "@/service/api/workflow-analysis-methods"
import type { WorkflowContext } from "@/service/api/workflow-definitions"
import { fetchAnalysisPipeline, fetchProjectAnalysisPipelines } from "@/service/api/analysis"
import { confirmWorkflowAnalysisPublication, previewWorkflowAnalysisPublication } from "@/service/api/workflow-analysis-methods"
import { fetchWorkflowContext } from "@/service/api/workflow-definitions"
import { isComputeAnalysisRecipe, parseAnalysisComputeParameters } from "@/utils/analysis-compute"
import { createWorkflowId } from "@/utils/workflow-editor"
import WorkflowMethodSummary from "@/views/workflow-definitions/components/workflow-method-summary.vue"
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { useI18n } from "vue-i18n"
import { onBeforeRouteLeave, onBeforeRouteUpdate } from "vue-router"

const props = defineProps<{ show: boolean, projectId: string, projectName: string, pipelineId?: string }>()
const emit = defineEmits<{ "update:show": [value: boolean], "published": [publication: WorkflowAnalysisPublication] }>()
const { t } = useI18n()
const methods = ref<AnalysisPipeline[]>([])
const protocols = ref<WorkflowContext["protocols"]>([])
const selected = ref<AnalysisPipeline | null>(null)
const methodId = ref<string | null>(null)
const revisionId = ref<string | null>(null)
const versionId = ref<string | null>(null)
const title = ref("")
const resultSchemaText = ref("")
const preview = ref<WorkflowAnalysisPublicationPreview | null>(null)
const request = ref<WorkflowAnalysisPublicationRequest | null>(null)
const published = ref<WorkflowAnalysisPublication | null>(null)
const reviewed = ref(false)
const loading = ref(false)
const busy = ref(false)
const uncertain = ref(false)
const error = ref("")
const key = ref("")
let sequence = 0
const methodOptions = computed(() => methods.value.map(method => ({ label: `${method.title}${isComputeAnalysisRecipe(method.current_recipe) ? ` · ${method.current_recipe.language === "python" ? "Python" : "R"}` : ""}`, value: method.id })))
const revisionOptions = computed(() => (selected.value?.revisions ?? []).map(revision => ({ label: t("page.workflowDefinitions.revision", { number: revision.revision }), value: revision.id })))
const selectedRecipe = computed(() => selected.value?.revisions?.find(revision => revision.id === revisionId.value)?.recipe)
const schemaError = computed(() => {
  if (!selectedRecipe.value || !isComputeAnalysisRecipe(selectedRecipe.value) || !resultSchemaText.value.trim())
    return false
  try {
    parseAnalysisComputeParameters(resultSchemaText.value)
    return false
  }
  catch { return true }
})
const selectedProtocol = computed(() => protocols.value.find(protocol => protocol.id === selected.value?.protocol_id))
const versionOptions = computed(() => (selectedProtocol.value?.versions ?? []).map(version => ({ label: version.version, value: version.id })))
const versionLabel = computed(() => selectedProtocol.value?.versions.find(version => version.id === versionId.value)?.version ?? versionId.value)
function errorText(cause: unknown) {
  const detail = (cause as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === "string" ? detail : t("page.workflowDefinitions.requestFailed")
}
async function loadMethod(id: string | null) {
  const current = ++sequence
  selected.value = null
  revisionId.value = null
  versionId.value = null
  if (!id)
    return
  loading.value = true
  try {
    const method = await fetchAnalysisPipeline(id)
    if (current !== sequence || !props.show)
      return
    if (method.project_id !== props.projectId)
      throw new Error("Method Project mismatch")
    selected.value = method
    revisionId.value = method.revisions?.find(revision => revision.revision === method.current_revision)?.id ?? null
    versionId.value = versionOptions.value[0]?.value ?? null
    title.value = method.title
    resultSchemaText.value = ""
  }
  catch (cause) { error.value = errorText(cause) }
  finally {
    if (current === sequence)
      loading.value = false
  }
}
function backToEdit() {
  preview.value = null
  reviewed.value = false
  error.value = ""
}
async function previewPublication() {
  if (!revisionId.value || !versionId.value || busy.value || schemaError.value)
    return
  busy.value = true
  error.value = ""
  try {
    request.value = { project_id: props.projectId, pipeline_revision_id: revisionId.value, protocol_version_id: versionId.value, title: title.value.trim() }
    if (selectedRecipe.value && isComputeAnalysisRecipe(selectedRecipe.value) && resultSchemaText.value.trim())
      request.value.compute_result_schema = parseAnalysisComputeParameters(resultSchemaText.value)
    preview.value = await previewWorkflowAnalysisPublication(request.value)
    key.value = createWorkflowId()
    reviewed.value = false
  }
  catch (cause) { error.value = errorText(cause) }
  finally { busy.value = false }
}
async function confirmPublication() {
  if (!request.value || !preview.value || !reviewed.value || busy.value)
    return
  busy.value = true
  error.value = ""
  try {
    published.value = await confirmWorkflowAnalysisPublication({ ...request.value, preview_digest: preview.value.preview_digest, idempotency_key: key.value })
    uncertain.value = false
    emit("published", published.value)
  }
  catch (cause) {
    const status = (cause as { response?: { status?: number } })?.response?.status
    uncertain.value = !status || status >= 500 || status === 408
    error.value = errorText(cause)
  }
  finally { busy.value = false }
}
watch(methodId, (id) => {
  if (id)
    void loadMethod(id)
})
watch(() => [props.show, props.projectId] as const, async ([show]) => {
  sequence++
  if (!show)
    return
  methodId.value = null
  selected.value = null
  revisionId.value = null
  versionId.value = null
  preview.value = null
  request.value = null
  published.value = null
  uncertain.value = false
  error.value = ""
  loading.value = true
  const current = sequence
  try {
    const [list, context] = await Promise.all([fetchProjectAnalysisPipelines(props.projectId), fetchWorkflowContext(props.projectId)])
    if (current !== sequence || !props.show)
      return
    methods.value = list.items
    protocols.value = context.protocols
    methodId.value = props.pipelineId ?? (methodOptions.value.length === 1 ? methodOptions.value[0].value : null)
  }
  catch (cause) { error.value = errorText(cause) }
  finally {
    if (current === sequence)
      loading.value = false
  }
})
function protectPendingPublication(event: BeforeUnloadEvent) {
  if (busy.value || uncertain.value) {
    event.preventDefault()
    event.returnValue = ""
  }
}
window.addEventListener("beforeunload", protectPendingPublication)
onBeforeUnmount(() => {
  sequence++
  window.removeEventListener("beforeunload", protectPendingPublication)
})
onBeforeRouteLeave(() => !busy.value && !uncertain.value)
onBeforeRouteUpdate(() => !busy.value && !uncertain.value)
</script>

<style scoped>
.method-json { max-height: 24rem; overflow: auto; padding: 12px; border-radius: 8px; background: #f8fafc; white-space: pre-wrap; overflow-wrap: anywhere; }
.method-digest { display: block; overflow-wrap: anywhere; }
</style>
