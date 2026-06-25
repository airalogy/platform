<template>
  <div class="flex flex-col">
    <template v-if="flowNodes.length > 0">
      <div v-for="(node, index) in flowNodes" :key="node.id" class="flex items-center">
        <workflow-node
          :node="node" :index="index" :is-last="index === flowNodes.length - 1"
          @generate-initial-values="emit('action:generate-initial-values', node)"
          @show-report="emit('action:show-report', node)" @add-record="emit('action:add-record', node)"
          @redo-record="emit('action:redo-record', node)"
          @set-intermediate-conclusion="emit('action:set-intermediate-conclusion', node)"
          @show-intermediate-conclusion="emit('action:show-intermediate-conclusion', node)"
          @show-initial-values="emit('action:show-initial-values', node)"
          @end-workflow="emit('action:end-workflow', node)" @delete="emit('action:delete', node)"
        />

        <node-connector v-if="index < flowNodes.length - 1" />
      </div>

      <!-- Workflow End State -->
      <template v-if="isWorkflowEnded">
        <n-tag type="success" class="ml-3" size="large">
          <template #icon>
            <n-icon><icon-ion-checkmark-circle /></n-icon>
          </template>
          {{ $t("page.protocol.workflow.ended") }}
        </n-tag>
      </template>
      <template v-else>
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-button quaternary :disabled="!canAddNewNode" class="ml-4" @click="$emit('select:next-research-node')">
              <template #icon>
                <n-icon size="28" color="#A1A4AF">
                  <icon-ion-add />
                </n-icon>
              </template>
            </n-button>
          </template>
          <span v-if="canAddNewNode">{{ $t("page.protocol.workflow.selectNext") }}</span>
          <span v-else>{{ $t("page.protocol.workflow.completePrevious") }}</span>
        </n-tooltip>
      </template>
    </template>
    <n-button v-else type="primary" @click="emit('select:next-research-node')">
      <template #icon>
        <n-icon>
          <icon-ion-add />
        </n-icon>
      </template>
      {{ $t("page.protocol.workflow.selectUnit") }}
    </n-button>
  </div>
</template>

<script lang="ts" setup>
import type { FlowNode } from "@/store/modules/workflow"
import { $t } from "@airalogy/shared/locales"
import IconIonAdd from "~icons/ion/add"
import IconIonCheckmarkCircle from "~icons/ion/checkmark-circle"
import { computed } from "vue"
import NodeConnector from "./linear-node-connector.vue"
import WorkflowNode from "./workflow-node.vue"

const props = defineProps<{
  flowNodes: FlowNode[]
}>()

const emit = defineEmits<IEmits>()
interface IEmits {
  (e: "select:next-research-node"): void
  (e: "action:generate-initial-values", node: FlowNode): void
  (e: "action:show-report", node: FlowNode): void
  (e: "action:add-record", node: FlowNode): void
  (e: "action:redo-record", node: FlowNode): void
  (e: "action:set-intermediate-conclusion", node: FlowNode): void
  (e: "action:show-intermediate-conclusion", node: FlowNode): void
  (e: "action:show-initial-values", node: FlowNode): void
  (e: "action:end-workflow", node: FlowNode): void
  (e: "action:delete", node: FlowNode): void
}
const isWorkflowEnded = computed(() => {
  return props.flowNodes.length > 0
    && props.flowNodes[props.flowNodes.length - 1].status === "done"
})

const canAddNewNode = computed(() => {
  return props.flowNodes.every(node => node.status === "done")
})
</script>
