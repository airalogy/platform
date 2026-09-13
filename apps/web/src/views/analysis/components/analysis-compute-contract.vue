<template>
  <section class="compute-contract" data-testid="analysis-compute-contract">
    <n-alert v-if="mode !== 'historical'" type="warning" class="mb-4" data-testid="analysis-compute-contract-review-warning">
      {{ t(mode === 'approval' ? "page.analysis.compute.approvalReviewHint" : "page.analysis.compute.reviewHint") }}
    </n-alert>
    <dl class="compute-contract-grid aira-type-meta">
      <dt>{{ t("page.analysis.compute.environment") }}</dt><dd>{{ contract.environment.name }} · r{{ contract.environment.metadata.environment_revision }}</dd>
      <dt>{{ t("page.analysis.compute.image") }}</dt><dd>{{ contract.environment.metadata.image_ref }}</dd>
      <dt>{{ t("page.analysis.compute.sourceDigest") }}</dt><dd>{{ contract.source.sha256 }} · {{ contract.source.bytes }} B · {{ contract.source.language }}</dd>
      <dt>{{ t("page.analysis.compute.input") }}</dt><dd>{{ contract.input.filename }} · {{ contract.input.record_count }} Records · {{ contract.input.bytes }} B<br>{{ contract.input.sha256 }}</dd>
      <dt>{{ t("page.analysis.compute.approver") }}</dt><dd>{{ contract.approver.name }}</dd>
      <dt>{{ t("page.analysis.compute.estimatedCost") }}</dt><dd>{{ contract.cost.estimated_cost === null ? t("page.analysis.compute.unpriced") : `${contract.cost.estimated_cost} ${contract.cost.currency || ''}` }}</dd>
      <dt>{{ t("page.analysis.compute.maxCost") }}</dt><dd>{{ contract.cost.max_cost === null ? t("page.analysis.compute.notSet") : `${contract.cost.max_cost} ${contract.cost.budget_currency || ''}` }}</dd>
      <dt>{{ t("page.analysis.compute.deadline") }}</dt><dd>{{ contract.deadline_at ? new Date(contract.deadline_at).toLocaleString(locale) : t("page.analysis.compute.notSet") }}</dd>
      <dt>{{ t(mode === 'historical' || mode === 'approval' ? "page.analysis.compute.historicalRunners" : "page.analysis.compute.runners") }}</dt><dd>{{ t("page.analysis.compute.runnerCounts", { authorized: contract.authorized_runner_count, ready: contract.ready_runner_count }) }}</dd>
      <dt>{{ t("page.analysis.compute.network") }}</dt><dd>{{ contract.environment.metadata.network_policy }}<br>{{ contract.environment.metadata.allowed_egress_hosts?.join(", ") }}</dd>
    </dl>
    <analysis-compute-input-receipt v-if="contract.input_files" :envelope="contract.input_files" />
    <n-alert v-if="mode !== 'historical' && mode !== 'approval' && !contract.ready_runner_count" type="warning" class="mb-3" data-testid="analysis-compute-contract-offline-warning">
      {{ t("page.analysis.compute.noReadyRunner") }}
    </n-alert>
    <h4 class="aira-type-label">
      {{ t("page.analysis.compute.resources") }}
    </h4>
    <pre tabindex="0">{{ JSON.stringify(contract.environment.metadata.resource_limits, null, 2) }}</pre>
    <h4 class="aira-type-label">
      {{ t("page.analysis.compute.schemas") }}
    </h4>
    <pre tabindex="0" data-testid="analysis-compute-review-schemas">{{ JSON.stringify({ input: contract.environment.input_schema, result: contract.environment.output_schema }, null, 2) }}</pre>
    <h4 class="aira-type-label">
      {{ t("page.analysis.compute.source") }}
    </h4>
    <pre tabindex="0" data-testid="analysis-compute-review-code">{{ contract.source.code }}</pre>
    <h4 class="aira-type-label">
      {{ t("page.analysis.compute.parameters") }}
    </h4>
    <pre tabindex="0">{{ JSON.stringify(contract.parameters, null, 2) }}</pre>
    <h4 class="aira-type-label">
      {{ t("page.analysis.compute.outputs") }}
    </h4>
    <pre tabindex="0">{{ JSON.stringify(contract.output_files, null, 2) }}</pre>
  </section>
</template>

<script setup lang="ts">
import type { AnalysisComputeContract } from "@/service/api/analysis-compute"
import { useI18n } from "vue-i18n"
import AnalysisComputeInputReceipt from "./analysis-compute-input-receipt.vue"

defineProps<{ contract: AnalysisComputeContract, mode?: "review" | "approval" | "historical" }>()
const { t, locale } = useI18n()
</script>

<style scoped>
.compute-contract { min-width: 0; }
.compute-contract-grid { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: .5rem .8rem; }
.compute-contract-grid dd { margin: 0; overflow-wrap: anywhere; }
pre { max-width: 100%; max-height: 18rem; overflow: auto; padding: .8rem; background: #f7f9fc; border: 1px solid #e5e7eb; border-radius: .5rem; font-size: .75rem; }
pre:focus-visible { outline: 2px solid #0084e2; outline-offset: 2px; }
@media (max-width: 600px) { .compute-contract-grid { grid-template-columns: minmax(0, 1fr); } }
</style>
