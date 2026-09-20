<template>
  <section class="comparison mt-6" data-testid="project-analysis-comparison">
    <h3 class="aira-type-section-title">
      {{ t("page.projectAnalysis.comparison.title") }}
    </h3>
    <p class="aira-type-meta">
      {{ t("page.projectAnalysis.comparison.hint") }}
    </p>
    <div class="flex flex-wrap gap-2">
      <n-select
        v-model:value="baselineId"
        class="min-w-0 flex-1"
        :options="options"
        :placeholder="t('page.projectAnalysis.comparison.baseline')"
        data-testid="project-comparison-baseline"
      /><n-button
        :disabled="!baselineId"
        :loading="loading"
        data-testid="project-compare"
        @click="compare"
      >
        {{ t("page.projectAnalysis.comparison.compare") }}
      </n-button>
    </div>
    <n-alert v-if="error" type="error" class="my-3">
      {{ error }}
    </n-alert>
    <template v-if="comparison">
      <n-alert :type="comparison.recipe_changed ? 'warning' : 'info'" class="my-3">
        {{
          t(
            comparison.recipe_changed
              ? "page.projectAnalysis.comparison.recipeChanged"
              : "page.projectAnalysis.comparison.sameRecipe",
          )
        }}
      </n-alert>
      <article
        v-for="input in comparison.inputs"
        :key="input.slot_id"
        class="comparison-source my-3"
        data-testid="project-comparison-source"
      >
        <h4>{{ label(input.slot_id) }}</h4><p>
          {{
            t("page.projectAnalysis.comparison.sourceChanges", {
              added: input.added.length,
              removed: input.removed.length,
              changed: input.changed.length,
            })
          }}
        </p>
        <details>
          <summary>{{ t("page.analysis.provenance") }}</summary><p v-for="record in input.added" :key="`a-${record.record_id}`" class="aira-type-meta">
            + Record {{ record.record_id }} · v{{ record.record_version }}
          </p><p v-for="record in input.removed" :key="`r-${record.record_id}`" class="aira-type-meta">
            − Record {{ record.record_id }} · v{{ record.record_version }}
          </p><p v-for="record in input.changed" :key="record.before.record_id" class="aira-type-meta">
            Record {{ record.before.record_id }} · v{{ record.before.record_version }} → v{{
              record.after.record_version
            }}
          </p>
        </details>
      </article>
      <details
        v-for="local in comparison.local_results"
        :key="local.slot_id"
        class="aira-disclosure"
      >
        <summary>
          {{ label(local.slot_id) }} ·
          {{
            t(
              local.changed
                ? "page.projectAnalysis.comparison.changed"
                : "page.projectAnalysis.comparison.unchanged",
            )
          }}
        </summary>
        <h4>{{ t("page.projectAnalysis.comparison.before") }}</h4><analysis-result-table :result="local.before" />
        <h4>{{ t("page.projectAnalysis.comparison.after") }}</h4><analysis-result-table :result="local.after" />
      </details>
      <details v-if="comparison.join.before || comparison.join.after" class="aira-disclosure">
        <summary>
          {{ t("page.projectAnalysis.joinedResult") }} ·
          {{
            t(
              comparison.join.changed
                ? "page.projectAnalysis.comparison.changed"
                : "page.projectAnalysis.comparison.unchanged",
            )
          }}
        </summary>
        <template v-if="comparison.join.before">
          <h4>{{ t("page.projectAnalysis.comparison.before") }}</h4><project-join-audit :audit="comparison.join.before.audit" /><analysis-result-table
            :result="comparison.join.before.report"
            :ungrouped-label="t('page.projectAnalysis.allJoinedRows')"
          />
        </template>
        <template v-if="comparison.join.after">
          <h4>{{ t("page.projectAnalysis.comparison.after") }}</h4><project-join-audit :audit="comparison.join.after.audit" /><analysis-result-table
            :result="comparison.join.after.report"
            :ungrouped-label="t('page.projectAnalysis.allJoinedRows')"
          />
        </template>
      </details>
    </template>
  </section>
</template>

<script setup lang="ts">
import type { ProjectAnalysisComparison, ProjectAnalysisRun } from "@/service/api/project-analysis"
import { compareProjectAnalyses } from "@/service/api/project-analysis"
import { useI18n } from "vue-i18n"
import AnalysisResultTable from "./analysis-result-table.vue"
import ProjectJoinAudit from "./project-join-audit.vue"

const props = defineProps<{ run: ProjectAnalysisRun, candidates: ProjectAnalysisRun[] }>()
const { t, locale } = useI18n()
const baselineId = ref<string | null>(null)
const comparison = ref<ProjectAnalysisComparison | null>(null)
const loading = ref(false)
const error = ref("")
let sequence = 0
const options = computed(() =>
  props.candidates
    .filter(item => item.id !== props.run.id && item.status === "succeeded")
    .map(item => ({
      value: item.id,
      label: `${item.question || t("page.analysis.report")} · ${new Date(item.created_at).toLocaleString(locale.value)}`,
    })),
)
const label = (id: string) => props.run.recipe.slots.find(slot => slot.slot_id === id)?.label || id
async function compare() {
  if (!baselineId.value)
    return
  const current = ++sequence
  comparison.value = null
  loading.value = true
  error.value = ""
  try {
    const result = await compareProjectAnalyses(props.run.id, baselineId.value)
    if (current === sequence)
      comparison.value = result
  }
  catch (cause) {
    const detail = (cause as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
    if (current === sequence)
      error.value = typeof detail === "string" ? detail : t("page.analysis.requestError")
  }
  finally {
    if (current === sequence)
      loading.value = false
  }
}
watch(
  () => props.run.id,
  () => {
    sequence += 1
    comparison.value = null
    baselineId.value = props.run.rerun_of_id
    error.value = ""
  },
)
onBeforeUnmount(() => {
  sequence += 1
})
</script>

<style scoped>
.comparison {
  min-width: 0;
  border-top: 1px solid #e5e7eb;
  padding-top: 12px;
}
.comparison-source {
  border: 1px solid #e5e7eb;
  padding: 12px;
  border-radius: 8px;
  overflow-wrap: anywhere;
}
</style>
