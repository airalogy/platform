<template>
  <section v-if="inputs?.length" class="input-declarations my-4" data-testid="analysis-compute-input-declarations">
    <h4 class="aira-type-label">
      {{ t('page.analysis.compute.inputFiles') }}
    </h4>
    <p class="aira-type-meta">
      {{ t(workflow ? 'page.analysis.compute.inputFilesWorkflowHint' : 'page.analysis.compute.inputFilesDeclarationHint') }}
    </p>
    <ul class="pl-5">
      <li v-for="input in inputs" :key="input.input_id" class="mb-2">
        <strong>{{ input.input_id }}</strong> ← {{ input.field_path.join(' · ') }}
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import type { AnalysisComputeInputFile } from "@/service/api/analysis-compute"
import { useI18n } from "vue-i18n"

defineProps<{ inputs?: AnalysisComputeInputFile[], workflow?: boolean }>()
const { t } = useI18n()
</script>

<style scoped>
.input-declarations { min-width: 0; overflow-wrap: anywhere; }
</style>
