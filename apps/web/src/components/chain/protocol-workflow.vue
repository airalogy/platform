<template>
  <div v-if="workflowModel && flowNodes && workflowNodes">
    <n-form class="b-t-1 p-4" :model="workflowModel" :rules="rules">
      <n-form-item label="Research Goal" required path="goal" label-style="font-size: 16px; font-weight: 600">
        <markdown-editor v-model:text="workflowModel.goal" raw-result class="h-fit" :post-add-attachments="postAddAttachments" />
      </n-form-item>

      <n-form-item
        label-placement="left" path="researchable" label-style="font-size: 16px; font-weight: 600"
        class="reset-form"
      >
        <template #label>
          <n-tooltip trigger="hover">
            Is this research can be researched?
            <template #trigger>
              <n-flex align="center">
                Researchable
                <n-icon>
                  <icon-local-information />
                </n-icon>
              </n-flex>
            </template>
          </n-tooltip>
        </template>

        <custom-checkbox
          v-model:checked="workflowModel.researchable" scope="research_workflow" :checked-value="true"
          :unchecked-value="false" :theme-overrides="researchableInfo.themeOverrides" class="ml-4 mr-auto"
        >
          <span class="ml-2 font-bold capitalize">{{ researchableInfo.label }}</span>
        </custom-checkbox>
      </n-form-item>

      <n-form-item label="Research Strategy" required path="strategy" label-style="font-size: 16px; font-weight: 600">
        <markdown-editor
          v-model:text="workflowModel.strategy" raw-result class="h-fit"
          :class="{ 'pb-8': workflowModel.strategy }"
          :post-add-attachments="postAddAttachments"
        >
          <template #action>
            <ai-button
              :button-props="strategyButtonProps" button-class="absolute right-2 bottom-2"
              tooltip="Let AI Generate Research Strategy"
            >
              AI
            </ai-button>
          </template>
        </markdown-editor>
      </n-form-item>
    </n-form>

    <div v-if="pathData?.steps" class="b-t-1 p-4">
      <workflow-timeline
        v-model:selected-research-node="selectedResearchNode" v-model:workflow-model="workflowModel"
        v-model:flow-nodes="flowNodes" v-model:show-intermediate="showConclusion"
        v-model:show-initial-values="isInitialValuesShown" :steps="pathData.steps" :workflow-nodes="workflowNodes"
        @select:next-research-node="showManualResearchNode" @generate:initial-values="handleGenerateInitialValue"
        @action:end-workflow="handleEndWorkflow" @action:generate-conclusion="handleGenerateConclusion"
        @action:show-final-conclusion="handleShowFinalConclusion"
      />
    </div>
    <div v-else>
      <n-skeleton text :repeat="6" />
    </div>

    <!-- Replace modal with plain conclusion modal component -->
    <!--
    <div v-if="showConclusion">
      <conclusion-modal
        :node="selectedResearchNode" :show="showConclusion" :workflow-model="workflowModel"
        @update:show="showConclusion = $event" @action:generate-conclusion="handleGenerateConclusion"
        @action:set-conclusion="handleSetConclusion" @action:end-workflow="handleEndConclusion"
      />
    </div>

  -->

    <select-node-modal
      v-model:show="isManualResearchNodeShown" :workflow-nodes="workflowNodes"
      :workflow-model="workflowModel" :flow-nodes="flowNodes" @action:add-next-node="handleAddNextRN"
      @action:ai-select="handleAISelectFromModal"
    />

    <generate-initial-values-modal
      v-model:show="isInitialValuesShown" v-model:selected-node="selectedResearchNode"
      :loading="loadingRecord.getInitialValue" @action:accept-initial-values="handleAcceptInitialValue"
      @action:regenerate-initial-values="handleGenerateInitialValue"
    />
  </div>
  <div v-else>
    Error loading workflow
  </div>
</template>

<script setup lang="ts">
import type {
  StepItem,
  WorkflowGeneratePayload,
} from "@/types/workflow"
import type { ProtocolModels } from "@airalogy/shared"
import type { CheckboxProps } from "naive-ui"
import { useBoolean, useFormRules } from "@/composables"
import { postAddAttachments } from "@/service/api/attachments"
import { postGenerateWorkflow, postStartWorkflow } from "@/service/api/workflow"

