<template>
  <define-item-box
    v-slot="{ label, type, status, icon, onClick, iconProps, tooltip, $slots, name, sequence, showReselect, onReselect }"
  >
    <n-tooltip>
      <component :is="$slots.tooltip" v-if="$slots.tooltip" />
      <span v-else>
        {{ tooltip }}
      </span>
      <template #trigger>
        <div class="max-w-28 flex flex-col items-center self-start rounded-2 p-2">
          <component :is="icon" :pending="iconProps?.pending" />
          <div
            class="box__wrapper relative mt-2 w-full b-1 rounded-lg px-1 py-1 text-center"
            :class="{ 'ai-generated': type === 'generated', 'box__wrapper--done': status === 'done' }"
          >
            <span v-if="typeof label === 'string'">{{ label }}</span>
            <component :is="label" v-else-if="label" />
            <component :is="$slots.label" v-else-if="$slots.label" />
            <template v-else>
              <n-text class="block">
                {{ name }}
              </n-text>

              <n-button icon-placement="right" size="small" quaternary type="primary" @click="onClick">
                # {{ sequence }}
                <template #icon>
                  <n-icon :size="14">
                    <icon-ion-open-outline />
                  </n-icon>
                </template>
              </n-button>
            </template>
            <n-button
              v-if="showReselect && onReselect" class="box__badge group !px-2 !font-0" round
              :theme-overrides="{ color: '#666' }"
              @click="onReselect"
            >
              <n-icon size="10">
                <icon-ion-refresh-outline />
              </n-icon>
              <span
                class="max-w-0 whitespace-nowrap text-xs opacity-0 transition-all duration-200 group-hover:ml-2 group-hover:max-w-[4rem] group-hover:opacity-100"
              >
                {{ $t("common.reselect") }}
              </span>
            </n-button>
          </div>
        </div>
      </template>
    </n-tooltip>
  </define-item-box>

  <define-box-connector v-slot="{ action, redo, onRedo }">
    <div class="relative h-full min-w-12 w-fit pb-9 text-center">
      <div v-if="action" class="flex-center gap-2" :class="{ 'px-4': redo && onRedo }">
        <tooltip-button
          :tooltip="action.label" :icon="action.icon"
          :icon-props="{ size: 20 }"
          :button-props="{ size: 'small', text: true, ...action.buttonProps, onClick: undefined }"
          @click="action.handler"
        />
        <tooltip-button v-if="redo && onRedo" :tooltip="$t('common.redo')" :icon="RefreshIcon" :icon-props="{ size: 16 }" :button-props="{ size: 'small', text: true }" />
      </div>
      <div class="pointer-events-none absolute-center w-full items-center opacity-60">
        <div class="h-[2px] w-full rounded bg-[#A1A4AF] -mr-1" />
        <n-icon size="20" color="#A1A4AF">
          <icon-ion-arrow-forward-outline />
        </n-icon>
      </div>
    </div>
  </define-box-connector>
  <div class="relative min-w-1/2 w-fit b-1 rounded-xl p-3" v-bind="$attrs">
    <div class="mb-2 flex flex-wrap items-center gap-2">
      <span class="text-gray-700 font-bold">
        {{ $t("page.protocol.workflow.protocolIndex", { index: props.item.node?.data?.sequence }) }}
      </span>
      <n-tag :bordered="false" type="info" size="small" round>
        {{ props.item.airalogy_protocol_id }}
      </n-tag>
      <n-dropdown :options="dropdownOptions" trigger="click" placement="bottom-end">
        <n-button
          class="ml-auto opacity-30 transition-opacity duration-200 hover:opacity-100" quaternary size="small"
          icon-placement="right"
        >
          <span v-if="props.item.unit_path_index" class="text-gray-500">
            # {{ props.item.unit_path_index }}
          </span>
          <template #icon>
            <n-icon size="14">
              <icon-ion-menu-outline />
            </n-icon>
          </template>
        </n-button>
      </n-dropdown>
    </div>

    <div class="flex flex-wrap items-center">
      <item-box
        :tooltip="$t('page.protocol.workflow.selectedProtocol')" :name="$t('common.protocol')" :sequence="item.node?.data?.sequence" :icon="ResearchIcon"
        :icon-props="{ size: 60 }" :type="item.type" :status="item.status" :show-reselect="true"
        @reselect="handleReselect" @click="handleAddRecord"
      >
        <template v-if="item.node?.data?.target" #tooltip>
          <div class="space-y-1">
            <div class="font-medium">
              {{ $t("common.protocol") }}: {{ item.node?.data?.label }}
            </div>
            <div class="text-sm">
              {{ $t("common.uuid") }}: {{ item.node?.data?.target.research_node?.uuid }}
            </div>
            <div class="text-sm">
              {{ $t("common.lab") }}: {{ item.node?.data?.target.lab_name }}
            </div>
            <div class="text-sm">
              {{ $t("common.project") }}: {{ item.node?.data?.target.project_name }}
            </div>
            <div class="text-sm">
              {{ $t("common.updated") }}: {{ formatDate(item.node?.data?.target.updated_at, "date-short") }}
            </div>
          </div>
        </template>
      </item-box>

      <box-connector :action="recordAction" :type="item.type" :redo="recordAction === showInitialValuesAction" :on-redo="handleRedo" />

      <item-box
        v-if="record?.data && !isEmpty(record.data)" :name="$t('common.record')" :sequence="record.data.number"
        :class="{ 'cursor-not-allowed': item.type === 'generated' && item.initialValue }" :icon="RecordIcon"
        :type="props.item.research" :status="props.item.status" :icon-props="{ size: 60 }"
      >
        <template #tooltip>
          <div class="space-y-1">
            <div class="font-medium">
              {{ $t("page.protocol.workflow.recordIndex", { id: record.data.id }) }}
            </div>
            <div class="text-sm">
              {{ $t("common.created") }}: {{ formatDate(record.data.created_at, "date-time") }}
            </div>
            <template v-if="record.data.data?.var">
              <div class="mt-2 font-medium">
                {{ $t("common.variables") }}:
              </div>
              <div v-for="(value, key) in record.data.data.var" :key="key" class="text-sm">
                {{ key }}: {{ value }}
              </div>
            </template>
          </div>
        </template>
      </item-box>

      <item-box
        v-else :tooltip="$t('page.protocol.workflow.clickToAddRecord')" :label="$t('page.protocol.workflow.waitingForRecord')" :icon="RecordIcon"
        :type="props.item.research" :status="props.item.status" :icon-props="{ pending: true, size: 60 }"
        @click="handleAddRecord"
      />
      <template v-if="item.status === 'conclusion'">
        <box-connector />

        <n-text class="mx-3">
          <span class="whitespace-nowrap">{{ $t("page.protocol.workflow.waitingForConclusion") }}</span>
          <!-- <template v-if="item.status === 'init' && item.type === 'manual'">
          recording
        </template>
  <template v-else-if="item.status === 'init' || (item.type === 'generated' && item.status === 'generated')">
          initial-values
        </template>
  <template v-else-if="item.status === 'pending'">
          recording
        </template>
  <template v-else-if="item.status === 'conclusion'">
          intermediate conclusion
        </template> -->
        </n-text>
      </template>
    </div>
    <conclusion-modal
      v-if="item.status === 'conclusion' || item.status === 'done'" class="mt-3 min-w-fit w-200"
      :node="item" :title="$t('page.protocol.workflow.intermediateConclusion')" :workflow-model="model"
      :editor-only="!nodeConclusions[item.id]?.collapse" @action:generate-conclusion="handleGenerateConclusion"
      @action:end-workflow="handleConclusionConfirm" @action:set-conclusion="handleConclusionConfirm"
    />
  </div>
