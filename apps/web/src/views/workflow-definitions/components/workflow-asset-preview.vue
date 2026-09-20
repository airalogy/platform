<template>
  <section v-if="inputs.length" class="my-4" data-testid="workflow-asset-preview">
    <h3 class="aira-type-section-title">
      {{ $t('page.workflowAssets.confirmedInputs') }}
    </h3>
    <n-alert type="warning" class="mb-3">
      {{ $t('page.workflowAssets.previewHint') }}
    </n-alert>
    <article v-for="input in inputs" :key="input.input_id" class="asset-preview-card my-3" data-testid="workflow-asset-preview-item">
      <h4 class="aira-type-label m-0">
        {{ input.label }} · {{ input.name }} v{{ input.version }}
      </h4>
      <p class="aira-type-meta my-2">
        {{ input.filename }} · {{ input.media_type }} · {{ input.byte_size }} B
      </p>
      <p class="aira-type-meta my-1">
        {{ $t('page.workflowAssets.versionId') }}: {{ input.data_asset_version_id }}
      </p>
      <p class="aira-type-meta my-1">
        SHA-256 · {{ input.sha256 }}
      </p>
      <ul class="pl-5">
        <li v-for="binding in input.bindings" :key="binding.binding_id" class="my-2">
          {{ workflowPathLabel(binding.source_path) }} → <strong>{{ nodes.find(node => node.node_id === binding.target_node_id)?.title || binding.target_node_id }}</strong> · {{ workflowPathLabel(binding.target_path) }}
          <p class="aira-type-meta my-1">
            {{ $t(`page.workflowDefinitions.fieldTypes.${binding.value_type}`) }}<span v-if="binding.unit"> · {{ binding.unit }}</span>
          </p>
          <p v-if="binding.value_type !== 'file' && Object.hasOwn(binding, 'value')" class="aira-type-meta my-1">
            {{ $t('page.workflowAssets.resolvedValue') }}: {{ JSON.stringify(binding.value) }}
          </p>
          <p v-if="binding.value_type === 'file'" class="aira-type-meta my-1">
            {{ $t('page.workflowFiles.destinationHint') }}
          </p>
        </li>
      </ul>
      <details class="aira-type-meta">
        <summary>{{ $t('page.workflowAssets.sourceDetails') }}</summary>
        <p>{{ $t('page.workflowAssets.assetId') }}: {{ input.data_asset_id }}</p>
        <p>{{ $t('page.workflowAssets.sourceDigest') }}: {{ input.source_digest }}</p>
      </details>
    </article>
  </section>
</template>

<script setup lang="ts">
import type { WorkflowAssetInputPreview, WorkflowNode } from "@/service/api/workflow-definitions"
import { workflowPathLabel } from "@/utils/workflow-editor"

defineProps<{ inputs: WorkflowAssetInputPreview[], nodes: WorkflowNode[] }>()
</script>

<style scoped>
.asset-preview-card { min-width: 0; padding: 12px; border: 1px solid #cbd5e1; border-radius: 8px; overflow-wrap: anywhere; }
</style>