import {
  type FlowNode,
  type SelectedNode,
  useProtocolWorkflowStore,
  type WorkflowModel,
} from "@/store/modules/workflow"
import { useClosableMessage } from "@airalogy/composables"
import { getRealAiralogyId } from "@airalogy/shared/utils/parseAiralogyId"
import { useRouteQuery } from "@vueuse/router"
import { nanoid } from "nanoid"
import { useI18n } from "vue-i18n"
import { WorkflowStatus, WorkflowStep } from "../../enum/workflow"
import GenerateInitialValuesModal from "./generate-initial-values-modal.vue"
import SelectNodeModal from "./select-node-modal.vue"
import WorkflowTimeline from "./workflow-timeline.vue"

interface IProps {
  workflowId: string
}

const props = withDefaults(defineProps<IProps>(), {})

const emit = defineEmits<IEmits>()
interface IEmits {
  (e: "update:selectedResearchNode", value: any): void
  (e: "update:workflowNodes", value: any): void
  (e: "update:flowNode", value: any): void
  (e: "update:workflowData", value: any): void
  (e: "update:workflow", value: any): void
}

const workflowStore = useProtocolWorkflowStore()

const {
  bool: isInitialValuesShown,
  setTrue: showInitialValues,
  setFalse: hideInitialValues,
} = useBoolean(false)
const {
  bool: isManualResearchNodeShown,
  setTrue: showManualResearchNode,
  setFalse: hideManualResearchNode,
} = useBoolean(false)
// const { openNewTab } = useOpenNewTab()

const workflowInfo = computed(() => workflowStore.getWorkflow(props.workflowId))

const flowNodes = computed({
  get: () => workflowInfo.value?.flowNodes,
  set: (newFlowNodes) => {
    workflowStore.setFlowNodes(props.workflowId, newFlowNodes)
  },
})
const workflowData = computed({
  get: () => workflowInfo.value?.data,
  set: (newData) => {
    workflowStore.setData(props.workflowId, newData)
  },
})
const workflowNodes = computed({
  get: () => workflowInfo.value?.workflowNodes,
  set: (newWorkflowNodes) => {
    workflowStore.setWorkflowNodes(props.workflowId, newWorkflowNodes)
  },
})

watch(
  workflowNodes,
  (nodes) => {
    if (!nodes?.length || !flowNodes.value?.length) {
      return
    }

    let changed = false
    const nextFlowNodes = flowNodes.value.map((node) => {
      if (node.node) {
        return node
      }

      const workflowNode = nodes.find(item =>
        item.id === node.airalogy_protocol_id
        || item.data?.target?.uid === node.airalogy_protocol_id,
      )
      if (!workflowNode) {
        return node
      }

      changed = true
      return { ...node, node: workflowNode }
    })

    if (changed) {
      flowNodes.value = nextFlowNodes
    }
  },
  { immediate: true },
)
const workflowModel = computed({
  get: () => workflowInfo.value?.model,
  set: (newModel) => {
    workflowStore.setModel(props.workflowId, newModel)
  },
})
// const steps = computed({
//   get: () => workflowInfo.value?.steps,
//   set: newSteps => workflowStore.setSteps(props.workflowId, newSteps),
// })
const pathData = computed({
  get: () => workflowInfo.value?.path,
  set: newPath => workflowStore.setPath(props.workflowId, newPath || { path_status: WorkflowStatus.RESEARCH_GOAL, /* research_goal: "",  research_strategy: "", */ researchable: false, steps: [] }),
})
const status = computed({
  get: () => pathData.value?.path_status || WorkflowStatus.RESEARCH_GOAL,
  set: (newStatus) => {
    if (!pathData.value) {
      return
    }
    pathData.value.path_status = newStatus
  },
})

const loadingRecord = reactive({
  goal: false,
  strategy: false,
  selectRN: false,
  getInitialValue: false,
  getInterMediateConclusion: false,
  getFinalConclusion: false,
  complete: false,
})

const message = useClosableMessage()
const { t, locale } = useI18n()
const nodesInfo = computed(() => workflowInfo.value?.flowNodes)
// const nodesInfo = computedAsync(async () => {
//   const nodes = workflowNodes.value
//   if (!nodes) {
//     return []
//   }

//   const res = await Promise.all(
//     nodes.map((node) => {
//       const target = (node.data.target || {}) as Api.Research.ResearchInfo