</template>

<script setup lang="tsx">
import type { FlowNode, SelectedNode, WorkflowModel } from "@/store/modules/workflow"
import type { ButtonProps, DropdownOption } from "naive-ui"
import type { FunctionalComponent } from "vue"
import ResearchIcon from "@/components/icon/protocol-icon.vue"

import RecordIcon from "@/components/icon/record-icon.vue"
import TooltipButton from "@airalogy/components/tooltip-button.vue"

import { useClosableMessage } from "@airalogy/composables"
import { formatDate } from "@airalogy/shared/utils"
import SetConclusionIcon from "~icons/ion/bulb-outline"
import AddRecordIcon from "~icons/ion/create-outline"
import ShowReportIcon from "~icons/ion/document-text"
import RefreshIcon from "~icons/ion/refresh-outline"
import EndWorkflowIcon from "~icons/ion/stop-circle-outline"
import GenerateIcon from "~icons/local/generate-value"
import GenerateDoneIcon from "~icons/local/generated-value"
import { isEmpty } from "lodash-es"
import { onMounted } from "vue"
import { useI18n } from "vue-i18n"
import ConclusionModal from "./conclusion-modal.vue"

defineOptions({ inheritAttrs: false })

const props = defineProps<IProps>()
const emit = defineEmits<IEmits>()
const { t, locale } = useI18n()

