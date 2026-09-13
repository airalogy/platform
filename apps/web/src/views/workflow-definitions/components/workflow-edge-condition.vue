<template>
  <section class="workflow-edge-condition" :data-edge-id="edge.edge_id">
    <h4 class="aira-type-label mb-2 mt-0">
      {{ sourceTitle }} → {{ targetTitle }}
    </h4>
    <n-select
      :value="edge.condition ? 'conditional' : 'always'" :options="modeOptions" :disabled="disabled"
      :aria-label="$t('page.workflowDefinitions.conditions.mode')" data-testid="workflow-condition-mode" @update:value="setMode"
    />
    <template v-if="edge.condition">
      <n-form-item :label="$t('page.workflowDefinitions.conditions.sourceField')" class="mt-3" label-placement="top">
        <n-select
          :value="workflowPathKey(edge.condition.path)" :options="fieldOptions" :disabled="disabled" filterable
          data-testid="workflow-condition-field" @update:value="setField"
        />
      </n-form-item>
      <div class="workflow-condition-comparison">
        <n-form-item :label="$t('page.workflowDefinitions.conditions.operator')" label-placement="top">
          <n-select
            :value="edge.condition.operator" :options="operatorOptions" :disabled="disabled"
            data-testid="workflow-condition-operator" @update:value="operator => updateCondition({ operator })"
          />
        </n-form-item>
        <n-form-item :label="$t('page.workflowDefinitions.conditions.value')" label-placement="top">
          <n-select
            v-if="edge.condition.value_type === 'boolean'" :value="String(edge.condition.value)" :options="booleanOptions" :disabled="disabled"
            data-testid="workflow-condition-value" @update:value="setValue"
          />
          <n-input
            v-else :value="String(edge.condition.value)" :disabled="disabled" :maxlength="edge.condition.value_type === 'string' ? 2000 : 100"
            data-testid="workflow-condition-value" @update:value="setValue"
          />
        </n-form-item>
      </div>
      <p class="aira-type-meta aira-text-secondary mb-0 mt-0">
        {{ $t(`page.workflowDefinitions.fieldTypes.${edge.condition.value_type}`) }}<template v-if="edge.condition.unit">
          · {{ edge.condition.unit }}
        </template>
        · {{ $t("page.workflowDefinitions.conditions.nullHint") }}
      </p>
    </template>
  </section>
</template>

<script setup lang="ts">
import type { WorkflowCondition, WorkflowControlEdge, WorkflowScalarField } from "@/service/api/workflow-definitions"
import { parseWorkflowScalar, workflowPathKey, workflowPathLabel } from "@/utils/workflow-editor"
import { computed } from "vue"
import { useI18n } from "vue-i18n"

const props = defineProps<{ edge: WorkflowControlEdge, fields: WorkflowScalarField[], sourceTitle: string, targetTitle: string, disabled: boolean }>()
const emit = defineEmits<{ change: [condition: WorkflowCondition | null] }>()
const { t } = useI18n()
const modeOptions = computed(() => [
  { value: "always", label: t("page.workflowDefinitions.conditions.always") },
  { value: "conditional", label: t("page.workflowDefinitions.conditions.conditional"), disabled: !props.fields.length },
])
const fieldOptions = computed(() => props.fields.map(field => ({ value: workflowPathKey(field.path), label: `${field.title || workflowPathLabel(field.path)}${field.unit ? ` (${field.unit})` : ""}` })))
const operatorOptions = computed(() => (["eq", "ne", "gt", "gte", "lt", "lte"] as const)
  .filter(operator => ["number", "integer"].includes(props.edge.condition?.value_type ?? "") || ["eq", "ne"].includes(operator))
  .map(operator => ({ value: operator, label: t(`page.workflowDefinitions.conditions.operators.${operator}`) })))
const booleanOptions = computed(() => [{ value: "true", label: t("page.workflowDefinitions.conditions.true") }, { value: "false", label: t("page.workflowDefinitions.conditions.false") }])

function setMode(mode: string) {
  if (mode === "always")
    emit("change", null)
  else if (props.fields[0])
    setField(workflowPathKey(props.fields[0].path))
}
function setField(key: string) {
  const field = props.fields.find(field => workflowPathKey(field.path) === key)
  if (!field)
    return
  emit("change", { path: [...field.path], value_type: field.value_type, operator: "eq", value: field.value_type === "string" ? "" : field.value_type === "boolean" ? false : 0, unit: field.unit ?? null })
}
function updateCondition(update: Partial<WorkflowCondition>) {
  if (props.edge.condition)
    emit("change", { ...props.edge.condition, ...update })
}
function setValue(value: string) {
  if (!props.edge.condition)
    return
  try {
    updateCondition({ value: parseWorkflowScalar(value, props.edge.condition.value_type) })
  }
  catch {
    // Keep invalid user input in the draft; whole-graph validation prevents
    // previewing a silently retained old value, even after switching cards.
    updateCondition({ value })
  }
}
</script>

<style scoped>
.workflow-edge-condition { min-width: 0; padding: 14px; border: 1px solid #dbe3ed; border-radius: 8px; background: white; overflow-wrap: anywhere; }
.workflow-condition-comparison { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 12px; }
@media (max-width: 479px) { .workflow-condition-comparison { grid-template-columns: minmax(0, 1fr); gap: 0; } }
</style>