//       if (!target) {
//         return null
//       }

//       const { id, current_node_id } = target

//       if (!id || !current_node_id) {
//         return null
//       }

//       // return getProtocolContent(target?.id) as Promise<{ protocol: string, assigner: string, model: string } | null >
//       // return workflowStore.getPackage(id, current_node_id)
//     }),
//   )

//   return res
//     .map(
//       (content: { protocol: string, assigner: string, model: string } | null, idx: number): WorkflowProtocolInfo | null => {
//         if (!content) {
//           return null
//         }

//         const node = nodes[idx]
//         const target = node.data.target as Api.Research.ResearchInfo | null
//         if (!target || !content) {
//           return null
//         }

//         const { research_node, uid } = target
//         if (!research_node) {
//           return null
//         }

//         const { json_schema } = research_node

//         return {
//           ...content,
//           airalogy_protocol_id: uid,
//           field_json_schema: toRaw(json_schema),
//         }
//       },
//     )
//     .filter((it): it is WorkflowProtocolInfo => Boolean(it))
// }, null)

const selectedResearchNode = ref<SelectedNode | null>(null)

const { workflowId } = inject<{ workflowId: Ref<string> }>("protocol-workflow", {
  workflowId: ref(nanoid()),
})

const route = useRoute()

function getPayload(pathStatus: WorkflowStatus) {
  if (!workflowId.value) {
    return null
  }

  if (!workflowModel.value) {
    return null
  }

  const { researchable, finalResearchConclusion } = workflowModel.value

  const payload: WorkflowGeneratePayload = {
    oldStatus: status.value,
    workflowId: workflowId.value,
    workflowInfo: workflowData.value,
    pathData: {
      path_status: pathStatus,
      researchable: researchable || false,
      final_research_conclusion: finalResearchConclusion || "",
      steps: pathData.value?.steps || [],
    },
  }

  switch (pathStatus) {
    case WorkflowStatus.NEXT_PROTOCOL:
      payload.pathData.steps = pathData.value?.steps || []
      break
  }

  return payload
}

const strategyButtonProps = computed(() => ({
  onClick: handleGenerateStrategy,
  loading: loadingRecord.strategy,
  disabled: !workflowModel.value?.goal,
}))

async function handleStartWorkflow() {
  const workflowRawData = workflowStore.getData(props.workflowId)
  if (!workflowRawData) {
    message.error("No workflow found")
    return
  }
  const { protocolUid } = route.params as { protocolUid: string }
  const initialProtocolId = workflowRawData.protocols.find(
    protocol => protocol.protocol_index === workflowRawData.default_initial_protocol_index,
  )?.airalogy_protocol_id

  if (!initialProtocolId && !protocolUid) {
    message.error("No protocol ID found")
    return
  }

  /** create workflow */
  const { data } = await postStartWorkflow({
    workflow_info: workflowRawData,
    airalogy_protocol_id: initialProtocolId || protocolUid,
    research_goal: workflowModel.value?.goal || "",
  })
  if (!data) {
    message.error("Failed to create workflow")
    return
  }
  const { id, path_data: currentPathData } = data

  workflowId.value = id
  pathData.value = currentPathData
}

async function handleGenerateStrategy() {
  if (!workflowModel.value) {
    message.error("No model found")
    return
  }

  try {
    loadingRecord.strategy = true

    if (!workflowId.value || workflowInfo.value?.id !== workflowId.value) {
      await handleStartWorkflow()
    }

    if (status.value === WorkflowStatus.RESEARCH_GOAL) {
      if (workflowModel.value?.goal) {
        status.value = WorkflowStatus.RESEARCH_STRATEGY
      }
      else {
        message.error("Please input research goal first")
        return
      }
    }

    if (status.value === WorkflowStatus.RESEARCH_STRATEGY) {
      //
    }

    if (!status.value) {
      status.value = WorkflowStatus.RESEARCH_STRATEGY
    }

    const payload = getPayload(status.value)
    if (!payload) {
      message.error("No payload found")
      return
    }

    const res = await postGenerateWorkflow(payload)

    if (res.data) {
      const {
        path_data: { researchable, path_status },
      } = res.data

      pathData.value = res.data.path_data
      // workflowModel.value.strategy = research_strategy
      workflowModel.value.researchable = researchable

      message.success("Research strategy generated successfully")
      // const { path_data: { steps: resSteps } } = res.data
      // steps.value = resSteps
      // // find last step
      // const strategy = resSteps.findLast(it => it.step === '')
    }
  }
  catch (e) {
    //
  }
  finally {
    loadingRecord.strategy = false
  }
}

