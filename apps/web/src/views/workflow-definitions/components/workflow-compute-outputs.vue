<template>
  <section class="compute-outputs" data-testid="workflow-compute-outputs">
    <n-alert type="info" class="mb-3">
      {{ t('page.workflowAnalysis.computePortsHint') }}
    </n-alert>
    <n-alert v-if="error" type="error" class="mb-3">
      {{ error }}<n-button :disabled="loading" @click="loadCatalog">
        {{ t('common.retry') }}
      </n-button>
    </n-alert>
    <article v-for="output in node.compute_outputs" :key="output.output_id" class="compute-output-row mb-3" data-testid="workflow-compute-output">
      <div class="min-w-0">
        <strong>{{ output.output_id }}</strong><p class="aira-type-meta my-1">
          {{ workflowPathLabel(output.path) }} · {{ t(`page.workflowDefinitions.fieldTypes.${output.value_type}`) }} · {{ output.unit || '—' }} · {{ t(output.nullable ? 'page.workflowAnalysis.nullableOutput' : 'page.workflowAnalysis.requiredOutput') }}
        </p>
      </div>
      <n-button size="small" :disabled="disabled" @click="emit('change', node.compute_outputs.filter(item => item.output_id !== output.output_id))">
        {{ t('common.delete') }}
      </n-button>
    </article>
    <p v-if="!node.compute_outputs.length" class="aira-type-meta">
      {{ t('page.workflowAnalysis.noOutputs') }}
    </p>
    <n-form label-placement="top" :disabled="disabled || loading">
      <n-form-item :label="t('page.workflowAnalysis.outputName')">
        <n-input v-model:value="outputId" :maxlength="64" data-testid="workflow-compute-output-id" />
      </n-form-item>
      <n-form-item :label="t('page.workflowAnalysis.computeResultPath')">
        <n-select v-model:value="pathKey" :options="options" :loading="loading" filterable data-testid="workflow-compute-output-path" />
      </n-form-item>
      <p v-if="selected" class="aira-type-meta" data-testid="workflow-compute-output-type">
        {{ t(`page.workflowDefinitions.fieldTypes.${selected.value_type}`) }} · {{ selected.unit || '—' }} · {{ t(selected.nullable ? 'page.workflowAnalysis.nullableOutput' : 'page.workflowAnalysis.requiredOutput') }}
      </p>
      <p v-if="!loading && !error && !fields.length" class="aira-type-meta">
        {{ t('page.workflowAnalysis.noScalarOutputs') }}
      </p>
      <n-button :disabled="!canAdd || disabled || loading" data-testid="workflow-compute-add-output" @click="addOutput">
        {{ t('page.workflowAnalysis.addOutput') }}
      </n-button>
    </n-form>
    <section class="mt-5" data-testid="workflow-compute-file-outputs">
      <h4 class="aira-type-label">
        {{ t('page.workflowFiles.outputs') }}
      </h4>
      <p class="aira-type-meta">
        {{ t('page.workflowFiles.outputHint') }}
      </p>
      <article v-for="output in node.compute_file_outputs ?? []" :key="output.output_id" class="compute-output-row mb-3" data-testid="workflow-compute-file-output">
        <div class="min-w-0">
          <strong>{{ output.output_id }}</strong><p class="aira-type-meta my-1">
            {{ output.mount_name }}
          </p>
        </div>
        <n-button size="small" :disabled="disabled" @click="emit('files', node.compute_file_outputs?.filter(item => item.output_id !== output.output_id) ?? [])">
          {{ t('common.delete') }}
        </n-button>
      </article>
      <n-empty v-if="!loading && !fileFields.length" :description="t('page.workflowFiles.noOutputs')" size="small" />
      <n-form v-else label-placement="top" :disabled="disabled || loading">
        <n-form-item :label="t('page.workflowAnalysis.outputName')">
          <n-input v-model:value="fileOutputId" :maxlength="64" data-testid="workflow-file-output-id" />
        </n-form-item>
        <n-form-item :label="t('page.workflowFiles.declaredFile')">
          <n-select v-model:value="fileMountName" :options="fileOptions" data-testid="workflow-file-output-mount" />
        </n-form-item>
        <p v-if="selectedFile" class="aira-type-meta" data-testid="workflow-file-output-contract">
          {{ selectedFile.media_type }} · ≤ {{ selectedFile.max_bytes }} B · {{ selectedFile.file_extensions?.join(', ') || '*' }} · {{ t(selectedFile.required ? 'page.instrumentFiles.required' : 'page.instrumentFiles.optional') }}
        </p>
        <n-button :disabled="disabled || loading || !canAddFile" data-testid="workflow-file-output-add" @click="addFileOutput">
          {{ t('page.workflowAnalysis.addOutput') }}
        </n-button>
      </n-form>
    </section>
  </section>
