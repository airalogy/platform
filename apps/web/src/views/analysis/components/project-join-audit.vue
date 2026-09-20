<template>
  <section data-testid="project-join-audit">
    <h4 class="aira-type-label">
      {{ t("page.projectAnalysis.joinAudit") }}
    </h4>
    <div class="audit-grid">
      <article v-for="side in [audit.left, audit.right]" :key="side.slot_id">
        <h5 class="aira-type-label my-2">
          {{ labels?.[side.slot_id] || side.slot_id }}
        </h5>
        <dl>
          <template v-for="key in keys" :key="key">
            <dt>{{ t(`page.projectAnalysis.audit.${key}`) }}</dt><dd>{{ side[key] }}</dd>
          </template>
        </dl>
      </article>
    </div>
    <p class="aira-type-body">
      {{ t("page.projectAnalysis.outputRows", { count: audit.output_rows }) }}
    </p>
  </section>
</template>

<script setup lang="ts">
import type { ProjectAnalysisJoinAudit } from "@/service/api/project-analysis"
import { useI18n } from "vue-i18n"

defineProps<{ audit: ProjectAnalysisJoinAudit, labels?: Record<string, string> }>()
const { t } = useI18n()
const keys = [
  "total",
  "filtered_out",
  "key_missing",
  "invalid_keys",
  "excluded",
  "duplicate_keys",
  "duplicate_rows",
  "matched",
  "unmatched",
] as const
</script>

<style scoped>
.audit-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
article {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px;
}
dl {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 6px;
  margin: 0;
}
dd {
  margin: 0;
  font-variant-numeric: tabular-nums;
}
@media (max-width: 600px) {
  .audit-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
