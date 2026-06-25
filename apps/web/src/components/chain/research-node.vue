<template>
  <n-dropdown :options="dropdownOptions">
    <div
      class="mx-3 b-1 rounded-2 p-2 hover:shadow"
      :class="{
        'ai-generated': node.type === 'generated',
        'box__wrapper--done': node.status === 'done',
      }"
    >
      <div v-if="node.type === 'generated'" class="box__badge">
        <n-icon size="10">
          <icon-ion-sparkles />
        </n-icon>
        AI
      </div>
      <div class="flex flex-col items-center">
        <n-tooltip trigger="hover" placement="top">
          {{ node.node?.data?.label ?? node.airalogy_protocol_id }}
          <template #trigger>
            <div class="mb-2 rounded bg-[#F1F4F6] px-3 py-1">
              {{ $t("page.protocol.workflow.protocolIndex", { index: node.node?.data?.sequence || "-" }) }}
            </div>
          </template>
        </n-tooltip>
        <n-button
          v-if="node.status === 'done' && history?.data"
          icon-placement="right"
          size="small"
          ghost
          type="primary"
          @click="emit('action:show-report', node)"
        >
          #{{ history.data.id }}
          <template #icon>
            <n-icon>
              <icon-ion-open-outline />
            </n-icon>
          </template>
        </n-button>
        <n-text v-else>
          -
        </n-text>
      </div>
    </div>
  </n-dropdown>
</template>

<script setup lang="ts">
import type { FlowNode, WorkflowModel } from "@/store/modules/workflow"
import type { DropdownOption } from "naive-ui"
import { useI18n } from "vue-i18n"

const props = defineProps<{
  node: FlowNode
  model: WorkflowModel
  isEnd: boolean
}>()

const emit = defineEmits<{
  (e: "action:show-report", node: FlowNode): void
  (e: "action:redo-record", node: FlowNode): void
  (e: "action:delete", node: FlowNode): void
  (e: "action:show-intermediate-conclusion", node: FlowNode): void
}>()

const { t, locale } = useI18n()

const history = computed(() => props.model.record[props.node.id])

const dropdownOptions = computed((): DropdownOption[] => {
  const { status } = props.node
  const options: DropdownOption[] = []

  if (props.isEnd && status !== "done") {
    options.push({
      label: t("common.redo"),
      key: "redo",
      props: {
        onClick: () => emit("action:redo-record", props.node),
      },
      icon: () => h("n-icon", {}, [h("icon-ion-refresh-outline")]),
    })
    options.push({
      label: t("common.delete"),
      key: "delete",
      props: {
        onClick: () => emit("action:delete", props.node),
      },
      icon: () => h("n-icon", {}, [h("icon-local-delete")]),
    })
  }

  if (status === "done") {
    options.push({
      label: t("page.protocol.workflow.showReport"),
      key: "show-report",
      props: {
        onClick: () => emit("action:show-report", props.node),
      },
      icon: () => h("n-icon", {}, [h("icon-ion-document-text-outline")]),
    })
    options.push({
      label: t("page.protocol.workflow.showIntermediateConclusion"),
      key: "show-conclusion",
      props: {
        onClick: () => emit("action:show-intermediate-conclusion", props.node),
      },
      icon: () => h("n-icon", {}, [h("icon-ion-bulb-outline")]),
    })
  }

  return options
})
</script>

<style scoped lang="sass">
.box__wrapper--done
  // border-color: $primary-color

.ai-generated
  --ai-linear: linear-gradient(130deg, rgba(26, 121, 255, 0.8) 0%, rgba(122, 75, 255, 0.8) 100%)
  position: relative

  .box__badge
    background: var(--ai-linear)
    position: absolute!important
    bottom: 0
    right: 0
    transform: translateX(50%) translateY(50%)
    text-align: center
    padding: 0 8px
    color: white
    font-size: 12px
    border-radius: 100px

  & > *
    position: relative
    z-index: 3

  &::before
    content: ""
    background: var(--ai-linear)
    position: absolute
    top: -2px
    left: -2px
    width: calc(100% + 4px)
    height: calc(100% + 4px)
    z-index: 1
    border-radius: 8px
    animation: flow 5s linear infinite

  &::after
    content: ""
    position: absolute
    top: 0
    left: 0
    width: 100%
    height: 100%
    background: #fff
    z-index: 2
    border-radius: 6px

@keyframes flow
  0%
    background-position: 0% 50%
  100%
    background-position: 100% 50%
</style>
