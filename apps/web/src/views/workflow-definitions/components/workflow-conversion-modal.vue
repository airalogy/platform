<template>
  <n-modal :show="show" preset="card" class="aira-dialog workflow-conversion" style="--aira-dialog-width: 52rem" :title="t('page.workflowLegacy.title')" :mask-closable="false" :closable="!busy && !uncertain" :close-on-esc="!busy && !uncertain" data-testid="workflow-conversion-dialog" @update:show="emit('update:show', $event)">
    <n-spin :show="loading">
      <n-alert v-if="error" type="error" class="mb-3" data-testid="workflow-conversion-error">
        {{ error }}
      </n-alert>
      <n-alert v-if="uncertain" type="warning" class="mb-3">
        {{ t('page.workflowDefinitions.confirmationUncertain') }}
      </n-alert>
      <template v-if="created">
        <n-alert type="success" data-testid="workflow-conversion-created">
          {{ t('page.workflowLegacy.created', { title: created.title }) }}
        </n-alert>
        <p>{{ t('page.workflowLegacy.preserve') }}</p>
      </template>
      <template v-else-if="preview">
        <n-alert type="warning" class="mb-3">
          {{ t('page.workflowLegacy.previewHint', { project: projectName }) }}
        </n-alert>
        <h3 class="aira-type-card-title">
          {{ draft?.title }}
        </h3>
        <p class="aira-type-meta">
          {{ t('page.workflowLegacy.source') }}: {{ context?.source.title }} · {{ context?.source.id }}
        </p>
        <p>{{ t('page.workflowLegacy.logicOmitted') }}</p>
        <n-alert v-for="warning in preview.warnings" :key="warning.code" type="warning" class="my-2">
          {{ warningText(warning) }}
        </n-alert>
        <ul class="pl-5">
          <li v-for="pin in preview.pins" :key="pin.node_id">
            {{ pin.name }} · {{ pin.kind === 'analysis' ? pin.engine_version : pin.version }}
          </li>
        </ul>
        <workflow-data-summary :graph="preview.graph" />
        <p>{{ t('page.workflowLegacy.preserve') }}</p>
        <details>
          <summary>{{ t('page.workflowLegacy.exactGraph') }}</summary>
          <pre tabindex="0" data-testid="workflow-conversion-graph">{{ JSON.stringify(preview.graph, null, 2) }}</pre>
        </details>
        <p class="aira-type-meta">
          {{ preview.preview_digest }}
        </p>
      </template>
      <template v-else>
        <n-alert type="info" class="mb-3">
          {{ t('page.workflowLegacy.hint') }}
        </n-alert>
        <n-form-item :label="t('page.workflowLegacy.source')" label-placement="top">
          <n-select :value="sourceId" :options="sourceOptions" :disabled="busy || loading" filterable data-testid="workflow-conversion-source" @update:value="selectSource" />
        </n-form-item>
        <n-empty v-if="!loading && !items.length" :description="t('page.workflowLegacy.none')" />
        <n-button v-if="error && !loading" size="small" @click="sourceId ? selectSource(sourceId) : loadDirectory()">
          {{ t('common.retry') }}
        </n-button>
        <n-form v-if="context && draft" label-placement="top" :disabled="busy">
          <n-form-item :label="t('page.workflowDefinitions.workflowTitle')" required>
            <n-input v-model:value="draft.title" :maxlength="255" data-testid="workflow-conversion-title" />
          </n-form-item>
          <n-form-item :label="t('page.workflowDefinitions.workflowDescription')">
            <n-input v-model:value="draft.description" type="textarea" :maxlength="4000" :autosize="{ minRows: 2, maxRows: 5 }" />
          </n-form-item>
          <h3 class="aira-type-card-title">
            {{ t('page.workflowLegacy.versions') }}
          </h3>
          <p class="aira-type-meta">
            {{ t('page.workflowLegacy.versionHint') }}
          </p>
          <article v-for="(node, index) in context.nodes" :key="node.node_id" class="conversion-row mb-3" data-testid="workflow-conversion-node">
            <strong>{{ node.protocol_index }}. {{ node.name }}</strong>
            <p class="aira-type-meta my-2">
              {{ node.original_reference }}
            </p>
            <n-select v-model:value="draft.nodes[index].protocol_version_id" :options="node.versions.map(version => ({ label: version.version, value: version.id }))" :disabled="busy || !node.protocol_id" :placeholder="t('page.workflowDefinitions.protocolVersion')" :data-testid="`workflow-conversion-version-${node.protocol_index}`" />
          </article>
          <h3 class="aira-type-card-title">
            {{ t('page.workflowLegacy.edges') }}
          </h3>
          <p class="aira-type-meta">
            {{ t('page.workflowLegacy.edgeHint') }}
          </p>
          <div v-for="edge in context.edges" :key="edge.edge_id" class="conversion-row mb-2">
            <n-checkbox :checked="hasEdge(edge.source_protocol_index, edge.target_protocol_index) && edge.supported" :disabled="busy || !edge.supported" :data-testid="`workflow-conversion-edge-${edge.edge_id}`" @update:checked="value => toggleEdge(edge.source_protocol_index, edge.target_protocol_index, value)">
              {{ edge.text }}
            </n-checkbox>
            <p v-if="!edge.supported" class="aira-type-meta my-1">
              {{ t('page.workflowLegacy.unsupportedEdge') }}
            </p>
          </div>
          <div class="conversion-edge-picker my-3">
            <n-select v-model:value="edgeSource" :options="nodeOptions" :placeholder="t('page.workflowDefinitions.bindings.sourceCard')" data-testid="workflow-conversion-edge-source" />
            <span>→</span>
            <n-select v-model:value="edgeTarget" :options="nodeOptions" :placeholder="t('page.workflowLegacy.targetCard')" data-testid="workflow-conversion-edge-target" />
            <n-button :disabled="busy || edgeSource === null || edgeTarget === null || edgeSource === edgeTarget || hasEdge(edgeSource, edgeTarget)" data-testid="workflow-conversion-add-edge" @click="toggleEdge(edgeSource, edgeTarget, true)">
              {{ t('common.add') }}
            </n-button>
          </div>
          <div v-for="edge in draft.edges" :key="`${edge.source_protocol_index}-${edge.target_protocol_index}`" class="conversion-row mb-2 flex items-center justify-between gap-3">
            <span>{{ nodeName(edge.source_protocol_index) }} → {{ nodeName(edge.target_protocol_index) }}</span>
            <n-button size="small" :disabled="busy" @click="toggleEdge(edge.source_protocol_index, edge.target_protocol_index, false)">
              {{ t('common.delete') }}
            </n-button>
          </div>
          <n-alert type="warning" class="my-3">
            {{ t('page.workflowLegacy.logicOmitted') }}
          </n-alert>
          <details v-if="context.logic_text">
            <summary>{{ t('page.workflowLegacy.originalLogic') }}</summary>
            <pre tabindex="0" data-testid="workflow-conversion-original-logic">{{ context.logic_text }}</pre>
          </details>
          <n-alert v-for="warning in context.warnings" :key="warning.code + warning.message" type="warning" class="my-2">
            {{ warningText(warning) }}
          </n-alert>
          <n-alert v-for="blocker in context.blockers" :key="blocker.protocol_index" type="error" class="my-2">
            {{ t('page.workflowLegacy.protocolUnavailable', { number: blocker.protocol_index }) }}
          </n-alert>
          <div class="conversion-checks mt-4">
            <n-checkbox v-model:checked="draft.acknowledge_versions" data-testid="workflow-conversion-ack-versions">
              {{ t('page.workflowLegacy.ackVersions') }}
            </n-checkbox>
            <n-checkbox v-model:checked="draft.acknowledge_structure_only" data-testid="workflow-conversion-ack-structure">
              {{ t('page.workflowLegacy.ackStructure') }}
            </n-checkbox>
            <n-checkbox v-model:checked="draft.acknowledge_logic_omission" data-testid="workflow-conversion-ack-logic">
              {{ t('page.workflowLegacy.ackLogic') }}
            </n-checkbox>
          </div>
        </n-form>
      </template>
    </n-spin>
    <template #footer>
      <div class="flex flex-wrap justify-end gap-2">
        <n-button :disabled="busy || uncertain" @click="preview && !created ? backToEdit() : emit('update:show', false)">
          {{ t(created ? 'common.close' : preview ? 'page.workflowDefinitions.backToEdit' : 'common.cancel') }}
        </n-button>
        <n-button v-if="created" type="primary" data-testid="workflow-conversion-open" @click="emit('open', created)">
          {{ t('page.workflowLegacy.openCreated') }}
        </n-button>
        <n-button v-else-if="preview" type="primary" :loading="busy" data-testid="workflow-conversion-confirm" @click="confirmConversion">
          {{ t('page.workflowLegacy.confirm') }}
        </n-button>
        <n-button v-else type="primary" :disabled="!ready || loading" :loading="busy" data-testid="workflow-conversion-preview" @click="requestPreview">
          {{ t('page.workflowLegacy.preview') }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type { LegacyWorkflowEntry, WorkflowConversionContext, WorkflowConversionPreview, WorkflowConversionRequest, WorkflowConversionResult } from "@/service/api/workflow-conversions"
import { confirmWorkflowConversion, fetchLegacyWorkflows, fetchWorkflowConversionContext, previewWorkflowConversion } from "@/service/api/workflow-conversions"
import { createWorkflowConversionDraft, workflowConversionReady } from "@/utils/workflow-conversion"
import { createWorkflowId } from "@/utils/workflow-editor"
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { useI18n } from "vue-i18n"
import WorkflowDataSummary from "./workflow-data-summary.vue"

const props = defineProps<{ show: boolean, projectId: string, projectName: string }>()
const emit = defineEmits<{ "update:show": [boolean], "busy": [boolean], "created": [WorkflowConversionResult], "open": [WorkflowConversionResult] }>()
const { t } = useI18n()
const items = ref<LegacyWorkflowEntry[]>([])
const sourceId = ref<string | null>(null)
const context = ref<WorkflowConversionContext | null>(null)
const draft = ref<WorkflowConversionRequest | null>(null)
const preview = ref<WorkflowConversionPreview | null>(null)
const previewRequest = ref<WorkflowConversionRequest | null>(null)
const created = ref<WorkflowConversionResult | null>(null)
const loading = ref(false)
const busy = ref(false)
const uncertain = ref(false)
const error = ref("")
const key = ref("")
const edgeSource = ref<number | null>(null)
const edgeTarget = ref<number | null>(null)
let sequence = 0
const ready = computed(() => !!context.value && !!draft.value && workflowConversionReady(draft.value, context.value))
const sourceOptions = computed(() => items.value.map(item => ({ label: item.title, value: item.id, disabled: !item.can_convert })))
const nodeOptions = computed(() => context.value?.nodes.map(node => ({ label: `${node.protocol_index}. ${node.name}`, value: node.protocol_index })) ?? [])
function nodeName(index: number) {
  return nodeOptions.value.find(node => node.value === index)?.label ?? index
}
function hasEdge(source: number | null, target: number | null) {
  return !!draft.value?.edges.some(edge => edge.source_protocol_index === source && edge.target_protocol_index === target)
}
function toggleEdge(source: number | null, target: number | null, selected: boolean) {
  if (!draft.value || source === null || target === null || source === target || busy.value)
    return
  draft.value.edges = draft.value.edges.filter(edge => edge.source_protocol_index !== source || edge.target_protocol_index !== target)
  if (selected)
    draft.value.edges.push({ source_protocol_index: source, target_protocol_index: target })
}
function errorText(cause: unknown) {
  const detail = (cause as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === "string" ? detail : t("page.workflowDefinitions.requestFailed")
}
function warningText(warning: { code: string, message: string }) {
  const keys = {
    structure_only: "page.workflowLegacy.previewHint",
    legacy_logic_not_executable: "page.workflowLegacy.logicOmitted",
    execution_history_not_copied: "page.workflowLegacy.preserve",
    legacy_start_not_preserved: "page.workflowLegacy.startOmitted",
    legacy_edges_need_review: "page.workflowLegacy.edgeHint",
    exact_version_required: "page.workflowLegacy.versionHint",
    dependencies_changed: "page.workflowLegacy.changedEdges",
  } as const
  const key = keys[warning.code as keyof typeof keys]
  return key ? t(key, { project: props.projectName }) : warning.message
}
async function loadDirectory() {
  const current = ++sequence
  loading.value = true
  error.value = ""
  try {
    const response = await fetchLegacyWorkflows(props.projectId)
    if (current === sequence)
      items.value = response.items
  }
  catch (cause) {
    if (current === sequence)
      error.value = errorText(cause)
  }
  finally {
    if (current === sequence)
      loading.value = false
  }
}
async function selectSource(id: string) {
  const current = ++sequence
  sourceId.value = id
  context.value = null
  draft.value = null
  preview.value = null
  edgeSource.value = null
  edgeTarget.value = null
  loading.value = true
  error.value = ""
  try {
    const response = await fetchWorkflowConversionContext(id)
    if (current !== sequence)
      return
    context.value = response
    draft.value = createWorkflowConversionDraft(response)
  }
  catch (cause) {
    if (current === sequence)
      error.value = errorText(cause)
  }
  finally {
    if (current === sequence)
      loading.value = false
  }
}
async function requestPreview() {
  if (!sourceId.value || !draft.value || !ready.value || busy.value)
    return
  busy.value = true
  error.value = ""
  try {
    previewRequest.value = JSON.parse(JSON.stringify(draft.value))
    preview.value = await previewWorkflowConversion(sourceId.value, previewRequest.value!)
    key.value = createWorkflowId()
  }
  catch (cause) { error.value = errorText(cause) }
  finally { busy.value = false }
}
function backToEdit() {
  preview.value = null
  previewRequest.value = null
  key.value = ""
  error.value = ""
}
async function confirmConversion() {
  if (!sourceId.value || !preview.value || !previewRequest.value || busy.value)
    return
  busy.value = true
  error.value = ""
  try {
    created.value = await confirmWorkflowConversion(sourceId.value, { ...previewRequest.value, preview_digest: preview.value.preview_digest, idempotency_key: key.value })
    uncertain.value = false
    emit("created", created.value)
  }
  catch (cause) {
    const status = (cause as { response?: { status?: number } })?.response?.status
    uncertain.value = !status || status >= 500
    error.value = errorText(cause)
  }
  finally { busy.value = false }
}
watch(() => props.show, (show) => {
  if (!show) {
    sequence++
    return
  }
  items.value = []
  sourceId.value = null
  context.value = null
  draft.value = null
  preview.value = null
  created.value = null
  uncertain.value = false
  void loadDirectory()
})
watch([busy, uncertain], () => emit("busy", busy.value || uncertain.value))
onBeforeUnmount(() => {
  sequence++
})
</script>

<style scoped>
.workflow-conversion { overflow-wrap: anywhere; }
.conversion-row { padding: 12px; border: 1px solid #dbe3ed; border-radius: 8px; }
.conversion-checks { display: grid; gap: 14px; }
.conversion-edge-picker { display: grid; grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr) auto; align-items: center; gap: 8px; }
pre { max-height: 22rem; overflow: auto; padding: 12px; white-space: pre-wrap; overflow-wrap: anywhere; background: #f8fafc; border-radius: 8px; }
pre:focus-visible { outline: 2px solid #0084e2; outline-offset: 2px; }
@media (max-width: 600px) { .conversion-edge-picker { grid-template-columns: minmax(0, 1fr); } }
</style>
