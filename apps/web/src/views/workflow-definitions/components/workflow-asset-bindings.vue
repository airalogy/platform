<template>
  <section class="workflow-asset-bindings mt-4" data-testid="workflow-asset-bindings">
    <h4 class="aira-type-label mt-0">
      {{ $t('page.workflowAssets.bindings') }}
    </h4>
    <p class="aira-type-meta aira-text-secondary">
      {{ $t('page.workflowAssets.bindingHint') }}
    </p>
    <article v-for="binding in nodeBindings" :key="binding.binding_id" class="asset-binding mb-3" data-testid="workflow-asset-binding-item">
      <div class="min-w-0 flex-1">
        <strong>{{ inputLabel(binding.input_id) }}</strong> · {{ workflowPathLabel(binding.source_path) }} → {{ workflowPathLabel(binding.target_path) }}
        <p class="aira-type-meta my-1">
          {{ $t(`page.workflowDefinitions.fieldTypes.${binding.value_type}`) }} <span v-if="binding.unit">· {{ binding.unit }}</span>
        </p>
      </div>
      <n-button size="small" :disabled="disabled" @click="remove(binding.binding_id)">
        {{ $t('common.delete') }}
      </n-button>
    </article>
    <n-empty v-if="!inputs.length" :description="$t('page.workflowAssets.addBeforeBinding')" size="small" />
    <n-form v-else label-placement="top" :disabled="disabled">
      <n-form-item :label="$t('page.workflowAssets.sourceInput')">
        <n-select v-model:value="inputId" :options="inputs.map(input => ({ value: input.input_id, label: input.label }))" data-testid="workflow-asset-binding-input" />
      </n-form-item>
      <n-form-item :label="$t('page.workflowAssets.valueKind')">
        <n-select v-model:value="valueType" :options="typeOptions" data-testid="workflow-asset-binding-type" />
      </n-form-item>
      <template v-if="valueType !== 'file'">
        <p class="aira-type-meta aira-text-secondary">
          {{ $t('page.workflowAssets.jsonPathHint') }}
        </p>
        <div v-for="(_, index) in pathKeys" :key="index" class="asset-path-row mb-2">
          <n-input v-model:value="pathKeys[index]" :maxlength="255" :aria-label="$t('page.workflowAssets.pathKey', { number: index + 1 })" data-testid="workflow-asset-json-key" />
          <n-button :disabled="disabled || pathKeys.length <= 1" :aria-label="$t('common.delete')" @click="pathKeys.splice(index, 1)">
            −
          </n-button>
        </div>
        <n-button size="small" class="mb-3" :disabled="disabled || pathKeys.length >= 16" data-testid="workflow-asset-add-key" @click="pathKeys.push('')">
          {{ $t('page.workflowAssets.addPathKey') }}
        </n-button>
        <n-form-item v-if="valueType === 'number' || valueType === 'integer'" :label="$t('page.workflowAssets.unit')">
          <n-input v-model:value="unit" :maxlength="255" data-testid="workflow-asset-binding-unit" />
        </n-form-item>
      </template>
      <n-alert v-else type="info" class="mb-3">
        {{ $t('page.workflowAssets.wholeFileHint') }}
      </n-alert>
      <n-form-item :label="$t('page.workflowDefinitions.bindings.targetField')">
        <n-select v-model:value="targetKey" :options="targetFields.map(field => ({ value: workflowPathKey(field.path), label: field.title + (field.value_type === 'file' ? ` (${field.file_extensions?.join(', ') || '*'})` : field.unit ? ` (${field.unit})` : '') }))" filterable data-testid="workflow-asset-binding-target" />
        <template #feedback>
          {{ $t('page.workflowDefinitions.bindings.targetHint') }}
        </template>
      </n-form-item>
      <n-button :disabled="disabled || !valid" data-testid="workflow-asset-binding-add" @click="add">
        {{ $t('page.workflowAssets.addBinding') }}
      </n-button>
    </n-form>
  </section>
</template>

<script setup lang="ts">
import type { WorkflowAssetBinding, WorkflowContext, WorkflowGraph, WorkflowProtocolNode, WorkflowScalarType } from "@/service/api/workflow-definitions"
import { createWorkflowId, workflowAssetSourceField, workflowFields, workflowFieldsCompatible, workflowPathKey, workflowPathLabel } from "@/utils/workflow-editor"
import { computed, ref, watch } from "vue"
import { useI18n } from "vue-i18n"

const props = defineProps<{ graph: WorkflowGraph, node: WorkflowProtocolNode, protocols: WorkflowContext["protocols"], disabled: boolean }>()
const emit = defineEmits<{ change: [bindings: WorkflowAssetBinding[]] }>()
const { t } = useI18n()
const inputId = ref<string | null>(null)
const valueType = ref<WorkflowScalarType | "file">("file")
const pathKeys = ref([""])
const unit = ref("")
const targetKey = ref<string | null>(null)
const inputs = computed(() => props.graph.asset_inputs ?? [])
const nodeBindings = computed(() => (props.graph.asset_bindings ?? []).filter(binding => binding.target_node_id === props.node.node_id))
const typeOptions = computed(() => (["file", "number", "integer", "string", "boolean"] as const).map(value => ({ value, label: t(value === "file" ? "page.workflowAssets.wholeFile" : `page.workflowDefinitions.fieldTypes.${value}`) })))
const source = computed(() => workflowAssetSourceField({ source_path: valueType.value === "file" ? ["file"] : ["json", ...pathKeys.value], value_type: valueType.value, unit: ["number", "integer"].includes(valueType.value) ? unit.value.trim() || null : null }))
const targetFields = computed(() => workflowFields(props.node, props.protocols).filter(field => workflowFieldsCompatible(source.value, field)
  && ![...props.graph.bindings, ...(props.graph.asset_bindings ?? [])].some(binding => binding.target_node_id === props.node.node_id && workflowPathKey(binding.target_path) === workflowPathKey(field.path))
  && !Object.hasOwn(props.node.initial_values, field.path[1])))
const target = computed(() => targetFields.value.find(field => workflowPathKey(field.path) === targetKey.value))
const valid = computed(() => inputs.value.some(input => input.input_id === inputId.value) && target.value && (valueType.value === "file" || pathKeys.value.every(key => key.length > 0 && key.length <= 255)) && props.graph.bindings.length + (props.graph.asset_bindings?.length ?? 0) < 128)
function inputLabel(id: string) {
  return inputs.value.find(input => input.input_id === id)?.label ?? id
}
function remove(id: string) {
  emit("change", (props.graph.asset_bindings ?? []).filter(binding => binding.binding_id !== id))
}
function add() {
  if (!valid.value || props.disabled || !inputId.value || !target.value)
    return
  emit("change", [...(props.graph.asset_bindings ?? []), { binding_id: `asset_binding_${createWorkflowId()}`, input_id: inputId.value, source_path: [...source.value.path], target_node_id: props.node.node_id, target_path: [...target.value.path], value_type: source.value.value_type, unit: source.value.unit, cardinality: "one" }])
  targetKey.value = null
}
watch(() => props.node.node_id, () => {
  inputId.value = null
  targetKey.value = null
})
watch([valueType, unit], () => {
  targetKey.value = null
})
</script>

<style scoped>
.workflow-asset-bindings { min-width: 0; padding: 14px; border: 1px solid #cbd5e1; border-radius: 8px; background: white; overflow-wrap: anywhere; }
.asset-binding, .asset-path-row { display: flex; align-items: start; gap: 10px; }
.asset-binding { flex-wrap: wrap; padding: 10px; border: 1px solid #e2e8f0; border-radius: 6px; }
</style>