async function handleGenerateNextRN() {
  if (!workflowModel.value?.goal) {
    message.error("Please input research goal first")
    return
  }
  if (!flowNodes.value || !workflowNodes.value) {
    message.error("No workflow found")
    return
  }

  if (!workflowId.value) {
    await handleStartWorkflow()
  }

  const payload = getPayload(WorkflowStatus.NEXT_PROTOCOL)

  if (!payload) {
    message.error("No payload found")
    return
  }

  try {
    loadingRecord.selectRN = true
    const res = await postGenerateWorkflow(payload)

    if (res.data) {
      const {
        path_data: { path_status, steps: currSteps },
      } = res.data

      const targetNode = currSteps.findLast(it => it.step === WorkflowStep.ADD_NEXT_PROTOCOL)
      if (targetNode && targetNode.data?.end_path) {
        status.value = WorkflowStatus.END_AFTER_NEXT_PROTOCOL
        const { thought } = targetNode.data
        message.error(`Protocol workflow ended: ${thought}`)
        return
      }
      if (targetNode && targetNode.data) {
        targetNode.data.id = nanoid()
      }

      status.value = path_status
      // steps.value = currSteps
      pathData.value = res.data.path_data

      const nextNodeRes = currSteps.findLast(({ step }) => step === WorkflowStep.ADD_NEXT_PROTOCOL)
      if (nextNodeRes?.data) {
        const nextNode = nextNodeRes.data
        const { airalogy_protocol_id } = nextNode
        flowNodes.value.push({
          ...nextNode,
          id: nanoid(),
          node: workflowNodes.value.find(it => it.id === airalogy_protocol_id) || null,
          status: "init",
          initialValue: null,
          type: "generated",
        })
      }
    }
  }
  catch (e) {
    message.error(`Failed to generate next protocol: ${(e as Error).message}`)
  }
  finally {
    loadingRecord.selectRN = false
  }
}

function mergeStepWithId(prev: StepItem[], curr: StepItem[]) {
  const result = curr.map((it, idx, ary) => {
    if (it.step === WorkflowStep.ADD_NEXT_PROTOCOL) {
      const prevItem = prev[idx]
      if (
        prevItem
        && prevItem.step === WorkflowStep.ADD_NEXT_PROTOCOL
        && prevItem.data.airalogy_protocol_id === it.data.airalogy_protocol_id
        && prevItem.data.id
      ) {
        return { ...it, data: { ...it.data, id: prevItem.data.id } }
      }
    }
    else if (it.step === WorkflowStep.ADD_INITIAL_VALUES_FOR_FIELDS_IN_NEXT_PROTOCOL) {
      const prevItem = prev[idx - 1]

      if (
        prevItem
        && prevItem.step === WorkflowStep.ADD_NEXT_PROTOCOL
        && prevItem.data.airalogy_protocol_id === it.data.airalogy_protocol_id
        && prevItem.data.id
      ) {
        return { ...it, data: { ...it.data, id: prevItem.data.id } }
      }
    }

    return it
  })

  return result
}

