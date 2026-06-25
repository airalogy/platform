<template>
  <n-card class="relative w-fit" size="small">
    <div class="flex items-center">
      <!-- Protocol Box -->
      <div
        class="flex-center flex-col p-2"
        :class="[
          node.type === 'generated' ? 'border rounded border-gradient' : '',
        ]"
      >
        <!-- AI Badge -->
        <n-tag v-if="node.type === 'generated'" size="tiny" class="absolute left-2 z-10 -top-2" type="info">
          AI
        </n-tag>

        <protocol-icon />
        <div class="mt-2 w-full text-center text-sm text-[#666]">
          {{ $t("page.protocol.workflow.protocolIndex", { index: index + 1 }) }}
        </div>
      </div>

      <!-- Connector with Cloud -->
      <div v-if="!isLast" class="flex items-center px-4">
        <n-icon size="24" class="text-[#A1A4AF]">
          <icon-ion-cloud />
        </n-icon>
        <div class="h-[2px] w-4 bg-[#A1A4AF]" />
        <n-icon size="20" color="#A1A4AF">
          <icon-ion-arrow-forward-outline />
        </n-icon>
      </div>

      <!-- Record/Waiting Box -->
      <div v-if="!isLast || node.status !== 'done'" class="min-w-[120px] flex flex-col">
        <div
          class="flex flex-col border rounded p-3" :class="[
            node.status === 'done' ? 'bg-[#f8f8f8] border-[#eee]' : 'bg-white border-[#eee]',
          ]"
        >
          <div class="text-sm text-[#666]">
            <template v-if="node.status === 'done'">
              {{ $t("page.protocol.workflow.recordIndex", { id: node.record_id }) }}
            </template>
            <template v-else-if="node.status === 'init' && node.type === 'manual'">
              {{ $t("page.protocol.workflow.waitingForRecord") }}
            </template>
            <template v-else-if="node.status === 'init' || (node.type === 'generated' && node.status === 'generated')">
              {{ $t("page.protocol.workflow.waitingForInitialValues") }}
            </template>
            <template v-else-if="node.status === 'pending'">
              {{ $t("page.protocol.workflow.waitingForRecord") }}
            </template>
            <template v-else-if="node.status === 'conclusion'">
              {{ $t("page.protocol.workflow.waitingForIntermediateConclusion") }}
            </template>
          </div>
        </div>
      </div>

      <!-- Action Buttons -->
      <div
        v-if="floatingActions.length > 0"
        class="absolute left-1/2 z-10 flex transform items-center -bottom-6 -translate-x-1/2 space-x-2"
      >
        <n-button
          v-for="action in floatingActions" :key="action.key" size="tiny" :type="action.type"
          @click="action.handler()"
        >
          {{ action.label }}
        </n-button>
      </div>

      <!-- Node Actions Dropdown -->
      <n-dropdown v-if="node.status === 'done'" :options="nodeActions" trigger="hover" @select="handleNodeAction">
        <n-button quaternary circle class="absolute right-2 top-2">
          <template #icon>
            <n-icon><icon-ion-ellipsis-vertical /></n-icon>
          </template>
        </n-button>
      </n-dropdown>
    </div>
  </n-card>
</template>

<script lang="ts" setup>
import type { FlowNode } from "@/store/modules/workflow"
import IconIonArrowForwardOutline from "~icons/ion/arrow-forward-outline"
import IconIonCloud from "~icons/ion/cloud"
import IconIonEllipsisVertical from "~icons/ion/ellipsis-vertical"
import { useMessage } from "naive-ui"
import { computed } from "vue"
import { useI18n } from "vue-i18n"

const props = defineProps<{
  node: FlowNode
  index: number
  isLast: boolean
}>()

const emit = defineEmits<{
  (e: "generateInitialValues"): void
  (e: "showReport"): void
  (e: "addRecord"): void
  (e: "redoRecord"): void
  (e: "setIntermediateConclusion"): void
  (e: "showIntermediateConclusion"): void
  (e: "showInitialValues"): void
  (e: "endWorkflow"): void
  (e: "delete"): void
}>()

const message = useMessage()
const { t, locale } = useI18n()

const nodeActions = computed(() => {
  const actions = [
    {
      label: t("page.protocol.workflow.showReport"),
      key: "show-report",
      disabled: props.node.status !== "done",
    },
    {
      label: t("page.protocol.workflow.showIntermediateConclusion"),
      key: "show-intermediate-conclusion",
      disabled: !props.node.intermediate_conclusion,
    },
    {
      label: t("page.protocol.workflow.redoRecord"),
      key: "redo-record",
      disabled: props.node.status !== "done",
    },
  ]

  // Only allow deletion of end nodes
  if (props.isLast) {
    actions.push({
      label: t("page.protocol.workflow.deleteNode"),
      key: "delete",
      disabled: props.node.status !== "done",
    })
  }

  return actions
})

const floatingActions = computed(() => {
  const actions: Array<{
    key: string
    label: string
    type: "default" | "primary" | "info" | "success" | "warning" | "error"
    handler: () => void
  }> = []

  if (props.node.status === "init" || props.node.status === "generated") {
    if (props.node.type === "generated") {
      actions.push({
        key: "get-initial-values",
        label: t("page.protocol.workflow.getInitialValues"),
        type: "primary",
        handler: () => emit("generateInitialValues"),
      })
    }
    else {
      actions.push({
        key: "add-record",
        label: t("page.protocol.workflow.addRecord"),
        type: "primary",
        handler: () => emit("addRecord"),
      })
    }
  }

  if (props.node.status === "done") {
    if (props.isLast) {
      actions.push({
        key: "end-workflow",
        label: t("page.protocol.workflow.endWorkflow"),
        type: "success",
        handler: () => emit("endWorkflow"),
      })
    }
    else {
      actions.push({
        key: "set-conclusion",
        label: t("page.protocol.workflow.writeConclusion"),
        type: "info",
        handler: () => emit("setIntermediateConclusion"),
      })
    }
  }

  return actions
})

function handleNodeAction(key: string) {
  switch (key) {
    case "show-report":
      emit("showReport")
      break
    case "show-intermediate-conclusion":
      emit("showIntermediateConclusion")
      break
    case "redo-record":
      emit("redoRecord")
      break
    case "delete":
      emit("delete")
      break
    default:
      message.warning(t("common.actionNotImplemented"))
  }
}
</script>

<style scoped lang="sass">
.border-gradient
  border-image: linear-gradient(to right, #1a79ff, #7c4dff) 1

:deep(.n-tag)
  text-transform: capitalize
</style>
