<template>
  <section class="join-editor" data-testid="project-join-editor">
    <h3 class="aira-type-section-title">
      {{ t("page.projectAnalysis.joinConfiguration") }}
    </h3>
    <n-alert type="info" class="mb-4">
      {{ t("page.projectAnalysis.joinHint") }}
    </n-alert>
    <div class="join-columns">
      <n-form-item :label="t('page.projectAnalysis.leftSource')" required>
        <n-select
          :value="model.left_slot_id"
          :options="slotOptions"
          data-testid="project-join-left"
          @update:value="value => changeSide('left_slot_id', value)"
        />
      </n-form-item>
      <n-form-item :label="t('page.projectAnalysis.rightSource')" required>
        <n-select
          :value="model.right_slot_id"
          :options="slotOptions"
          data-testid="project-join-right"
          @update:value="value => changeSide('right_slot_id', value)"
        />
      </n-form-item>
      <n-form-item :label="t('page.projectAnalysis.joinKind')">
        <n-select
          v-model:value="model.kind"
          :options="kindOptions"
          data-testid="project-join-kind"
        />
      </n-form-item>
      <n-form-item :label="t('page.projectAnalysis.missingKeys')">
        <n-select
          v-model:value="model.missing_key_policy"
          :options="missingOptions"
          data-testid="project-join-missing"
        />
      </n-form-item>
    </div>
    <p class="aira-type-meta">
      {{ t("page.projectAnalysis.oneToOne") }}
    </p>
    <h4 class="aira-type-label">
      {{ t("page.projectAnalysis.joinKeys") }}
    </h4>
    <div
      v-for="(key, index) in model.keys"
      :key="index"
      class="join-row mb-3"
      data-testid="project-join-key"
    >
      <n-select
        v-model:value="key.left_field"
        :options="fieldOptions(model.left_slot_id)"
        :aria-label="t('page.projectAnalysis.leftKey')"
        data-testid="project-join-key-left"
      />
      <n-select
        v-model:value="key.right_field"
        :options="fieldOptions(model.right_slot_id)"
        :aria-label="t('page.projectAnalysis.rightKey')"
        data-testid="project-join-key-right"
      />
      <n-button
        size="small"
        :disabled="model.keys.length <= 1"
        @click="model.keys.splice(index, 1)"
      >
        {{ t("common.delete") }}
      </n-button>
    </div>
    <n-button
      size="small"
      :disabled="model.keys.length >= 3"
      @click="model.keys.push({ left_field: '', right_field: '' })"
    >
      {{ t("page.projectAnalysis.addKey") }}
    </n-button>
    <h4 class="aira-type-label mt-5">
      {{ t("page.projectAnalysis.outputFields") }}
    </h4>
    <p class="aira-type-meta">
      {{ t("page.projectAnalysis.outputHint") }}
    </p>
    <article
      v-for="(output, index) in model.outputs"
      :key="index"
      class="join-output mb-3"
      data-testid="project-join-output"
    >
      <div class="join-columns">
        <n-form-item :label="t('page.projectAnalysis.outputId')" required>
          <n-input
            v-model:value="output.output_id"
            :maxlength="24"
            data-testid="project-output-id"
          />
        </n-form-item>
        <n-form-item :label="t('page.projectAnalysis.sourceSlot')" required>
          <n-select
            :value="output.slot_id"
            :options="slotOptions"
            data-testid="project-output-source"
            @update:value="value => changeOutputSource(index, value)"
          />
        </n-form-item>
        <n-form-item :label="t('page.analysis.field')" required>
          <n-select
            :value="output.field || null"
            :options="fieldOptions(output.slot_id)"
            data-testid="project-output-field"
            @update:value="value => changeOutputField(index, value)"
          />
        </n-form-item>
        <n-form-item :label="t('page.projectAnalysis.semanticLabel')" required>
          <n-input
            v-model:value="output.semantic_label"
            :maxlength="255"
            data-testid="project-output-label"
          />
        </n-form-item>
      </div>
      <p class="aira-type-meta">
        {{ t("page.projectAnalysis.sourceUnit") }}:
        {{ output.unit || t("page.analysis.charts.noUnit") }}
      </p>
      <n-button size="small" @click="model.outputs.splice(index, 1)">
        {{ t("common.delete") }}
      </n-button>
    </article>
    <n-button
      size="small"
      :disabled="model.outputs.length >= 20"
      data-testid="project-add-output"
      @click="addOutput"
    >
      {{ t("page.projectAnalysis.addOutput") }}
    </n-button>
    <h4 class="aira-type-label mt-5">
      {{ t("page.projectAnalysis.joinStatistics") }}
    </h4>
    <project-statistics-editor
      v-model="model.recipe"
      :fields="outputFields"
      @validity="valid => emit('validity', valid)"
    />
    <n-checkbox
      v-model:checked="model.semantic_alignment_confirmed"
      class="mt-4"
      data-testid="project-confirm-semantics"
    >
      {{ t("page.projectAnalysis.semanticConfirmation") }}
    </n-checkbox>
  </section>