async function handleGenerateInitialValue(node: FlowNode) {
  if (!workflowModel.value || !pathData.value?.steps) {
    message.error("No model found")
    return
  }

  const { airalogy_protocol_id, id } = node
  const targetNode = flowNodes.value?.find(it => it.id === id)
  if (!targetNode) {
    message.error("No protocol found")
    return
  }

  const lastIndex = pathData.value?.steps.findLastIndex(it => it.step === WorkflowStep.ADD_NEXT_PROTOCOL)
  if (lastIndex === -1 || !airalogy_protocol_id || !id) {
    message.error("Please get recommended next Research Protocol first")
    return
  }

  const payload = getPayload(WorkflowStatus.INITIAL_VALUES)

  if (!payload) {
    message.error("No payload found")
    return
  }

  // if the last step is not recommend_next_rn, then we need to slice the steps
  // because the steps will be used to generate the initial values for the fields (or re-generate the initial values for the fields)
  if (lastIndex < pathData.value?.steps.length - 1) {
    payload.pathData.steps = pathData.value?.steps.slice(0, lastIndex + 1)
  }

  try {
    selectedResearchNode.value = {
      ...targetNode,
      name: `Generating initial values for Research Protocol ${node.airalogy_protocol_id}?`,
    }
    loadingRecord.getInitialValue = true
    showInitialValues()

    status.value = WorkflowStatus.INITIAL_VALUES

    if (workflowModel.value.record[id]) {
      workflowModel.value.record[id].status = "generating"
      workflowModel.value.record[id].initialValue = null
    }
    else {
      workflowModel.value.record[id] = {
        status: "generating",
        data: {},
        id: airalogy_protocol_id,
        conclusion: "",
        initialValue: null,
        isConclusionGenerated: false,
      }
    }

    const res = await postGenerateWorkflow(payload)

    if (res.data) {
      const {
        path_data: { steps: currSteps, path_status },
      } = res.data

      pathData.value = {
        ...pathData.value,
        path_status,
        steps: mergeStepWithId(payload.pathData.steps, currSteps),
      }

      const initialValue = currSteps[currSteps.length - 1].data.values
      if (workflowModel.value.record[id]) {
        workflowModel.value.record[id].status = "generated"
        workflowModel.value.record[id].initialValue = initialValue
      }
      else {
        workflowModel.value.record[id] = {
          status: "generated",
          data: {},
          id: airalogy_protocol_id,
          conclusion: "",
          initialValue,
          isConclusionGenerated: false,
        }
      }

      if (targetNode) {
        targetNode.status = "generated"
        targetNode.initialValue = initialValue || null

        selectedResearchNode.value = {
          ...targetNode,
          name: `Using initial values for Research Protocol ${node.airalogy_protocol_id}?`,
          field: { var: initialValue },
        }
        message.success("Protocol initial values generated successfully")
      }
    }
  }
  catch (e) {
    //
  }
  finally {
    loadingRecord.getInitialValue = false
  }
}

function handleAcceptInitialValue(node: FlowNode) {
  if (!node) {
    message.error("No node selected")
    return
  }

  const { id, initialValue, airalogy_protocol_id } = node
  if (!initialValue) {
    message.error("No initial value found")
    return
  }

  const targetModel = workflowModel.value?.record[id]
  const targetNode = flowNodes.value?.find(it => it.id === id)
  if (!targetModel || !targetNode) {
    message.error("No model found")
    return
  }

  targetModel.initialValue = initialValue
  targetNode.status = "pending"

  if (node.node?.data?.sequence) {
    message.success(`Set initial value for Protocol #${node.node?.data?.sequence}(${airalogy_protocol_id})`)
  }
  else {
    message.success(`Set initial value for ${airalogy_protocol_id}`)
  }

  hideInitialValues()
}

const { defaultRequiredRule } = useFormRules()

const rules: Partial<Record<keyof WorkflowModel, App.Global.FormRule[]>> = {
  goal: [defaultRequiredRule],
  strategy: [defaultRequiredRule],
}

const checkboxOverrides: Record<string, any> = {
  init: {
    border: "2px solid rgb(224, 224, 230)",
    borderDisabled: "2px solid rgb(224, 224, 230)",
    borderRadius: "6px",
    borderFocus: "2px solid #18a058",
    boxShadowFocus: "0 0 0 2px rgba(24, 160, 88, 0.3)",
    borderChecked: "2px solid #18a058",
    borderDisabledChecked: "2px solid rgba(224, 224, 230)",
    labelPadding: "0 0",
  } satisfies CheckboxProps["themeOverrides"],
  checked: {
    border: "2px solid rgba(24, 160, 88, 0.6)",
    borderDisabled: "2px solid rgba(24, 160, 88, 0.6)",
    borderRadius: "6px",
    borderFocus: "2px solid rgba(24, 160, 88, 1)",
    boxShadowFocus: "0 0 0 2px rgba(24, 160, 88, 0.6)",
    borderChecked: "2px solid rgba(24, 160, 88, 1)",
    borderDisabledChecked: "2px solid rgba(24, 160, 88, 1)",
    colorChecked: "rgba(24, 160, 88, 1)",
    colorDisabledChecked: "rgba(24, 160, 88, 1)",
    checkMarkColorDisabledChecked: "#fff",
    labelPadding: "0 0",
  } satisfies CheckboxProps["themeOverrides"],
  unchecked: {
    border: "2px solid rgba(255, 80, 83, 0.6)",
    borderDisabled: "2px solid rgba(255, 80, 83, 0.6)",
    borderRadius: "6px",
    borderFocus: "2px solid rgba(255, 80, 83, 1)",
    boxShadowFocus: "0 0 0 2px rgba(255, 80, 83, 0.6)",
    borderChecked: "2px solid rgba(255, 80, 83, 1)",
    borderDisabledChecked: "2px solid rgba(255, 80, 83, 1)",
    colorChecked: "rgba(255, 80, 83, 1)",
    colorDisabledChecked: "rgba(255, 80, 83, 1)",
    labelPadding: "0 0",
  } satisfies CheckboxProps["themeOverrides"],
}