interface IProps {
  item: FlowNode
  model: WorkflowModel
  isStart: boolean
  isEnd: boolean
}

interface IEmits {
  (e: "action:add-record", payload?: any): void
  (e: "action:redo-record", payload?: any): void
  (e: "action:generate-initial-values", payload?: any): void
  (e: "action:show-initial-values", payload?: any): void
  (e: "action:delete", payload?: any): void
  (e: "action:show-report", payload?: any): void
  (e: "action:set-intermediate-conclusion", payload?: any): void
  (e: "action:show-intermediate-conclusion", payload?: any): void
  (e: "action:end-workflow", payload?: any): void
  (e: "action:generate-conclusion", payload: { type: "intermediate" | "final", id: string, node?: any }): void
  (e: "action:reselect", payload?: any): void
}

// Add state management for conclusions
interface ConclusionState {
  collapse: boolean
  showFinal: boolean
  model: {
    intermediate: string
    final: string
  }
}

interface NodeConclusions {
  [nodeId: string]: ConclusionState
}

const nodeConclusions = ref<NodeConclusions>({})
const conclusionName = computed(() => {
  const sequence = props.item.node?.data?.sequence
  if (sequence) {
    return t("page.protocol.workflow.intermediateConclusionWithSequence", {
      protocolId: props.item.airalogy_protocol_id,
      sequence,
    })
  }
  return t("page.protocol.workflow.intermediateConclusionBase", { protocolId: props.item.airalogy_protocol_id })
})

// Initialize conclusion state for a node
function initNodeConclusion(nodeId: string) {
  if (!nodeConclusions.value[nodeId]) {
    nodeConclusions.value[nodeId] = {
      collapse: false,
      showFinal: false,
      model: {
        intermediate: props.model.record[nodeId]?.conclusion || "",
        final: props.model.finalResearchConclusion || "",
      },
    }
  }
}

const message = useClosableMessage()
// Add handler for conclusion confirmation
function handleConclusionConfirm(data: {
  final: string
  intermediate: string
  id?: string
  type: "intermediate" | "final" | "both"
  node?: SelectedNode | null
},
) {
  const { id, node, type, intermediate, final } = data
  if (!node || !id) {
    message.error(t("common.nodeNotFound"))
    return
  }

  const conclusionState = nodeConclusions.value[id]

  if (!conclusionState)
    return

  const payload = {
    type: conclusionState.showFinal ? "final" : "intermediate",
    id,
    data,
  }
  if (type === "intermediate") {
    conclusionState.model.intermediate = intermediate
  }
  else if (type === "final") {
    conclusionState.model.final = final
  }
  else if (type === "both") {
    conclusionState.model.intermediate = intermediate
    conclusionState.model.final = final
  }

  if (conclusionState.showFinal) {
    emit("action:end-workflow", payload)
  }
  else {
    emit("action:set-intermediate-conclusion", payload)
  }

  conclusionState.collapse = true
}

// Initialize conclusions when component is mounted
onMounted(() => {
  if (props.item?.id) {
    initNodeConclusion(props.item.id)
  }
})

