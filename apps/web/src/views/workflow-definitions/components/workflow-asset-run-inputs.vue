<template>
  <section v-if="graph.asset_inputs?.length" class="mb-4" data-testid="workflow-asset-run-inputs">
    <h3 class="aira-type-section-title">
      {{ $t('page.workflowAssets.selectVersions') }}
    </h3>
    <n-alert type="info" class="mb-3">
      {{ $t('page.workflowAssets.runHint') }}
    </n-alert>
    <n-alert v-if="error" type="error" class="mb-3" role="alert">
      {{ $t('page.workflowAssets.loadFailed') }} {{ error }}
    </n-alert>
    <n-empty v-if="!versions.length && !loading && !error && !hasMore" :description="$t('page.workflowAssets.noVersions')" size="small" />
    <article v-for="input in graph.asset_inputs" :key="input.input_id" class="asset-run-slot my-3" data-testid="workflow-asset-run-slot">
      <n-form-item :label="input.label" label-placement="top" required>
        <n-select :value="model[input.input_id] ?? null" :disabled="disabled" :options="options(input.input_id)" filterable clearable :placeholder="$t('page.workflowAssets.chooseVersion')" data-testid="workflow-asset-version" @update:value="value => select(input.input_id, value)" />
      </n-form-item>
      <div v-if="selected(input.input_id)" class="aira-type-meta">
        <strong>{{ selected(input.input_id)?.filename }}</strong>
        <p class="my-1">
          {{ selected(input.input_id)?.media_type }} · {{ selected(input.input_id)?.byte_size }} B
        </p>
        <p class="my-1">
          {{ $t('page.workflowAssets.versionId') }}: {{ selected(input.input_id)?.version_id }}
        </p>
        <p class="my-1">
          SHA-256 · {{ selected(input.input_id)?.sha256 }}
        </p>
        <details class="mt-2">
          <summary>{{ $t('page.workflowAssets.availableFields') }}</summary>
          <ul class="pl-5">
            <li v-for="field in selected(input.input_id)?.fields ?? []" :key="workflowPathKey(field.path)">
              {{ workflowPathLabel(field.path) }} · {{ $t(`page.workflowDefinitions.fieldTypes.${field.value_type}`) }}<span v-if="field.unit"> · {{ field.unit }}</span>
              <span v-if="field.value_type === 'file'"> · {{ field.file_extensions?.join(', ') || '*' }}</span>
            </li>
          </ul>
        </details>
      </div>
    </article>
    <n-button v-if="hasMore" :loading="loading" :disabled="disabled || loading" data-testid="workflow-asset-load-more" @click="emit('loadMore')">
      {{ error ? $t('page.workflowAssets.retryVersions') : $t('page.workflowAssets.loadMoreVersions') }}
    </n-button>
  </section>
</template>

<script setup lang="ts">
import type { WorkflowAssetVersion, WorkflowContext, WorkflowGraph } from "@/service/api/workflow-definitions"
import { workflowAssetVersionCompatible, workflowPathKey, workflowPathLabel } from "@/utils/workflow-editor"
import { useI18n } from "vue-i18n"

const props = defineProps<{ graph: WorkflowGraph, protocols: WorkflowContext["protocols"], versions: WorkflowAssetVersion[], disabled: boolean, loading: boolean, error: string, hasMore: boolean }>()
const emit = defineEmits<{ loadMore: [] }>()
const model = defineModel<Record<string, string>>({ required: true })
const { t } = useI18n()
function selected(inputId: string) {
  return props.versions.find(version => version.version_id === model.value[inputId])
}
function options(inputId: string) {
  const bindings = (props.graph.asset_bindings ?? []).filter(binding => binding.input_id === inputId)
  return props.versions.map(version => ({ value: version.version_id, label: `${version.name} · v${version.version}`, disabled: !workflowAssetVersionCompatible(version, bindings, props.protocols, props.graph) }))
}
function select(inputId: string, value: string | null) {
  const next = { ...model.value }
  if (value)
    next[inputId] = value
  else
    delete next[inputId]
  model.value = next
}
</script>

<style scoped>
.asset-run-slot { min-width: 0; padding: 12px; border: 1px solid #cbd5e1; border-radius: 8px; overflow-wrap: anywhere; }
</style>