const researchableInfo = computed(() => {
  const info = { themeOverrides: checkboxOverrides.init, label: t("common.none") }

  if (!workflowModel.value) {
    message.error(t("page.protocol.workflow.noResearchNodeSelected"))
    return info
  }

  const { researchable } = workflowModel.value

  if (typeof researchable === "boolean") {
    if (researchable) {
      info.themeOverrides = checkboxOverrides.checked
      info.label = t("common.true")
    }
    else {
      info.themeOverrides = checkboxOverrides.unchecked
      info.label = t("common.false")
    }
  }
  return info
})

const showConclusion = ref(false)

function handleUpdateSelectedResearchNode(node: any) {
  if (node) {
    showInitialValues()
  }
  else {
    hideInitialValues()
  }
}

async function handleGenerateConclusion(requestPayload: {
  id?: string
  node?: SelectedNode | null
  type: "intermediate" | "final"
}) {
  if (!workflowModel.value || !flowNodes.value) {
    return
  }

  const { id, type } = requestPayload

  const targetNode = flowNodes.value.find(it => it.id === id)
  if (!targetNode) {
    return
  }

  let payload
  if (type === "intermediate") {
    status.value = WorkflowStatus.PHASED_CONCLUSION
    payload = getPayload(WorkflowStatus.PHASED_CONCLUSION)
    // TODO: allow regenerate conclusion
  }
  else if (type === "final") {
    status.value = WorkflowStatus.FINAL_CONCLUSION
    payload = getPayload(WorkflowStatus.FINAL_CONCLUSION)
  }

  if (!payload) {
    return
  }

  try {
    if (type === "intermediate") {
      loadingRecord.getInterMediateConclusion = true
    }
    else if (type === "final") {
      loadingRecord.getFinalConclusion = true
    }

    const res = await postGenerateWorkflow(payload)

    if (res.data) {
      const {
        path_data: { steps: currSteps, path_status, final_research_conclusion },
      } = res.data
      status.value = path_status
      pathData.value = res.data.path_data

      if (type === "final") {
        // targetNode.finalConclusion = final_research_conclusion
        handleSetConclusion({ intermediate: "", final: final_research_conclusion || "", id, type, isGenerated: true })
        message.success("Generate final conclusion successfully")
      }
      else if (type === "intermediate") {
        const target = currSteps.findLast(
          ({ step }) =>
            step
            === (type === "intermediate"
              ? WorkflowStep.ADD_PHASED_RESEARCH_CONCLUSION
              : WorkflowStep.ADD_FINAL_RESEARCH_CONCLUSION),
        )
        if (target?.data) {
          handleSetConclusion({
            intermediate: target.data.conclusion || "",
            final: "",
            id,
            type,
            isGenerated: true,
          })
        }
        message.success("Generate intermediate conclusion successfully")
      }
    }
  }
  catch (e) {
    //
  }
  finally {
    loadingRecord.getFinalConclusion = false
    loadingRecord.getInterMediateConclusion = false
  }
}

function handleAddNextRN(researchNode: ProtocolModels.ProjectProtocolInfo) {
  if (!workflowData.value || !flowNodes.value || !workflowNodes.value) {
    message.error("No workflow found")
    return
  }

  if (!researchNode) {
    message.error("No protocol selected")
    return
  }

  const { uid } = researchNode
  const airalogyProtocolId = researchNode.airalogy_id
    ? getRealAiralogyId(researchNode)
    : uid

  const id = nanoid()

  flowNodes.value.push({
    airalogy_protocol_id: airalogyProtocolId,
    status: "init",
    type: "manual",
    id,
    initialValue: [],
    node: workflowNodes.value.find(({ id }) => id === airalogyProtocolId || id === uid) || null,
  })

  hideManualResearchNode()
}