const item = toRef(props, "item")

const record = computed(() => props.model.record[item.value.id])

const dropdownOptions = computed((): DropdownOption[] => {
  const { status } = item.value
  const options: DropdownOption[] = []

  const redoOption: DropdownOption = {
    label: t("common.redo"),
    key: "redo",
    props: {
      onClick: () => emit("action:redo-record", item.value),
    },
    icon: () => <n-icon><icon-ion-refresh-outline /></n-icon>,
  }

  const deleteOption: DropdownOption = {
    label: t("common.delete"),
    key: "delete",
    props: {
      onClick: () => emit("action:delete", item.value),
    },
    icon: () => <n-icon><icon-local-delete /></n-icon>,
  }

  const showIntermediateOption: DropdownOption = {
    label: t("page.protocol.workflow.showIntermediateConclusion"),
    key: "show-conclusion",
    props: {
      onClick: () => emit("action:show-intermediate-conclusion", { ...item.value, isEnd: props.isEnd }),
    },
    icon: () => <n-icon><icon-ion-bulb-outline /></n-icon>,
  }

  const showReportOption: DropdownOption = {
    label: t("page.protocol.workflow.showReport"),
    key: "show-report",
    props: {
      onClick: () => emit("action:show-report", item.value),
    },
    icon: () => <n-icon><icon-ion-document-text-outline /></n-icon>,
  }

  const endWorkflowOption: DropdownOption = {
    label: t("page.protocol.workflow.endWorkflow"),
    key: "end-workflow",
    props: {
      onClick: () => emit("action:end-workflow", item.value),
    },
    icon: () => <n-icon><icon-ion-stop-circle-outline /></n-icon>,
  }

  if (props.isEnd && status !== "done") {
    options.push(redoOption)
    options.push(deleteOption)
  }

  if (status === "done") {
    options.push(showReportOption)
    options.push(showIntermediateOption)
    options.push(endWorkflowOption)
  }

  return options
})

const generateInitialValuesAction = computed<IStatusAction>(() => ({
  label: t("page.protocol.workflow.getInitialValues"),
  icon: GenerateIcon,
  handler: () => emit("action:generate-initial-values", item.value),
  buttonProps: {
    themeOverrides: { textColorText: "#A1A4AF" },
  },
  loading: false,
  disabled: false,
}))

const showInitialValuesAction = computed<IStatusAction>(() => ({
  label: t("page.protocol.workflow.showInitialValues"),
  icon: GenerateDoneIcon,
  handler: () => emit("action:show-initial-values", item.value),
  buttonProps: {
    type: "primary",
  },
  loading: false,
  disabled: false,
}))

const intermediateConclusionAction = computed<IStatusAction>(() => ({
  label: t("page.protocol.workflow.writeIntermediateConclusion"),
  icon: SetConclusionIcon,
  handler: () => emit("action:set-intermediate-conclusion", { ...item.value, isEnd: props.isEnd }),
  buttonProps: {
    themeOverrides: { textColorText: "#A1A4AF" },
  },
  loading: false,
  disabled: false,
}))

const addNewRecordAction = computed<IStatusAction>(() => ({
  label: t("page.protocol.workflow.addRecord"),
  icon: AddRecordIcon,
  handler: () => emit("action:add-record", item.value),
  buttonProps: {
    themeOverrides: { textColorText: "#A1A4AF" },
  },
  loading: false,
  disabled: false,
}))

const showReportAction = computed<IStatusAction>(() => ({
  label: t("page.protocol.workflow.showReport"),
  icon: ShowReportIcon,
  handler: () => emit("action:show-report", item.value),
  buttonProps: {
    type: "primary",
  },
  loading: false,
  disabled: false,
}))

const endWorkflowAction = computed<IStatusAction>(() => ({
  label: t("page.protocol.workflow.endWorkflow"),
  icon: EndWorkflowIcon,
  buttonProps: {
    onClick: () => emit("action:end-workflow", item.value),
    themeOverrides: { textColorText: "#A1A4AF" },
  },
  loading: false,
  disabled: false,
}))

