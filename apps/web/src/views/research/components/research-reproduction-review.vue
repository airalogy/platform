<template>
  <section class="reproduction-review mb-4">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <div class="aira-type-label">
          {{ $t("page.research.reproductionAssessment") }}
        </div>
        <p class="aira-type-meta mb-0 mt-1">
          {{ $t("page.research.reproductionAssessmentHint", {
            source: context.source_run.run_number,
            replication: context.replication_run.run_number,
          }) }}
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <n-tag :type="context.lineage_intact ? 'success' : 'error'" size="small" round>
          {{ context.lineage_intact ? $t("page.research.lineageVerified") : $t("page.research.lineageInvalid") }}
        </n-tag>
        <n-tag :type="context.environment_equivalent ? 'success' : 'error'" size="small" round>
          {{ context.environment_equivalent ? $t("page.research.environmentMatched") : $t("page.research.environmentChanged") }}
        </n-tag>
      </div>
    </div>

    <n-alert v-if="!context.source_run.snapshot_sealed" type="warning" class="mt-3">
      {{ $t("page.research.legacyReplicationSource") }}
    </n-alert>

    <div class="grid grid-cols-1 mt-4 gap-4 md:grid-cols-2">
      <n-form-item :label="$t('page.research.reproductionOutcome')" required>
        <n-select
          :value="model.outcome"
          :options="outcomeOptions"
          @update:value="value => updateField('outcome', value)"
        />
      </n-form-item>
      <n-form-item :label="$t('page.research.reproductionSummary')" required>
        <n-input
          :value="model.summary"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          @update:value="value => updateField('summary', value)"
        />
      </n-form-item>
    </div>

    <div class="aira-type-eyebrow mt-2">
      {{ $t("page.research.criterionComparison") }}
    </div>
    <div class="mt-2 space-y-3">
      <article
        v-for="(item, index) in model.criteria_results"
        :key="item.criterion"
        class="reproduction-criterion"
      >
        <div class="aira-type-label break-words">
          {{ item.criterion }}
        </div>
        <div class="grid grid-cols-1 mt-3 gap-3 md:grid-cols-[14rem_minmax(0,1fr)]">
          <n-select
            :value="item.status"
            :options="criterionStatusOptions"
            @update:value="value => updateCriterion(index, 'status', value)"
          />
          <n-input
            :value="item.rationale"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            :placeholder="$t('page.research.criterionRationalePlaceholder')"
            @update:value="value => updateCriterion(index, 'rationale', value)"
          />
        </div>
      </article>
    </div>

    <div class="grid grid-cols-1 mt-4 gap-4 md:grid-cols-2">
      <n-form-item :label="$t('page.research.sourceEvidence')">
        <n-select
          :value="model.source_evidence_ids"
          :options="sourceEvidenceOptions"
          multiple
          filterable
          clearable
          :placeholder="$t('page.research.selectValidatedEvidence')"
          @update:value="value => updateField('source_evidence_ids', value)"
        />
      </n-form-item>
      <n-form-item :label="$t('page.research.replicationEvidence')">
        <n-select
          :value="model.replication_evidence_ids"
          :options="replicationEvidenceOptions"
          multiple
          filterable
          clearable
          :placeholder="$t('page.research.selectValidatedEvidence')"
          @update:value="value => updateField('replication_evidence_ids', value)"
        />
      </n-form-item>
      <n-form-item :label="$t('page.research.replicationDeviations')">
        <n-input
          :value="lines(model.deviations)"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          :placeholder="$t('page.research.oneItemPerLine')"
          @update:value="value => updateField('deviations', parseLines(value))"
        />
      </n-form-item>
      <n-form-item :label="$t('page.research.replicationLimitations')">
        <n-input
          :value="lines(model.limitations)"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          :placeholder="$t('page.research.oneItemPerLine')"
          @update:value="value => updateField('limitations', parseLines(value))"
        />
      </n-form-item>
    </div>
  </section>
</template>

<script setup lang="ts">
import type {
  ReproductionCriterionResult,
  ResearchReproductionAssessment,
  ResearchReproductionContext,
} from "@/service/api/research-tasks"
import { $t } from "@airalogy/shared/locales"

const props = defineProps<{
  context: ResearchReproductionContext
}>()

const model = defineModel<ResearchReproductionAssessment>({ required: true })

const outcomeOptions = computed(() => [
  { label: $t("page.research.reproductionOutcomes.reproduced"), value: "reproduced" },
  { label: $t("page.research.reproductionOutcomes.partially_reproduced"), value: "partially_reproduced" },
  { label: $t("page.research.reproductionOutcomes.not_reproduced"), value: "not_reproduced" },
  { label: $t("page.research.reproductionOutcomes.inconclusive"), value: "inconclusive" },
])

const criterionStatusOptions = computed(() => [
  { label: $t("page.research.reproductionCriterionStatus.reproduced"), value: "reproduced" },
  { label: $t("page.research.reproductionCriterionStatus.not_reproduced"), value: "not_reproduced" },
  { label: $t("page.research.reproductionCriterionStatus.inconclusive"), value: "inconclusive" },
])

const sourceEvidenceOptions = computed(() => evidenceOptions(props.context.source_evidence))
const replicationEvidenceOptions = computed(() => evidenceOptions(props.context.replication_evidence))

function evidenceOptions(items: ResearchReproductionContext["source_evidence"]) {
  return items.map(item => ({
    value: item.id,
    label: item.summary || `${item.kind} · ${item.artifact_type}`,
  }))
}

function updateField<K extends keyof ResearchReproductionAssessment>(
  field: K,
  value: ResearchReproductionAssessment[K],
) {
  model.value = { ...model.value, [field]: value }
}

function updateCriterion<K extends keyof ReproductionCriterionResult>(
  index: number,
  field: K,
  value: ReproductionCriterionResult[K],
) {
  const criteria = model.value.criteria_results.map((item, itemIndex) => (
    itemIndex === index ? { ...item, [field]: value } : item
  ))
  updateField("criteria_results", criteria)
}

function lines(items: string[]) {
  return items.join("\n")
}

function parseLines(value: string) {
  return value.split("\n").map(item => item.trim()).filter(Boolean)
}
</script>

<style scoped>
.reproduction-review {
  border: 1px solid rgb(219 234 254);
  border-radius: 14px;
  background: rgb(239 246 255 / 55%);
  padding: 16px;
}

.reproduction-criterion {
  border: 1px solid rgb(219 234 254);
  border-radius: 12px;
  background: rgb(255 255 255 / 88%);
  padding: 14px;
}
</style>
