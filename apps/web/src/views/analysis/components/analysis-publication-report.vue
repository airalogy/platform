<template>
  <section class="publication-report" data-testid="analysis-publication-report">
    <h3 class="aira-type-section-title">
      {{ snapshot.title }}
    </h3>
    <p v-if="snapshot.summary" class="whitespace-pre-wrap">
      {{ snapshot.summary }}
    </p>
    <n-alert type="info" class="my-3">
      {{ t('page.analysisPublication.reviewHint') }}
    </n-alert>
    <n-alert v-if="snapshot.analysis.source_scope === 'project'" type="info" class="my-3">
      {{ t(snapshot.join_audit ? 'page.projectAnalysis.associationOnly' : 'page.projectAnalysis.separateEvidence') }}
    </n-alert>
    <article v-for="section in snapshot.sections" :key="section.section_id" class="my-4 min-w-0">
      <h4 class="aira-type-label">
        {{ section.label }}
      </h4>
      <p>{{ t('page.analysis.countSummary', { ...section.report.counts }) }}</p>
      <n-alert v-for="(warning, index) in section.report.warnings" :key="index" type="warning" class="mb-2">
        {{ t(`page.analysis.warnings.${warning.code}`, { field: warning.field || '', count: warning.count }) }}
      </n-alert>
      <analysis-result-table :result="section.report" />
    </article>
    <project-join-audit v-if="snapshot.join_audit" :audit="snapshot.join_audit" :labels="sourceLabels" />
    <section v-if="snapshot.interpretation" class="my-4" data-testid="analysis-publication-interpretation">
      <h4 class="aira-type-label">
        {{ t('page.analysisPublication.humanInterpretation') }} · r{{ snapshot.interpretation.revision }}
      </h4>
      <p>{{ t(`page.projectAnalysis.relations.${snapshot.interpretation.content.judgement}`) }}</p>
      <p class="whitespace-pre-wrap">
        {{ snapshot.interpretation.content.summary }}
      </p>
      <ul>
        <li v-for="(finding, index) in snapshot.interpretation.content.findings" :key="index">
          {{ sourceLabels[finding.slot_id] || finding.slot_id }} · {{ finding.field }} ·
          {{ t(`page.projectAnalysis.relations.${finding.relation}`) }}: {{ finding.note }}
        </li>
      </ul>
      <h5 class="aira-type-label">
        {{ t('page.projectAnalysis.interpretation.limitations') }}
      </h5>
      <ul>
        <li v-for="(limitation, index) in snapshot.interpretation.content.limitations" :key="index">
          {{ limitation }}
        </li>
      </ul>
      <h5 class="aira-type-label">
        {{ t('page.projectAnalysis.interpretation.questions') }}
      </h5>
      <ul>
        <li v-for="(question, index) in snapshot.interpretation.content.unanswered_questions" :key="index">
          {{ question }}
        </li>
      </ul>
    </section>
    <details class="aira-disclosure mt-4" data-testid="analysis-publication-sources">
      <summary>{{ t('page.analysis.provenance') }}</summary>
      <dl class="aira-type-meta">
        <dt>{{ t('page.analysis.engine') }}</dt><dd>{{ snapshot.analysis.engine_version }}</dd>
        <dt>{{ t('page.analysis.sourceDigest') }}</dt><dd>{{ snapshot.analysis.source_digest }}</dd>
        <dt>{{ t('page.analysis.recipeDigest') }}</dt><dd>{{ snapshot.analysis.recipe_digest }}</dd>
        <dt>{{ t('page.analysis.resultDigest') }}</dt><dd>{{ snapshot.analysis.result_digest }}</dd>
      </dl>
      <article v-for="source in snapshot.sources" :key="source.slot_id">
        <h5 class="aira-type-label">
          {{ sourceLabels[source.slot_id] || source.slot_id }}
        </h5>
        <p class="aira-type-meta">
          Protocol · {{ source.protocol_id }}
        </p>
        <p v-for="record in source.records" :key="`${record.record_id}:${record.record_version}`" class="aira-type-meta">
          Record · {{ record.record_id }} · v{{ record.record_version }} · Protocol {{ record.protocol_version }}<br>
          SHA-1 · {{ record.record_hash }}
        </p>
        <p v-for="schema in source.schemas" :key="schema.id" class="aira-type-meta">
          Schema · {{ schema.version }} · SHA-256 · {{ schema.schema_digest }}
        </p>
      </article>
    </details>
  </section>
</template>

<script setup lang="ts">
import type { AnalysisPublicationSnapshot } from "@/service/api/analysis-publications"
import { useI18n } from "vue-i18n"
import AnalysisResultTable from "./analysis-result-table.vue"
import ProjectJoinAudit from "./project-join-audit.vue"

const props = defineProps<{ snapshot: AnalysisPublicationSnapshot }>()
const { t } = useI18n()
const sourceLabels = computed(() => Object.fromEntries(props.snapshot.sections.map(section => [section.section_id.replace(/^source:/, ""), section.label])))
</script>

<style scoped>
.publication-report { min-width: 0; overflow-wrap: anywhere; }
dl { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 2fr); gap: 8px; }
dd { margin: 0; }
ul { padding-left: 1.25rem; }
@media (max-width: 600px) { dl { grid-template-columns: minmax(0, 1fr); } }
</style>
