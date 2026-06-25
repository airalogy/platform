<template>
  <div class="relative h-full" :class="node.status === 'done' ? isEnd ? 'min-w-12' : 'w-6' : 'min-w-20'">
    <div v-if="actions.length > 0" class="flex items-center justify-center pr-4 -mt-7">
      <action-button v-for="(action, idx) in actions" :key="idx" v-bind="action" />
    </div>
    <div class="absolute-center w-full items-center opacity-60">
      <div class="h-[2px] w-full rounded bg-[#A1A4AF] -mr-1" />
      <n-icon size="20" color="#A1A4AF">
        <icon-ion-arrow-forward-outline />
      </n-icon>
    </div>
    <n-text
      v-if="node.status !== 'done'"
      class="absolute-center h-fit w-full flex-col items-center pr-1 pt-2 text-[10px] line-height-tight"
      depth="3"
    >
      <span class="whitespace-nowrap">{{ waitingLabel }}</span>
    </n-text>
  </div>
</template>

<script setup lang="ts">
import type { FlowNode } from "@/store/modules/workflow"
import type { ButtonProps } from "naive-ui"
import type { FunctionalComponent } from "vue"

import SetConclusionIcon from "~icons/ion/bulb-outline"
import GenerateDoneIcon from "~icons/ion/cloud-done"
import GenerateIcon from "~icons/ion/cloud-download-outline"
import AddRecordIcon from "~icons/ion/create-outline"
import ShowReportIcon from "~icons/ion/document-text"
import EndWorkflowIcon from "~icons/ion/stop-circle-outline"
import { useI18n } from "vue-i18n"

interface Action {
  label: string
  icon: FunctionalComponent
  loading?: boolean
  disabled?: boolean
  buttonProps?: ButtonProps
}

const props = defineProps<{
  node: FlowNode
  isEnd: boolean
}>()

const emit = defineEmits<{
  (e: "action:generate-initial-values", node: FlowNode): void
  (e: "action:show-initial-values", node: FlowNode): void
  (e: "action:add-record", node: FlowNode): void
  (e: "action:show-report", node: FlowNode): void
  (e: "action:set-intermediate-conclusion", node: FlowNode): void
  (e: "action:end-workflow", node: FlowNode): void
}>()

const { t, locale } = useI18n()

const waitingLabel = computed(() => {
  const { status, type } = props.node
  if (status === "init" && type === "manual")
    return t("page.protocol.workflow.waitingForRecord")
  if (status === "init" || (type === "generated" && status === "generated"))
    return t("page.protocol.workflow.waitingForInitialValues")
  if (status === "pending")
    return t("page.protocol.workflow.waitingForRecord")
  if (status === "conclusion")
    return t("page.protocol.workflow.waitingForConclusion")
  return ""
})

const actions = computed(() => {
  const { status, type } = props.node
  const actionList: Action[] = []

  switch (status) {
    case "init":
      if (type === "generated") {
        actionList.push({
          label: t("page.protocol.workflow.getInitialValues"),
          icon: GenerateIcon,
          buttonProps: {
            onClick: () => emit("action:generate-initial-values", props.node),
            themeOverrides: { textColorText: "#A1A4AF" },
          },
        })
      }
      if (type === "manual") {
        actionList.push({
          label: t("page.protocol.workflow.addRecord"),
          icon: AddRecordIcon,
          buttonProps: {
            onClick: () => emit("action:add-record", props.node),
            themeOverrides: { textColorText: "#A1A4AF" },
          },
        })
      }
      break

    case "generating":
      actionList.push({
        label: t("page.protocol.workflow.getInitialValues"),
        icon: GenerateIcon,
        loading: true,
        disabled: true,
        buttonProps: {
          themeOverrides: { textColorText: "#A1A4AF" },
        },
      })
      break

    case "generated":
      actionList.push({
        label: t("page.protocol.workflow.showInitialValues"),
        icon: GenerateDoneIcon,
        buttonProps: {
          onClick: () => emit("action:show-initial-values", props.node),
          type: "primary",
        },
      })
      break

    case "pending":
      if (type === "generated") {
        actionList.push({
          label: t("page.protocol.workflow.showInitialValues"),
          icon: GenerateDoneIcon,
          buttonProps: {
            onClick: () => emit("action:show-initial-values", props.node),
            type: "primary",
          },
        })
      }
      actionList.push({
        label: t("page.protocol.workflow.addRecord"),
        icon: AddRecordIcon,
        buttonProps: {
          onClick: () => emit("action:add-record", props.node),
          themeOverrides: { textColorText: "#A1A4AF" },
        },
      })
      break

    case "conclusion":
      actionList.push({
        label: t("page.protocol.workflow.showReport"),
        icon: ShowReportIcon,
        buttonProps: {
          onClick: () => emit("action:show-report", props.node),
          type: "primary",
        },
      })
      actionList.push({
        label: t("page.protocol.workflow.writeIntermediateConclusion"),
        icon: SetConclusionIcon,
        buttonProps: {
          onClick: () => emit("action:set-intermediate-conclusion", props.node),
          themeOverrides: { textColorText: "#A1A4AF" },
        },
      })
      break

    case "done":
      if (props.isEnd) {
        actionList.push({
          label: t("page.protocol.workflow.endWorkflow"),
          icon: EndWorkflowIcon,
          buttonProps: {
            onClick: () => emit("action:end-workflow", props.node),
            themeOverrides: { textColorText: "#A1A4AF" },
          },
        })
      }
      break
  }

  return actionList
})

const [DefineActionButton, ActionButton] = createReusableTemplate<Action>()
</script>

<style scoped>
.absolute-center {
  @apply absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 flex;
}
</style>
