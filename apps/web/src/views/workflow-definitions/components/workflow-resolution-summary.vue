<template>
  <n-alert v-if="restricted" type="warning" class="mt-3" data-testid="workflow-resolution-restricted">
    {{ $t("page.workflowDefinitions.resolution.restrictedHint") }}
  </n-alert>
  <section v-else-if="resolution" class="workflow-resolution" data-testid="workflow-resolution-summary" :data-resolution-state="resolution.state">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h4 class="aira-type-label m-0">
        {{ $t("page.workflowDefinitions.resolution.title") }}
      </h4>
      <n-tag :type="resolution.state === 'failed' || resolution.state === 'blocked' ? 'warning' : 'info'" size="small">
        {{ stateLabel }}
      </n-tag>
    </div>
    <p v-if="pendingApproval" class="aira-type-meta mt-2">
      {{ $t("page.workflowDefinitions.resolution.approvalHint") }}
    </p>
    <div v-for="(source, nodeId) in resolution.receipt.sources" :key="nodeId" class="workflow-resolution-source mt-3">
      <strong>{{ sourceTitles?.[nodeId] || nodeId }}</strong>
      <div v-if="source.kind === 'analysis'" class="aira-type-meta mt-1">
        {{ $t('page.workflowAnalysis.analysisResult') }}: {{ source.analysis_id }}
        <div>{{ $t('page.workflowAnalysis.resultDigest') }}: {{ source.result_digest }}</div>
      </div>
      <div v-else class="aira-type-meta mt-1">
        {{ $t("page.workflowDefinitions.resolution.record") }}: {{ source.record_id }} · {{ $t("page.workflowDefinitions.revision", { number: source.record_version }) }}
      </div>
      <div v-if="source.kind !== 'analysis'" class="aira-type-meta aira-text-secondary">
        Protocol · {{ source.protocol_version }}
      </div>
      <div v-for="edge in sourceConditions(nodeId)" :key="edge.edge_id" class="aira-type-meta mt-2">
        {{ workflowConditionText(edge.condition!) }}
      </div>
      <ul v-if="sourceBindings(nodeId).length" class="mb-0 mt-2 pl-5">
        <li v-for="binding in sourceBindings(nodeId)" :key="binding.binding_id">
          {{ workflowPathLabel(binding.source_path) }} → {{ workflowPathLabel(binding.target_path) }}
          <span v-if="binding.unit"> · {{ binding.unit }}</span>
          <div v-if="fileReceipt(binding.binding_id)" class="workflow-resolved-file mt-2" data-testid="workflow-resolved-file">
            <strong>{{ $t('page.workflowFiles.receipt') }}</strong>
            <p class="aira-type-meta my-1">
              {{ fileReceipt(binding.binding_id)?.filename }} · {{ fileReceipt(binding.binding_id)?.content_type }} · {{ fileReceipt(binding.binding_id)?.size_bytes }} B
            </p>
            <p class="aira-type-meta my-1">
              SHA-256 · {{ fileReceipt(binding.binding_id)?.sha256 }}
            </p>
            <p class="aira-type-meta my-1">
              {{ $t('page.workflowFiles.destinationHint') }}
            </p>
          </div>
        </li>
      </ul>
    </div>
    <div v-for="(source, inputId) in resolution.receipt.asset_sources ?? {}" :key="inputId" class="workflow-resolution-source mt-3" data-testid="workflow-resolved-asset">
      <strong>{{ $t('page.workflowAssets.sourceInput') }} · {{ inputId }}</strong>
      <p class="aira-type-meta my-1">
        {{ $t('page.workflowAssets.assetId') }}: {{ source.data_asset_id }} · v{{ source.version }}
      </p>
      <p class="aira-type-meta my-1">
        {{ $t('page.workflowAssets.versionId') }}: {{ source.data_asset_version_id }}
      </p>
      <ul class="mb-0 mt-2 pl-5">
        <li v-for="binding in assetBindings(inputId)" :key="binding.binding_id" class="my-2">
          {{ workflowPathLabel(binding.source_path) }} → {{ workflowPathLabel(binding.target_path) }}<span v-if="binding.unit"> · {{ binding.unit }}</span>
          <p v-if="binding.value_type !== 'file' && Object.hasOwn(binding, 'value')" class="aira-type-meta my-1">
            {{ $t('page.workflowAssets.resolvedValue') }}: {{ JSON.stringify(binding.value) }}
          </p>
          <div v-if="fileReceipt(binding.binding_id)" class="workflow-resolved-file mt-2" data-testid="workflow-resolved-file">
            <strong>{{ $t('page.workflowFiles.receipt') }}</strong>
            <p class="aira-type-meta my-1">
              {{ fileReceipt(binding.binding_id)?.filename }} · {{ fileReceipt(binding.binding_id)?.content_type }} · {{ fileReceipt(binding.binding_id)?.size_bytes }} B
            </p>
            <p class="aira-type-meta my-1">
              SHA-256 · {{ fileReceipt(binding.binding_id)?.sha256 }}
            </p>
            <p class="aira-type-meta my-1">
              {{ $t('page.workflowFiles.destinationHint') }}
            </p>
          </div>
        </li>
      </ul>
      <details class="aira-type-meta mt-2">
        <summary>{{ $t('page.workflowAssets.sourceDetails') }}</summary>
        <p>{{ $t('page.workflowAssets.sourceDigest') }}: {{ source.source_digest }}</p>
      </details>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { WorkflowAssetBinding, WorkflowControlEdge, WorkflowScalarBinding } from "@/service/api/workflow-definitions"