</template>

<script setup lang="ts">
import type { AnalysisField } from "@/service/api/analysis"
import type { ProjectAnalysisJoin, ProjectAnalysisSlot } from "@/service/api/project-analysis"
import { projectFieldType } from "@/utils/project-analysis"
import { useI18n } from "vue-i18n"
import ProjectStatisticsEditor from "./project-statistics-editor.vue"

const props = defineProps<{
  slots: ProjectAnalysisSlot[]
  fields: Record<string, AnalysisField[]>
}>()
const emit = defineEmits<{ validity: [valid: boolean] }>()
const model = defineModel<ProjectAnalysisJoin>({ required: true })
const { t } = useI18n()
const slotOptions = computed(() =>
  props.slots.map(slot => ({ value: slot.slot_id, label: slot.label || slot.slot_id })),
)
const kindOptions = computed(() =>
  (["inner", "left"] as const).map(value => ({
    value,
    label: t(`page.projectAnalysis.joinKinds.${value}`),
  })),
)
const missingOptions = computed(() =>
  (["error", "exclude"] as const).map(value => ({
    value,
    label: t(`page.projectAnalysis.keyPolicies.${value}`),
  })),
)
function fieldOptions(slotId: string) {
  return (props.fields[slotId] || [])
    .filter(field => ["string", "number", "integer", "boolean"].includes(projectFieldType(field)))
    .map(field => ({
      value: field.key,
      label: `${field.title || field.key} · ${projectFieldType(field)}${field.unit ? ` (${field.unit})` : ""}`,
    }))
}
const outputFields = computed(() =>
  model.value.outputs.flatMap((output) => {
    const source = props.fields[output.slot_id]?.find(field => field.key === output.field)
    return source
      ? [{ ...source, key: output.output_id, title: output.semantic_label || output.output_id }]
      : []
  }),
)
function changeSide(side: "left_slot_id" | "right_slot_id", value: string) {
  model.value[side] = value
}
function changeOutputSource(index: number, value: string) {
  Object.assign(model.value.outputs[index], { slot_id: value, field: "", unit: null })
}
function changeOutputField(index: number, value: string) {
  const output = model.value.outputs[index]
  output.field = value
  output.unit = props.fields[output.slot_id]?.find(field => field.key === value)?.unit || null
}
function addOutput() {
  let number = 1
  while (model.value.outputs.some(output => output.output_id === `value_${number}`)) number += 1
  model.value.outputs.push({
    output_id: `value_${number}`,
    slot_id: model.value.left_slot_id,
    field: "",
    semantic_label: "",
    unit: null,
  })
}
watch(
  [
    () => model.value,
    () => JSON.stringify([model.value.left_slot_id, model.value.right_slot_id, model.value.keys, model.value.outputs]),
  ],
  ([current], [previous]) => {
    // Loading a sealed saved revision is not a user edit of its meaning.
    if (current === previous)
      current.semantic_alignment_confirmed = false
  },
)
</script>

<style scoped>
.join-editor {
  min-width: 0;
  border-top: 1px solid #e5e7eb;
  padding-top: 12px;
}
.join-columns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 12px;
}
.join-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
  gap: 8px;
}
.join-output {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px;
}
@media (max-width: 600px) {
  .join-columns,
  .join-row {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
