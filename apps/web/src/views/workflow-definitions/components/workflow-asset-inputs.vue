<template>
  <section class="workflow-assets my-4" data-testid="workflow-asset-inputs">
    <h3 class="aira-type-section-title mt-0">
      {{ $t('page.workflowAssets.title') }}
    </h3>
    <p class="aira-type-meta aira-text-secondary">
      {{ $t('page.workflowAssets.definitionHint') }}
    </p>
    <article v-for="input in graph.asset_inputs ?? []" :key="input.input_id" class="asset-slot mb-3" data-testid="workflow-asset-slot">
      <n-form-item :label="$t('page.workflowAssets.label')" label-placement="top" required class="min-w-0 flex-1">
        <n-input v-model:value="input.label" :disabled="disabled" :maxlength="255" data-testid="workflow-asset-label" />
        <template #feedback>
          <span>{{ input.input_id }} · {{ $t('page.workflowAssets.bindingCount', { count: graph.asset_bindings?.filter(binding => binding.input_id === input.input_id).length ?? 0 }) }}</span>
        </template>
      </n-form-item>
      <n-button size="small" :disabled="disabled" @click="graph = removeWorkflowAssetInput(graph, input.input_id)">
        {{ $t('common.delete') }}
      </n-button>
    </article>
    <p v-if="graph.asset_inputs?.length" class="aira-type-meta aira-text-secondary">
      {{ $t('page.workflowAssets.removeHint') }}
    </p>
    <n-button :disabled="disabled || (graph.asset_inputs?.length ?? 0) >= 32" data-testid="workflow-add-asset-input" @click="add">
      {{ $t('page.workflowAssets.add') }}
    </n-button>
  </section>
</template>

<script setup lang="ts">
import type { WorkflowGraph } from "@/service/api/workflow-definitions"
import { addWorkflowAssetInput, removeWorkflowAssetInput } from "@/utils/workflow-editor"
import { useI18n } from "vue-i18n"

defineProps<{ disabled: boolean }>()
const graph = defineModel<WorkflowGraph>("graph", { required: true })
const { t } = useI18n()
function add() {
  graph.value = addWorkflowAssetInput(graph.value, t("page.workflowAssets.defaultLabel", { number: (graph.value.asset_inputs?.length ?? 0) + 1 }))
}
</script>

<style scoped>
.workflow-assets { min-width: 0; padding: 14px; border: 1px solid #dbe3ed; border-radius: 8px; background: #f8fafc; overflow-wrap: anywhere; }
.asset-slot { display: flex; flex-wrap: wrap; align-items: start; gap: 10px; }
</style>