import { workflowConditionText, workflowPathLabel } from "@/utils/workflow-editor"
import { computed } from "vue"
import { useI18n } from "vue-i18n"

interface Resolution {
  state: string
  receipt: {
    sources: Record<string, { kind?: "record", record_id: string, record_version: number, protocol_version: string } | { kind: "analysis", analysis_id: string, result_digest: string, source_digest: string }>
    bindings: WorkflowScalarBinding[]
    edges: WorkflowControlEdge[]
    files?: Array<{ binding_id: string, file_id: string, digest: string, filename: string, content_type: string, size_bytes: number, sha256: string }>
    asset_sources?: Record<string, { kind: "data_asset", asset_input_id: string, input_id: string, data_asset_id: string, data_asset_version_id: string, version: number, research_file_id: string, source_digest: string }>
    asset_bindings?: Array<WorkflowAssetBinding & { value?: string | number | boolean | null, value_digest?: string }>
  }
}
const props = defineProps<{ inputData: Record<string, unknown>, restricted?: boolean, pendingApproval?: boolean, sourceTitles?: Record<string, string> }>()
const { t } = useI18n()
const resolution = computed(() => {
  const value = props.inputData.workflow_resolution as Resolution | undefined
  return value && typeof value.state === "string" && value.receipt && typeof value.receipt.sources === "object" && Array.isArray(value.receipt.bindings) ? value : null
})
const stateLabel = computed(() => {
  if (resolution.value?.state === "branch_not_selected")
    return t("page.workflowDefinitions.conditions.branchNotSelected")
  const key = `page.workflowDefinitions.resolution.states.${resolution.value?.state}`
  const text = t(key)
  return text === key ? resolution.value?.state : text
})
function sourceBindings(nodeId: string) {
  return resolution.value?.receipt.bindings.filter(binding => binding.source_node_id === nodeId) ?? []
}
function assetBindings(inputId: string) {
  return resolution.value?.receipt.asset_bindings?.filter(binding => binding.input_id === inputId) ?? []
}
function fileReceipt(bindingId: string) {
  return resolution.value?.receipt.files?.find(file => file.binding_id === bindingId)
}
function sourceConditions(nodeId: string) {
  return resolution.value?.receipt.edges?.filter(edge => edge.source_node_id === nodeId && edge.condition) ?? []
}
</script>

<style scoped>
.workflow-resolution { margin-top: 14px; padding: 12px; border: 1px solid #cbd5e1; border-radius: 8px; background: #f8fafc; overflow-wrap: anywhere; }
.workflow-resolution-source { padding-top: 10px; border-top: 1px solid #e2e8f0; }
</style>
