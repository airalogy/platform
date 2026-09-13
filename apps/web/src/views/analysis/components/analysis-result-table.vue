<template>
  <div class="analysis-table-scroll" tabindex="0" :aria-label="t('page.analysis.resultTable')">
    <table class="analysis-table" data-testid="analysis-result-table">
      <caption class="sr-only">
        {{ t('page.analysis.resultTable') }}
      </caption>
      <thead>
        <tr>
          <th v-for="key in columns" :key="key" scope="col">
            {{ t(`page.analysis.statistics.${key}`) }}
          </th>
        </tr>
      </thead>
      <tbody>
        <template v-for="(group, index) in result.groups" :key="index">
          <tr v-for="field in result.fields" :key="`${index}:${field.key}`">
            <th scope="row">
              {{ groupLabel(group) }}
            </th>
            <td>
              {{ field.title || field.key }}<template v-if="field.unit">
                ({{ field.unit }})
              </template>
            </td>
            <td v-for="key in statistics" :key="key">
              {{ number(group.fields[field.key][key]) }}
            </td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import type { AnalysisGroup, AnalysisResult } from "@/service/api/analysis"
import { useI18n } from "vue-i18n"

defineProps<{ result: AnalysisResult }>()
const { t, locale } = useI18n()
const statistics = ["count", "missing", "invalid", "mean", "median", "min", "max", "sample_stddev"] as const
const columns = ["group", "field", ...statistics] as const
function number(value: number | null) {
  return value === null ? "—" : value.toLocaleString(locale.value, { maximumSignificantDigits: 8 })
}
function groupLabel(group: AnalysisGroup) {
  return group.key.length ? group.key.map(item => `${item.field}: ${item.value === null ? t("page.analysis.missingGroup") : String(item.value)}`).join(" · ") : t("page.analysis.allRecords")
}
</script>

<style scoped>
.analysis-table-scroll { max-width: 100%; overflow: auto; }
.analysis-table-scroll:focus-visible { outline: 2px solid #0084e2; outline-offset: 2px; }
.analysis-table { width: 100%; border-collapse: collapse; font-size: .8125rem; text-align: left; }
.analysis-table th, .analysis-table td { padding: .65rem .75rem; border-bottom: 1px solid #e5e7eb; white-space: nowrap; }
.analysis-table th { font-weight: 600; }
</style>