function handleEndConclusion(payload: {
  final: string
  id?: string
  type: "intermediate" | "final" | "both"
}) {
  if (!workflowModel.value) {
    message.error("No model found")
    return
  }
  const { final, id, type } = payload
  if (!id) {
    message.error("No node selected")
    return
  }
  if (!final && type !== "final") {
    message.error("Final conclusion is empty")
    return
  }

  handleSetConclusion({ ...payload, intermediate: "" })
}

function handleSetConclusion(payload: {
  final: string
  intermediate: string
  id?: string
  type: "intermediate" | "final" | "both"
  isGenerated?: boolean
}) {
  if (!workflowModel.value) {
    message.error("No model found")
    return
  }

  if (!flowNodes.value) {
    message.error("No nodes found")
    return
  }

  // const { node, data } = intermediateData.value
  const { intermediate, final, id, type, isGenerated } = payload
  if (
    (type === "intermediate" && !intermediate)
    || (type === "final" && !final)
    || (type === "both" && !intermediate && !final)
  ) {
    message.error("Conclusion is empty")
    return
  }

  let successMessage = ""
  if (id && (type === "intermediate" || type === "both")) {
    const target = workflowModel.value.record[id]
    const targetNodeIndex = flowNodes.value.findIndex(node => node.id === id)
    if (targetNodeIndex === -1) {
      message.error("No node found")
      return
    }

    const targetNode = flowNodes.value[targetNodeIndex]

    if (intermediate && target) {
      target.conclusion = intermediate
      target.status = "done"
      targetNode.status = "done"
      target.isConclusionGenerated = isGenerated || false

      successMessage = "Set intermediate conclusion successfully"
    }

    handleAddRecordStep(targetNode, targetNodeIndex)
  }

  if (type === "final" || type === "both") {
    if (final) {
      workflowModel.value.finalResearchConclusion = final

      if (successMessage) {
        successMessage = "Set final conclusion and intermediate conclusion successfully"
      }
      else {
        successMessage = "Set final conclusion successfully"
      }
    }
  }

  if (successMessage) {
    message.success(successMessage)
  }
  else if (id) {
    message.error("Conclusion is empty")
  }
  else {
    message.error("No node selected")
  }
}

function handleAddRecordStep(node: FlowNode, index: number) {
  if (!pathData.value?.steps || !workflowModel.value) {
    return
  }

  const { airalogy_protocol_id, type, id, node: rawNode, protocol_index } = node

  const recordData = workflowModel.value.record[id]?.data
  if (!recordData) {
    message.error("No record data found")
    return
  }

  const recordPayload = recordData as Record<string, any>
  const rawRecordData = recordPayload.data && typeof recordPayload.data === "object"
    ? recordPayload.data
    : recordPayload
  const researchStep = rawRecordData.step || rawRecordData.research_step || {}
  const researchVariable = rawRecordData.var || rawRecordData.research_variable || {}
  const researchCheck = rawRecordData.check || rawRecordData.research_check || {}
  const researchResult = rawRecordData.result || rawRecordData.research_result || {}
  const report = recordPayload.report || rawRecordData.report || ""
  const airalogyRecordId = recordPayload.airalogy_record_id || recordPayload.airalogy_id || ""

  const stepItem: StepItem = {
    step: WorkflowStep.ADD_RECORD,
    path_index: index + 1,
    data: {
      airalogy_protocol_id,
      protocol_index: rawNode?.data?.sequence || protocol_index || null,
      airalogy_record_id: airalogyRecordId,
      record_data: airalogyRecordId
        ? recordPayload
        : {
            data: {
              step: researchStep,
              var: researchVariable,
              check: researchCheck,
              result: researchResult,
            },
            report,
          },
    },
  }

  node.record_id = airalogyRecordId || undefined

  let didApplyStep = false

  if (type === "generated" && recordData) {
    const targetStepIndex = pathData.value?.steps.findLastIndex(
      ({ step }) => step === WorkflowStep.ADD_INITIAL_VALUES_FOR_FIELDS_IN_NEXT_PROTOCOL,
    )
    if (targetStepIndex !== -1) {
      pathData.value.steps.splice(targetStepIndex, 1, stepItem)
      didApplyStep = true
    }
  }

  if (!didApplyStep) {
    pathData.value.steps.push(stepItem)
  }
}