</template>

<script setup lang="ts">
import type { WorkflowComputeFileField, WorkflowComputeFileOutput, WorkflowComputeOutput } from "@/service/api/workflow-analysis-methods"
import type { WorkflowComputeAnalysisNode, WorkflowScalarField } from "@/service/api/workflow-definitions"
import { fetchWorkflowComputeOutputCatalog } from "@/service/api/workflow-analysis-methods"
import { createWorkflowComputeFileOutput, createWorkflowComputeOutput, workflowPathKey, workflowPathLabel } from "@/utils/workflow-editor"
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { useI18n } from "vue-i18n"

const props = defineProps<{ node: WorkflowComputeAnalysisNode, disabled: boolean }>()
const emit = defineEmits<{ change: [outputs: WorkflowComputeOutput[]], files: [outputs: WorkflowComputeFileOutput[]] }>()
const { t } = useI18n()
const fields = ref<WorkflowScalarField[]>([])
const fileFields = ref<WorkflowComputeFileField[]>([])
const fileOutputId = ref("")
const fileMountName = ref<string | null>(null)
const fileOptions = computed(() => fileFields.value.map(file => ({ label: `${file.title} (${file.mount_name})`, value: file.mount_name })))
const selectedFile = computed(() => fileFields.value.find(file => file.mount_name === fileMountName.value))
const canAddFile = computed(() => !!selectedFile.value && uniqueOutputId(fileOutputId.value))
const loading = ref(false)
const error = ref("")
const outputId = ref("")
const pathKey = ref<string | null>(null)
let sequence = 0
const options = computed(() => fields.value.map(field => ({ label: workflowPathLabel(field.path), value: workflowPathKey(field.path) })))
const selected = computed(() => fields.value.find(field => workflowPathKey(field.path) === pathKey.value))
const canAdd = computed(() => !!selected.value && uniqueOutputId(outputId.value))
function uniqueOutputId(id: string) {
  return /^[a-z][a-z0-9_-]{0,63}$/.test(id) && !props.node.compute_outputs.some(output => output.output_id === id) && !props.node.compute_file_outputs?.some(output => output.output_id === id)
}
function addFileOutput() {
  if (!canAddFile.value || !selectedFile.value || props.disabled)
    return
  emit("files", [...(props.node.compute_file_outputs ?? []), createWorkflowComputeFileOutput(fileOutputId.value, selectedFile.value)])
  fileOutputId.value = ""
}
async function loadCatalog() {
  const current = ++sequence
  fields.value = []
  fileFields.value = []
  loading.value = true
  error.value = ""
  try {
    const response = await fetchWorkflowComputeOutputCatalog(props.node.method_publication_id)
    if (current === sequence) {
      fields.value = response.fields
      fileFields.value = response.file_fields ?? []
    }
  }
  catch (cause) {
    if (current === sequence) {
      const detail = (cause as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      error.value = typeof detail === "string" ? detail : t("page.workflowDefinitions.requestFailed")
    }
  }
  finally {
    if (current === sequence)
      loading.value = false
  }
}
function addOutput() {
  if (!canAdd.value || !selected.value || props.disabled)
    return
  emit("change", [...props.node.compute_outputs, createWorkflowComputeOutput(outputId.value, selected.value)])
  outputId.value = ""
}
watch(() => [props.node.node_id, props.node.method_publication_id], () => {
  outputId.value = ""
  pathKey.value = null
  fileOutputId.value = ""
  fileMountName.value = null
  void loadCatalog()
}, { immediate: true })
onBeforeUnmount(() => {
  sequence++
})
</script>

<style scoped>
.compute-outputs { min-width: 0; }
.compute-output-row { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; padding: 12px; border: 1px solid #e2e8f0; border-radius: 8px; overflow-wrap: anywhere; }
</style>
