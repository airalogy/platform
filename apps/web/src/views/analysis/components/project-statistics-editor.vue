<template>
  <div class="statistics-editor" data-testid="project-statistics-editor">
    <n-form-item :label="t('page.analysis.numericFields')" required>
      <n-select
        v-model:value="model.numeric_fields"
        :options="numericOptions"
        multiple
        filterable
        :max="20"
        data-testid="project-numeric-fields"
      />
    </n-form-item>
    <n-form-item :label="t('page.analysis.groupBy')">
      <n-select
        v-model:value="model.group_by"
        :options="scalarOptions"
        multiple
        filterable
        clearable
        :max="3"
        data-testid="project-group-by"
      />
    </n-form-item>
    <div class="statistics-options">
      <n-form-item :label="t('page.analysis.missingPolicy')">
        <n-select v-model:value="model.missing_policy" :options="missingOptions" />
      </n-form-item>
      <n-form-item :label="t('page.analysis.charts.selector')">
        <n-select
          v-model:value="model.chart"
          :options="chartOptions"
          data-testid="project-chart-type"
        />
      </n-form-item>
    </div>
    <n-collapse>
      <n-collapse-item
        :title="t('page.analysis.fieldFilters', { count: model.filters.length })"
        name="filters"
      >
        <div v-for="(filter, index) in model.filters" :key="index" class="statistics-filter mb-3">
          <n-select
            :value="filter.field"
            :options="scalarOptions"
            :placeholder="t('page.analysis.field')"
            :aria-label="t('page.analysis.field')"
            @update:value="value => changeField(index, value)"
          />
          <n-select
            :value="filter.op"
            :options="operators(filter.field)"
            :aria-label="t('page.analysis.operator')"
            @update:value="value => changeOperator(index, value)"
          />
          <n-input
            v-if="!['missing', 'present'].includes(filter.op)"
            :value="valueText(filter)"
            :type="filter.op === 'in' ? 'textarea' : 'text'"
            :aria-label="t('page.analysis.value')"
            :placeholder="
              filter.op === 'in' ? t('page.analysis.valuesHint') : t('page.analysis.value')
            "
            @update:value="value => changeValue(index, value)"
          />
          <n-alert v-if="invalid.has(filter)" type="warning">
            {{ t("page.analysis.invalidFilterValue") }}
          </n-alert>
          <n-button size="small" @click="removeFilter(index)">
            {{ t("common.delete") }}
          </n-button>
        </div>
        <n-button
          :disabled="model.filters.length >= 20 || !scalarOptions.length"
          size="small"
          data-testid="project-add-filter"
          @click="addFilter"
        >
          {{ t("page.analysis.addFilter") }}
        </n-button>
      </n-collapse-item>
    </n-collapse>
  </div>
</template>

<script setup lang="ts">
import type { AnalysisField, AnalysisFilter, AnalysisRecipe } from "@/service/api/analysis"
import { analysisFieldType, parseAnalysisFieldOperand } from "@/utils/analysis-context"
import { useI18n } from "vue-i18n"

const props = defineProps<{ fields: AnalysisField[] }>()
const emit = defineEmits<{ validity: [valid: boolean] }>()
const model = defineModel<AnalysisRecipe>({ required: true })
const { t } = useI18n()
const invalid = reactive(new Map<AnalysisFilter, string>())
const scalarFields = computed(() =>
  props.fields.filter(field =>
    ["string", "number", "integer", "boolean"].includes(analysisFieldType(field)),
  ),
)
function option(field: AnalysisField) {
  return {
    value: field.key,
    label: `${field.title || field.key}${field.unit ? ` (${field.unit})` : ""}`,
  }
}
const scalarOptions = computed(() => scalarFields.value.map(option))
const numericOptions = computed(() =>
  scalarFields.value
    .filter(field => ["number", "integer"].includes(analysisFieldType(field)))
    .map(option),
)
const missingOptions = computed(() =>
  (["exclude", "error"] as const).map(value => ({
    value,
    label: t(`page.analysis.missing.${value}`),
  })),
)
const chartOptions = computed(() =>
  (["none", "bar", "line"] as const).map(value => ({
    value,
    label: t(`page.analysis.charts.types.${value}`),
  })),
)
function operators(key: string) {
  const numeric = ["number", "integer"].includes(
    analysisFieldType(props.fields.find(field => field.key === key)),
  )
  return (
    numeric
      ? ["eq", "ne", "gt", "gte", "lt", "lte", "in", "missing", "present"]
      : ["eq", "ne", "in", "missing", "present"]
  ).map(value => ({ value, label: t(`page.analysis.operators.${value}`) }))
}
function valueText(filter: AnalysisFilter) {
  return (
    invalid.get(filter)
    ?? (Array.isArray(filter.value)
      ? filter.value.map(String).join("\n")
      : filter.value === null
        ? ""
        : String(filter.value))
  )
}
function changeValue(index: number, value: string) {
  const filter = model.value.filters[index]
  const field = props.fields.find(field => field.key === filter.field)
  try {
    filter.value = ["missing", "present"].includes(filter.op)
      ? null
      : filter.op === "in"
        ? value.split("\n").map(item => parseAnalysisFieldOperand(item, field))
        : parseAnalysisFieldOperand(value, field)
    invalid.delete(filter)
  }
  catch {
    invalid.set(filter, value)
  }
  emit("validity", !invalid.size)
}
function changeField(index: number, field: string) {
  model.value.filters[index].field = field
  model.value.filters[index].op = "eq"
  changeValue(index, "")
}
function changeOperator(index: number, op: AnalysisFilter["op"]) {
  const filter = model.value.filters[index]
  const previous = valueText(filter)
  filter.op = op
  changeValue(index, previous)
}
function removeFilter(index: number) {
  invalid.delete(model.value.filters[index])
  model.value.filters.splice(index, 1)
  emit("validity", !invalid.size)
}
function addFilter() {
  model.value.filters.push({ field: scalarFields.value[0]?.key || "", op: "present", value: null })
}
watch(
  () => model.value,
  () => {
    invalid.clear()
    emit("validity", true)
  },
)
</script>

<style scoped>
.statistics-editor {
  min-width: 0;
}
.statistics-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.statistics-filter {
  display: grid;
  gap: 8px;
  padding: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}
@media (max-width: 600px) {
  .statistics-options {
    grid-template-columns: minmax(0, 1fr);
    gap: 0;
  }
}
</style>