async function handleEndWorkflow(node: FlowNode) {
  try {
    loadingRecord.complete = true
    status.value = WorkflowStatus.COMPLETED
    const payload = getPayload(WorkflowStatus.COMPLETED)
    if (!payload) {
      message.error("No payload found")
      return
    }

    const res = await postGenerateWorkflow(payload)

    if (res.data) {
      const {
        path_data: { final_research_conclusion },
      } = res.data

      message.success("Protocol workflow completed successfully")
      // const { path_data: { steps: resSteps } } = res.data
      if (workflowModel.value) {
        workflowModel.value.finalResearchConclusion = final_research_conclusion || ""
      }
      emit("update:workflow", res.data)
    }
  }
  catch (e) {
    //
  }
  finally {
    loadingRecord.complete = false
  }
}

const showFinalConclusion = ref(false)
function handleShowFinalConclusion(payload: { id: string, node?: SelectedNode | null }) {
  showFinalConclusion.value = true
}

const { data: channelData } = useBroadcastChannel({ name: `workflow-${workflowId.value}` })
const { id: instanceId } = inject<{ id: string }>("protocol-workflow-channel", { id: nanoid() })

watch(channelData, (val) => {
  if (typeof val !== "object") {
    return
  }

  const { action, id, source, data } = val as {
    action: string
    data: any
    id: string
    source: string
  }
  if (id === instanceId) {
    return
  }

  if (action === "showIntermediate") {
    const targetIndex = flowNodes.value ? flowNodes.value.findIndex(node => node.id === source) : -1

    if (!flowNodes.value || targetIndex === -1) {
      message.error("No target node found")
      return
    }

    const target = flowNodes.value[targetIndex]

    status.value = WorkflowStatus.PHASED_CONCLUSION
    showConclusion.value = true
    selectedResearchNode.value = {
      ...target,
      name: `Input conclusion of ${target.name}`,
      field: data,
      isEnd: targetIndex === flowNodes.value.length - 1,
    }
    target.status = "conclusion"

    if (workflowModel.value?.record?.[source]) {
      workflowModel.value.record[source].status = "conclusion"
      workflowModel.value.record[source].data = data
    }
    else if (workflowModel.value) {
      workflowModel.value.record[source] = {
        data,
        status: "conclusion",
        id: source,
        conclusion: "",
        isConclusionGenerated: false,
      }
    }
  }
})

watch(status, async (curr, prev) => {
  if (prev === WorkflowStatus.RESEARCH_STRATEGY) {
    if (curr === WorkflowStatus.NEXT_PROTOCOL) {
      // await handleSelectNextRN()
    }
    else if (curr === "end_after_generating_research_strategy") {
      message.warning("Failed to generate research strategy.Research unreachable.")
    }
  }
  else if (prev === WorkflowStatus.NEXT_PROTOCOL) {
    if (curr === WorkflowStatus.INITIAL_VALUES) {
      // await handleGenerateInitialValue()
    }
  }
  else if (prev === WorkflowStatus.INITIAL_VALUES) {
    if (curr === WorkflowStatus.RECORD) {
      // await handleRedirect()
    }
  }
})

const workflowQuery = useRouteQuery("workflow")
onMounted(() => {
  // 检查当前路由是否已经有这个查询参数
  // 如果没有，则更新 URL 并添加默认查询参数
  if (workflowId.value && !workflowQuery.value) {
    workflowQuery.value = workflowId.value
  }
})

function handleAISelectFromModal() {
  hideManualResearchNode()
  handleGenerateNextRN()
}

// watch(workflowModel, (val) => {
//   console.log(val)
// })
</script>

<style scoped lang="sass">
.reset-form
  :deep(.n-form-item-blank)
    flex-direction: row
:deep(.n-form-item-label__text)
  max-width: fit-content!important

// Add transition styles for modal
.modal-enter-active,
.modal-leave-active
  transition: opacity 0.3s ease

.modal-enter-from,
.modal-leave-to
  opacity: 0
</style>
