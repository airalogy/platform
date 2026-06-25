<template>
  <define-research-variable-info v-slot="{ title, description }">
    <div>{{ title }}</div>
    <div v-if="description">
      {{ $t("common.description") }}: {{ description }}
    </div>
  </define-research-variable-info>
  <n-modal
    v-model:show="isInitialValuesShown"
    class="max-w-70vw min-w-2xl"
    :class="selectedResearchNode?.type === 'generated' ? 'ai-generated__modal' : ''"
    preset="card"
  >
    <template #header>
      <div class="relative flex items-center gap-2">
        <span class="ai-generated__header">{{ selectedResearchNode?.name || $t("page.protocol.workflow.researchProtocol") }}</span>
        <n-tag type="info" size="small" round class="box__badge">
          {{ $t("page.protocol.workflow.aiGenerated") }}
        </n-tag>
      </div>
    </template>
    <n-space vertical>
      <n-skeleton v-if="props.loading" text :repeat="6" />
      <n-descriptions
        v-else-if="selectedResearchNode?.field"
        :column="1"
        bordered
        label-placement="left"
        :theme-overrides="{ borderRadius: '12px' }"
        class="max-h-70vh overflow-auto text-lg"
      >
        <n-descriptions-item
          v-for="(prop, key) in selectedResearchNode.field.var"
          :key="key"
        >
          <template #label>
            <n-tooltip trigger="hover">
              <!-- <research-variable-info v-bind="getResearchVariable(key)" /> -->
              <template #trigger>
                {{ key }}
              </template>
            </n-tooltip>
          </template>
          <!-- <asset-item v-if="prop.airalogy_file_id" v-bind="assetRecord[prop.airalogy_file_id]" /> -->
          <div class="w-fit whitespace-pre-wrap">
            {{ prop }}
          </div>
        </n-descriptions-item>
      </n-descriptions>
      <n-flex class="mt-3">
        <n-button
          type="warning"
          :loading="props.loading || selectedResearchNode?.status === 'generating'"
          @click="handleRegenerateInitialValue"
        >
          {{ $t("common.regenerate") }}
        </n-button>
        <n-button
          class="ml-auto mr-2"
          :disabled="props.loading"
          :type="showAcceptButton ? 'default' : 'primary'"
          @click="hideChainResearchNode"
        >
          {{ showAcceptButton ? $t("common.cancel") : $t("common.close") }}
        </n-button>
        <n-button
          v-if="showAcceptButton"
          type="primary"
          class="min-w-15"
          :disabled="props.loading"
          @click="handleAcceptInitialValues"
        >
          {{ $t("common.accept") }}
        </n-button>
      </n-flex>
    </n-space>
  </n-modal>
</template>

<script setup lang="ts">
import type { SelectedNode } from "@/store/modules/workflow"
import type { WorkflowProtocolInfo } from "@/types/workflow"

interface IProps {
  show: boolean
  selectedNode: SelectedNode | null
  nodesInfo?: WorkflowProtocolInfo[] | null
  loading: boolean
}

const props = withDefaults(defineProps<IProps>(), {})

const emit = defineEmits<IEmits>()
// const targetResearchNode = computed(() =>
//   props.nodesInfo?.find(node => node.airalogy_protocol_id === props.selectedNode?.airalogy_protocol_id),
// )

const [DefineResearchVariableInfo, ResearchVariableInfo] = createReusableTemplate<{
  title: string
  description: string
}>()
// function getResearchVariable(key: string) {
//   const defaultInfo = { title: key, description: "" }
//   if (!targetResearchNode.value)
//     return defaultInfo

//   const { properties } = targetResearchNode.value.field_json_schema.research_variable || {}
//   if (properties) {
//     return properties[key] || defaultInfo
//   }

//   return defaultInfo
// }
interface IEmits {
  (e: "update:show", value: boolean): void
  (e: "update:selected-node", value: SelectedNode): void
  (e: "action:regenerate-initial-values", payload: any): void
  (e: "action:accept-initial-values", payload: any): void
}

const isInitialValuesShown = useVModel(props, "show", emit, { defaultValue: false })
const selectedResearchNode = useVModel(props, "selectedNode", emit)
const showAcceptButton = computed(
  () =>
    selectedResearchNode.value?.status === "init"
    || selectedResearchNode.value?.status === "generating"
    || selectedResearchNode.value?.status === "generated",
)

function handleRegenerateInitialValue() {
  emit("action:regenerate-initial-values", selectedResearchNode.value)
}

function hideChainResearchNode() {
  isInitialValuesShown.value = false
}

function handleAcceptInitialValues() {
  emit("action:accept-initial-values", selectedResearchNode.value)
}
</script>

<style lang="sass">
.ai-generated__modal
  --ai-linear: linear-gradient(130deg, rgba(26, 121, 255, 0.8) 0%, rgba(122, 75, 255, 0.8) 100%)

  .ai-generated__header
    font-weight: 600
    font-size: 16px
    color: rgba(0,0,0,0.2)
    background: var(--ai-linear)
    background-clip: text
    -webkit-background-clip: text

  .box__badge
    background: var(--ai-linear) !important
    color: white
    &--small
      font-size: 10px
      line-height: 1.5
</style>