interface IStatusAction {
  label: string
  icon: FunctionalComponent
  loading: boolean
  disabled: boolean
  buttonProps?: ButtonProps
  handler?: () => void
}

interface IItemBox {
  label?: string | Component
  tooltip?: string
  icon: Component
  iconProps?: Record<string, any>
  type: "manual" | "generated"
  status: "init" | "generating" | "regenerate" | "generated" | "pending" | "done" | "error" | "deleted" | "conclusion"
  onClick?: () => void
  onReselect?: () => void
  name?: string
  sequence?: number
  showReselect?: boolean
}

interface RecordNode extends IItemBox {
  sequence: number
}

interface IBoxConnector {
  action?: IStatusAction
  redo?: boolean
  onRedo?: () => void
}

const [DefineItemBox, ItemBox] = createReusableTemplate<IItemBox, { label: undefined, tooltip: undefined }>()
const [DefineBoxConnector, BoxConnector] = createReusableTemplate<IBoxConnector>()

const recordAction = computed(() => {
  const { status, type } = item.value

  switch (status) {
    case "init":
      return isEmpty(item.value.initialValue) ? generateInitialValuesAction.value : showInitialValuesAction.value
      break
    case "generating":
      return generateInitialValuesAction.value
    case "generated":
    case "pending":
    case "conclusion":
    case "done":
      return showInitialValuesAction.value
    // return showReportAction
    // return endWorkflowAction
    default:
      return undefined
  }

  return undefined
})

function handleRedo() {
  emit("action:redo-record", item.value)
}
// const recordActionList = computed((): IStatusAction[] => {
//   const { status, type } = item.value

//   const actions: IStatusAction[] = []
//   switch (status) {
//     case "init":
//       if (type === "generated") {
//         actions.push(generateInitialValuesAction)
//       }

//       if (type === "manual") {
//         actions.push(addNewRecordAction)
//       }
//       break
//     case "generating":
//       actions.push({ ...generateInitialValuesAction, loading: true, disabled: true })
//       break

//     case "generated":
//       actions.push(showInitialValuesAction)
//       break

//     case "pending":
//       if (type === "generated") {
//         actions.push(showInitialValuesAction)
//       }

//       actions.push(addNewRecordAction)
//       break
//     case "conclusion":
//       actions.push(showReportAction)
//       actions.push(intermediateConclusionAction)
//       break
//     case "done":
//       if (props.isEnd && !props.model.finalResearchConclusion) {
//         actions.push(endWorkflowAction)
//       }
//       break
//     case "regenerate":
//     case "error":
//     case "deleted":
//   }

//   return actions
// })

function handleAddRecord() {
  emit("action:add-record", item.value)
}

function handleReselect() {
  emit("action:reselect", item.value)
}
function handleGenerateConclusion(payload: { type: "intermediate" | "final", node?: SelectedNode | null }) {
  emit("action:generate-conclusion", {
    type: payload.type,
    id: item.value.id,
    node: payload.node,
  })
}
</script>

<style scoped lang="sass">
@use "@styles/sass/variable.sass" as *

.box__wrapper
  position: relative

  &--done
    // border-color: $primary-color

  .box__badge
    background: transparent
    position: absolute!important
    bottom: 0
    right: 0
    transform: translateX(50%) translateY(50%)
    text-align: center
    height: 24px!important
    font-size: 12px
    border-radius: 100px
    &--small
      font-size: 10px
      line-height: 1.5
  & > *
    position: relative
    z-index: 3
  &:not(.ai-generated--no-bg)::before
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
  &:not(.ai-generated--no-bg)::after
    content: ""
    position: absolute
    top: 0
    left: 0
    width: 100%
    height: 100%
    background: #fff
    z-index: 2
    border-radius: 6px

.ai-generated
  --ai-linear: linear-gradient(130deg, rgba(26, 121, 255, 0.8) 0%, rgba(122, 75, 255, 0.8) 100%)

  .box__badge
    background: var(--ai-linear)
    color: white

@keyframes flow
  0%
    background-position: 0% 50%
  100%
    background-position: 100% 50%
</style>
