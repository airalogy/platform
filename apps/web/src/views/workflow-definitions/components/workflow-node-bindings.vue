<template>
  <section class="workflow-bindings" data-testid="workflow-node-bindings">
    <h4 class="aira-type-label mb-2 mt-0">
      {{ $t("page.workflowDefinitions.bindings.title") }}
    </h4>
    <p class="aira-type-meta aira-text-secondary mt-0">
      {{ $t("page.workflowDefinitions.bindings.hint") }}
    </p>
    <n-alert v-if="sourceField?.value_type === 'file' || nodeBindings.some(binding => binding.value_type === 'file')" type="info" class="mb-3">
      {{ $t('page.workflowFiles.bindingHint') }}
    </n-alert>
    <article v-for="binding in nodeBindings" :key="binding.binding_id" class="workflow-binding-row mb-3" data-testid="workflow-binding-item">
      <div class="min-w-0">
        <strong>{{ nodeTitle(binding.source_node_id) }}</strong>: {{ fieldLabel(binding.source_node_id, binding.source_path) }}
        <span class="mx-1">→</span>
        <strong>{{ node.title }}</strong>: {{ fieldLabel(node.node_id, binding.target_path) }}
        <div class="aira-type-meta aira-text-secondary mt-1">
          {{ $t(`page.workflowDefinitions.fieldTypes.${binding.value_type}`) }}<template v-if="binding.unit">
            · {{ binding.unit }}
          </template>
          · {{ $t(binding.value_type === 'file' ? 'page.workflowFiles.oneFile' : 'page.workflowDefinitions.bindings.oneValue') }}
        </div>
      </div>
      <n-button size="small" :disabled="disabled" @click="removeBinding(binding.binding_id)">
        {{ $t("common.delete") }}
      </n-button>
    </article>
    <n-empty v-if="!nodeBindings.length" :description="$t('page.workflowDefinitions.bindings.none')" size="small" class="mb-3" />
    <n-form label-placement="top" :disabled="disabled">
      <n-form-item :label="$t('page.workflowDefinitions.bindings.sourceCard')">
        <n-select v-model:value="sourceNodeId" :options="sourceOptions" clearable data-testid="workflow-binding-source-card" />
      </n-form-item>
      <n-form-item :label="$t('page.workflowDefinitions.bindings.sourceField')">
        <n-select v-model:value="sourcePathKey" :options="sourceFieldOptions" :disabled="disabled || !sourceNodeId" filterable data-testid="workflow-binding-source-field" />
      </n-form-item>
      <n-form-item :label="$t('page.workflowDefinitions.bindings.targetField')">
        <n-select v-model:value="targetPathKey" :options="targetFieldOptions" :disabled="disabled || !sourceField" filterable data-testid="workflow-binding-target-field" />
        <template #feedback>
          {{ $t("page.workflowDefinitions.bindings.targetHint") }}
        </template>
      </n-form-item>
      <n-button :disabled="disabled || !sourceNodeId || !sourceField || !targetField" data-testid="workflow-binding-add" @click="addBinding">
        {{ $t("page.workflowDefinitions.bindings.add") }}
      </n-button>
    </n-form>
  </section>
</template>

<script setup lang="ts">
import type { WorkflowContext, WorkflowField, WorkflowGraph, WorkflowProtocolNode, WorkflowScalarBinding } from "@/service/api/workflow-definitions"
import { createWorkflowId, workflowFields, workflowFieldsCompatible, workflowPathKey, workflowPathLabel } from "@/utils/workflow-editor"
import { computed, ref, watch } from "vue"

const props = defineProps<{ graph: WorkflowGraph, node: WorkflowProtocolNode, protocols: WorkflowContext["protocols"], analysisFields?: Record<string, WorkflowField[]>, disabled: boolean }>()
const emit = defineEmits<{ change: [bindings: WorkflowScalarBinding[]] }>()
const sourceNodeId = ref<string | null>(null)
const sourcePathKey = ref<string | null>(null)
const targetPathKey = ref<string | null>(null)
const nodeBindings = computed(() => props.graph.bindings.filter(binding => binding.target_node_id === props.node.node_id))
const sources = computed(() => props.graph.nodes.filter(node => props.graph.edges.some(edge => edge.source_node_id === node.node_id && edge.target_node_id === props.node.node_id)))
const sourceOptions = computed(() => sources.value.map(node => ({ label: node.title, value: node.node_id })))
const sourceFields = computed(() => workflowFields(sources.value.find(node => node.node_id === sourceNodeId.value), props.protocols, props.analysisFields))
const sourceField = computed(() => sourceFields.value.find(field => workflowPathKey(field.path) === sourcePathKey.value))
const targetFields = computed(() => workflowFields(props.node, props.protocols).filter((field) => {
  return sourceField.value && workflowFieldsCompatible(sourceField.value, field)
    && ![...nodeBindings.value, ...(props.graph.asset_bindings ?? []).filter(binding => binding.target_node_id === props.node.node_id)].some(binding => workflowPathKey(binding.target_path) === workflowPathKey(field.path))
    && !Object.hasOwn(props.node.initial_values, field.path[1])
}))
const targetField = computed(() => targetFields.value.find(field => workflowPathKey(field.path) === targetPathKey.value))
const sourceFieldOptions = computed(() => sourceFields.value.map(field => ({ label: label(field), value: workflowPathKey(field.path) })))
const targetFieldOptions = computed(() => targetFields.value.map(field => ({ label: label(field), value: workflowPathKey(field.path) })))

function label(field: WorkflowField) {
  return `${field.title || workflowPathLabel(field.path)}${field.value_type === "file" ? ` (${field.file_extensions?.join(", ") || "*"})` : field.unit ? ` (${field.unit})` : ""}`
}
function nodeTitle(id: string) {
  return props.graph.nodes.find(node => node.node_id === id)?.title ?? id
}
function fieldLabel(id: string, path: string[]) {
  return workflowFields(props.graph.nodes.find(node => node.node_id === id), props.protocols, props.analysisFields).find(field => workflowPathKey(field.path) === workflowPathKey(path))?.title || workflowPathLabel(path)
}
function removeBinding(id: string) {
  emit("change", props.graph.bindings.filter(binding => binding.binding_id !== id))
}
function addBinding() {
  if (!sourceNodeId.value || !sourceField.value || !targetField.value || props.disabled || props.graph.bindings.length + (props.graph.asset_bindings?.length ?? 0) >= 128)
    return
  emit("change", [...props.graph.bindings, {
    binding_id: `binding_${createWorkflowId()}`,
    source_node_id: sourceNodeId.value,
    source_path: [...sourceField.value.path],
    target_node_id: props.node.node_id,
    target_path: [...targetField.value.path],
    value_type: sourceField.value.value_type,
    unit: sourceField.value.unit ?? null,
    cardinality: "one",
  }])
  sourcePathKey.value = null
  targetPathKey.value = null
}
watch(() => props.node.node_id, () => {
  sourceNodeId.value = null
  sourcePathKey.value = null
  targetPathKey.value = null
})
watch(sourceNodeId, () => {
  sourcePathKey.value = null
})
watch(sourcePathKey, () => {
  targetPathKey.value = null
})
</script>

<style scoped>
.workflow-bindings { min-width: 0; padding: 14px; border: 1px solid #dbe3ed; border-radius: 8px; background: white; }
.workflow-binding-row { display: flex; flex-wrap: wrap; align-items: start; justify-content: space-between; gap: 10px; padding: 12px; border: 1px solid #e2e8f0; border-radius: 8px; overflow-wrap: anywhere; }
</style>
