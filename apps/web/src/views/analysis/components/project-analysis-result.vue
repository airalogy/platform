<template>
  <section class="project-results" data-testid="project-analysis-result">
    <n-alert type="info" class="my-3">
      {{
        t(
          result.mode === "evidence_synthesis"
            ? "page.projectAnalysis.separateEvidence"
            : "page.projectAnalysis.associationOnly",
        )
      }}
    </n-alert>
    <p class="aira-type-body">
      {{
        t("page.projectAnalysis.sourceCounts", {
          protocols: result.counts.protocols,
          records: result.counts.records,
        })
      }}
    </p>
    <article
      v-for="local in result.local_results"
      :key="local.slot_id"
      class="local-result"
      data-testid="project-local-result"
    >
      <h3 class="aira-type-section-title">
        {{ local.label }}
      </h3>
      <p class="aira-type-body">
        {{ t("page.analysis.countSummary", { ...local.report.counts }) }}
      </p>
      <n-alert
        v-for="(warning, index) in local.report.warnings"
        :key="index"
        type="warning"
        class="mb-2"
      >
        {{
          t(`page.analysis.warnings.${warning.code}`, {
            field: warning.field || "",
            count: warning.count,
          })
        }}
      </n-alert>
      <analysis-result-charts :result="local.report" />
      <analysis-result-table :result="local.report" />
    </article>
    <template v-if="result.join">
      <h3 class="aira-type-section-title mt-5">
        {{ t("page.projectAnalysis.joinedResult") }}
      </h3>
      <project-join-audit :audit="result.join.audit" :labels="labels" />
      <analysis-result-charts :result="result.join.report" :ungrouped-label="t('page.projectAnalysis.allJoinedRows')" />
      <analysis-result-table :result="result.join.report" :ungrouped-label="t('page.projectAnalysis.allJoinedRows')" />
      <details class="aira-disclosure mt-4" data-testid="project-join-lineage">
        <summary>
          {{
            t("page.projectAnalysis.joinedSources", { count: result.join.rows.length })
          }}
        </summary>
        <p class="aira-type-meta">
          {{ t("page.projectAnalysis.lineageHint") }}
        </p>
        <article v-for="row in result.join.rows" :key="row.row_id" class="lineage-row mb-3">
          <dl>
            <template v-for="field in result.join.fields" :key="field.output_id">
              <dt>
                {{ field.semantic_label }}<span v-if="field.unit"> ({{ field.unit }})</span>
              </dt>
              <dd>
                {{ row.values[field.output_id] === null ? "—" : row.values[field.output_id]
                }}<br><span class="aira-type-meta">{{ labels[field.slot_id] || field.slot_id }} · {{ field.field }}</span>
              </dd>
            </template>
          </dl>
          <div v-for="(source, slotId) in row.sources" :key="slotId" class="aira-type-meta mt-2">
            {{ labels[slotId] || slotId }}:
            <n-button v-if="source" text class="source-link" @click="emit('source', source)">
              Record {{ source.record_id }} · v{{ source.record_version }} · Protocol
              {{ source.protocol_version }}
            </n-button>
            <span v-else>{{ t("page.projectAnalysis.unmatchedSource") }}</span>
          </div>
        </article>
      </details>
    </template>
  </section>
</template>

<script setup lang="ts">
import type {
  ProjectAnalysisRecordRef,
  ProjectAnalysisResult,
} from "@/service/api/project-analysis"
import { useI18n } from "vue-i18n"
import AnalysisResultCharts from "./analysis-result-charts.vue"
import AnalysisResultTable from "./analysis-result-table.vue"
import ProjectJoinAudit from "./project-join-audit.vue"

const props = defineProps<{ result: ProjectAnalysisResult }>()
const emit = defineEmits<{ source: [source: ProjectAnalysisRecordRef] }>()
const { t } = useI18n()
const labels = computed(() =>
  Object.fromEntries(props.result.local_results.map(item => [item.slot_id, item.label])),
)
</script>

<style scoped>
.project-results {
  min-width: 0;
}
.local-result {
  margin-top: 20px;
  padding-top: 4px;
  border-top: 1px solid #e5e7eb;
}
.lineage-row {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px;
}
dl {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 8px;
  overflow-wrap: anywhere;
}
dd {
  margin: 0;
}
.source-link {
  max-width: 100%;
  white-space: normal;
  height: auto;
  text-align: left;
}
.source-link :deep(.n-button__content) {
  white-space: normal;
  overflow-wrap: anywhere;
}
@media (max-width: 600px) {
  dl {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
