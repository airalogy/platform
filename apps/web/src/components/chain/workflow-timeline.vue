<template>
  <div class="flex flex-col">
    <flow-node-box
      v-for="(item, index) in flowNode" :key="index" class="mb-3" :item="item" :is-start="index === 0"
      :is-end="index === flowNodes.length - 1" :model="model" @action:generate-initial-values="handleGetInitialValues"
      @action:delete="handleDelete" @action:show-report="handleShowReport" @action:add-record="handleAddRecord"
      @action:redo-record="handleRedoRecord" @action:set-intermediate-conclusion="handleSetIntermediateConclusion"
      @action:show-intermediate-conclusion="handleShowIntermediateConclusion"
      @action:show-initial-values="handleShowInitialValues" @action:end-workflow="handleEndWorkflow"
      @action:generate-conclusion="payload => emit('action:generate-conclusion', payload)"
    />

    <show-report-modal :record="currentRecordData" :title="reportTitle" @update:show="handleUpdateShow" />

    <!-- <div class="mt-4 space-y-2">
      <template v-for="node in flowNode" :key="node.id">
        <conclusion-modal
          v-if="nodeConclusions[node.id]" :node="{
            ...node,
            name: `Conclusion for protocol ${node.airalogy_protocol_id}${node.node?.data?.sequence ? ` (Protocol #${node.node.data.sequence})` : ''}`,
          }" :workflow-model="model" :show="nodeConclusions[node.id].showModal" @action:generate-conclusion="payload =>
            $emit('action:generate-conclusion', {
              type: payload.type,
              id: node.id,
              node: payload.node,
            })
          " @action:end-workflow="() => handleConclusionConfirm(node)"
          @action:set-conclusion="() => handleConclusionConfirm(node)"
        />
      </template>

    </div> -->

    <conclusion-modal
      v-if="showFinalConclusion"
      :editor-only="true"
      :node="{ id: 'final', isEnd: true, readonly: false, name: 'Final Research Conclusion', conclusionType: 'final', status: 'pending', type: 'manual', node: null, initialValue: null }"
      :show="showFinalConclusion" :workflow-model="model" @action:generate-conclusion=" $emit('action:generate-conclusion', { type: 'final', id: 'final', node: null })" @action:end-workflow="handleFinalConclusion" @action:set-conclusion="handleFinalConclusion"
    />
    <tooltip-button
      v-else-if="!isWorkflowEnded"
      :tooltip="couldAddNewNode ? 'Select next protocol' : 'Complete previous record first'" type="primary"
      :icon-props="{ size: 28 }" :icon="IconIonAdd" :disabled="!couldAddNewNode"
      :button-props="{ quaternary: true, size: 'large' }" @click="handleAddFlowNode"
    />
    <n-tag v-else type="success" class="ml-3" size="large">
      <template #icon>
        <n-icon>
          <icon-ion-checkmark-circle />
        </n-icon>
      </template>
      Workflow Ended
    </n-tag>
  </div>
</template>

<script setup lang="tsx">
import type { FlowNode, SelectedNode, WorkflowModel } from "@/store/modules/workflow"
import type { StepItem } from "@/types/workflow"
import type { ProtocolModels } from "@airalogy/shared/types"

import type { Node } from "@vue-flow/core"
import { useOpenNewTab } from "@/composables"
import ShowReportModal from "@/views/project-protocols/modules/show-report-modal.vue"
import { useClosableMessage } from "@airalogy/composables"
import IconIonAdd from "~icons/ion/add"
// import { IconIonCheckmarkCircle } from "@vicons/ionicons5"
import IconIonCheckmarkCircle from "~icons/ion/checkmark-circle"
import { useDialog } from "naive-ui"
import { nanoid } from "nanoid"
import FlowNodeBox from "./flow-node-box.vue"

interface IProps {
  selectedResearchNode?: SelectedNode | null
  steps: StepItem[]
  workflowNodes: Node[]
  workflowModel: WorkflowModel
  flowNodes: FlowNode[]
  showIntermediate: boolean
  showInitialValues: boolean
}

const props = withDefaults(defineProps<IProps>(), {
  selectedResearchNode: undefined,
  steps: () => [],
  nodesInfo: () => [],
})

const emit = defineEmits<IEmits>()

interface IEmits {
  (e: "update:selectedResearchNode", value: any): void
  (e: "update:history", value: any): void
  (e: "update:workflowModel", value: any): void
  (e: "update:flowNode", value: any): void
  (e: "select:next-research-node"): void
  (e: "generate:initial-values", item: FlowNode): void
  (e: "action:end-workflow", item: FlowNode): void
  (
    e: "action:set-conclusion",
    payload: { type: string, id: string, intermediate: string, final: string },
  ): void
  (e: "action:generate-conclusion",
    payload: { type: "intermediate" | "final", id: string, node?: SelectedNode | null },
  ): void
}

const selectedResearchNode = useVModel(props, "selectedResearchNode", emit)
const model = useVModel(props, "workflowModel", emit, {
  defaultValue: { record: {}, finalResearchConclusion: "", goal: "", strategy: "" },
})
const flowNode = useVModel(props, "flowNodes", emit, { defaultValue: [] })

const showIntermediate = useVModel(props, "showIntermediate")
const showInitialValues = useVModel(props, "showInitialValues")

const message = useClosableMessage()
const { workflowId } = inject<{ workflowId: Ref<string> }>("protocol-workflow", {
  workflowId: ref(nanoid()),
})

const couldAddNewNode = computed(() => {
  return flowNode.value.every(it => it.status === "done")
})

const { openNewTab } = useOpenNewTab()
function handleGetInitialValues(node: FlowNode) {
  if (!node) {
    selectedResearchNode.value = null
    return
  }
  const { id, initialValue, status, type } = node

  selectedResearchNode.value = null

  if (initialValue) {
    const targetNode = flowNode.value.find(it => it.id === id)
    if (targetNode) {
      targetNode.initialValue = null
    }
    const targetModel = model.value.record[id]
    if (targetModel) {
      targetModel.status = "generated"
      targetModel.initialValue = null
    }
  }

  emit("generate:initial-values", node)
  // selectedResearchNode.value = {
  //   ...node,
  //   name: `Using initial values for Research Protocol ${node.airalogy_protocol_id}?`,
  //   field: { research_variable: initialValue },
  // }
}

function handleContinue(node: FlowNode) {
  if (!node) {
    selectedResearchNode.value = null
    return
  }
  const { airalogy_protocol_id, initialValue, status, node: rawNode } = node

  if (status === "init") {
    if (!rawNode) {
      message.error("No node found")
      return
    }

    const { id } = rawNode.data.target as ProtocolModels.ProjectProtocolInfo

    openNewTab({
      name: "add-protocol-record-from-workflow",
      params: { protocolId: id },
      query: {
        protocol: id,
        target: node.id,
        chain: workflowId.value,
      },
    })
  }
  if (status === "generated") {
    if (!initialValue) {
      selectedResearchNode.value = null
      message.loading("Waiting for protocol recommendation")
      return
    }
    selectedResearchNode.value = {
      ...node,
      name: `Using initial values for Research Protocol ${airalogy_protocol_id}?`,
      field: { var: initialValue },
    }
  }
}
function handleDelete(node: FlowNode) {
  const { id, airalogy_protocol_id } = node
  const targetIndex = flowNode.value.findIndex(it => it.id === id)

  if (targetIndex === -1) {
    message.error("No target node found")
  }
  else {
    flowNode.value.splice(targetIndex, 1)
    const sequence = node.node?.data?.sequence
    if (sequence) {
      message.success(`Remove protocol ${airalogy_protocol_id} (Protocol #${sequence}) from workflow`)
    }
    else {
      message.success(`Remove protocol ${airalogy_protocol_id} from workflow`)
    }
  }

  model.value.record[id] = { data: {}, status: "deleted", conclusion: "", id, isConclusionGenerated: false }
}

interface NodeConclusions {
  [nodeId: string]: ConclusionState
}

// Add new state management
const nodeConclusions = ref<NodeConclusions>({})

function handleSetIntermediateConclusion(node: FlowNode) {
  const { id } = node
  initNodeConclusion(id)
  nodeConclusions.value[id].showModal = true
  const targetNode = flowNode.value.find(it => it.id === id)
  if (targetNode) {
    targetNode.status = "done"
  }
  selectedResearchNode.value = {
    ...node,
    name: `Set conclusion for protocol ${node.airalogy_protocol_id}${node.node?.data?.sequence ? ` (Protocol #${node.node.data.sequence})` : ""}`,
  }
}

function handleShowIntermediateConclusion(node: FlowNode) {
  const { id } = node
  initNodeConclusion(id)
  nodeConclusions.value[id].showModal = true
  selectedResearchNode.value = {
    ...node,
    name: `View conclusion for protocol ${node.airalogy_protocol_id}${node.node?.data?.sequence ? ` (Protocol #${node.node.data.sequence})` : ""}`,
    hideAIButton: true,
  }
}

function handleShowFinalConclusion(node?: FlowNode) {
  if (!node) {
    // Handle button click case
    const lastNode = flowNode.value[flowNode.value.length - 1]
    if (lastNode) {
      handleShowFinalConclusion(lastNode)
    }
    return
  }

  const { id } = node
  initNodeConclusion(id)
  nodeConclusions.value[id].showModal = true
  selectedResearchNode.value = {
    ...node,
    isEnd: true,
    readonly: true,
    name: "Final conclusion for workflow",
    conclusionType: "final",
  } as SelectedNode
}

function handleShowInitialValues(node: FlowNode) {
  showInitialValues.value = true

  selectedResearchNode.value = {
    ...node,
    name: `Initial values for Research Protocol ${node.airalogy_protocol_id}`,
    field: node.initialValue ? { var: node.initialValue } : {},
  }
}

const dialog = useDialog()

function handleAddRecord(node: FlowNode) {
  if (!node) {
    message.error("No node selected")
    return
  }

  const { node: rawNode } = node
  if (!rawNode) {
    message.error("No node found")
    return
  }

  const { uid, id, lab, project } = rawNode.data.target as ProtocolModels.ProjectProtocolInfo

  openNewTab({
    name: "add-protocol-record-from-workflow",
    params: { labUid: lab.uid, projectUid: project.uid, protocolUid: uid },
    query: {
      protocol: id,
      target: node.id,
      chain: workflowId.value,
    },
  })
}

function handleRedoRecord(node: FlowNode) {
  if (!node) {
    message.error("No node selected")
    return
  }

  dialog.warning({
    title: "Redo current research",
    content: "It will overwrite the current research record and conclusion",
    positiveText: "Continue",
    negativeText: "Cancel",
    onPositiveClick: () => {
      node.status = "init"
      node.initialValue = []
      model.value.record[node.id] = { data: {}, status: "init", conclusion: "", id: node.id, isConclusionGenerated: false }
    },
  })
}

function handleAddFlowNode() {
  emit("select:next-research-node")
}

// Add new state for final conclusion
const showFinalConclusion = ref(false)

// Update handleEndWorkflow function
function handleEndWorkflow(node: FlowNode) {
  const { id } = node
  const targetModel = model.value.record[id]
  if (!targetModel) {
    message.error("No target model found")
    return
  }

  if (targetModel.status === "done") {
    initNodeConclusion(id)
    if (model.value.finalResearchConclusion) {
      emit("action:end-workflow", node)
    }
    else if (!targetModel.conclusion) {
      handleShowIntermediateConclusion(node)
    }
    else {
      // showFinalConclusionForm.value = true
      // if (!nodeConclusions.value.final) {
      //   nodeConclusions.value.final = {
      //     showModal: true,
      //     showFinal: true,
      //     model: {
      //       intermediate: "",
      //       final: model.value.finalResearchConclusion || "",
      //     },
      //   }
      // }
      showFinalConclusion.value = true
    }
  }
  else {
    message.error("Protocol is not completed")
  }
}

const currentRecordData = ref<ProtocolModels.RecordInfo | null>(null)
const reportTitle = ref<string | undefined>(undefined)

function handleUpdateShow(show: boolean) {
  if (!show) {
    currentRecordData.value = null
  }
}

function handleShowReport(node: FlowNode) {
  const targetModel = model.value.record[node.id]
  if (!targetModel) {
    message.error("No target model found")
    return
  }

  currentRecordData.value = targetModel.data as ProtocolModels.RecordInfo
  const { sequence, label } = node.node?.data || {}

  if (sequence) {
    reportTitle.value = `Report of Protocol #${sequence}${label ? `(${label})` : ""}${node.unit_path_index ? `at index ${node.unit_path_index}` : ""}`
  }
  else {
    reportTitle.value = `Report of protocol ${node.airalogy_protocol_id}`
  }
}

// Add new interfaces for conclusion management
interface ConclusionState {
  showModal: boolean
  showFinal: boolean
  model: {
    intermediate: string
    final: string
  }
}
// Initialize conclusion state for a node
function initNodeConclusion(nodeId: string) {
  if (!nodeConclusions.value[nodeId]) {
    nodeConclusions.value[nodeId] = {
      showModal: true,
      showFinal: false,
      model: {
        intermediate: model.value.record[nodeId]?.conclusion || "",
        final: model.value.finalResearchConclusion || "",
      },
    }
  }
}

// Add handler for conclusion confirmation
function handleConclusionConfirm(node: FlowNode) {
  const { id } = node
  const conclusionState = nodeConclusions.value[id]

  if (!conclusionState)
    return

  const payload = {
    type: conclusionState.showFinal ? "final" : "intermediate",
    id,
    intermediate: conclusionState.model.intermediate,
    final: conclusionState.model.final,
  }

  if (conclusionState.showFinal) {
    // Update the model's finalResearchConclusion
    model.value = {
      ...model.value,
      finalResearchConclusion: conclusionState.model.final,
    }
    node.status = "done"
    if (model.value.record[id]) {
      model.value.record[id].status = "done"
    }
    emit("action:end-workflow", node)
  }
  else {
    emit("action:set-conclusion", payload)
  }

  conclusionState.showModal = false
}

// Update handleFinalConclusion function
function handleFinalConclusion(payload: {
  final: string
  intermediate: string
  id?: string
  type: "intermediate" | "final" | "both"
  node?: SelectedNode | null
}) {
  if (!payload)
    return

  model.value = {
    ...model.value,
    finalResearchConclusion: payload.final,
  }

  if (flowNode.value.length > 0) {
    const lastNode = flowNode.value[flowNode.value.length - 1]
    lastNode.status = "done"
    if (model.value.record[lastNode.id]) {
      model.value.record[lastNode.id].status = "done"
    }
  }

  emit("action:set-conclusion", {
    type: "final",
    id: "final",
    intermediate: "",
    final: payload.final,
  })

  message.success("Workflow ended successfully")
}

// Watch for changes in workflow model to update conclusions
watch(
  () => props.workflowModel,
  (newModel) => {
    if (newModel) {
      // Update all node conclusions
      Object.keys(newModel.record).forEach((nodeId) => {
        if (nodeConclusions.value[nodeId]) {
          nodeConclusions.value[nodeId].model.intermediate
            = newModel.record[nodeId]?.conclusion || ""
          nodeConclusions.value[nodeId].model.final = newModel.finalResearchConclusion || ""
        }
      })
      // Update final conclusion if exists
      if (nodeConclusions.value.final) {
        nodeConclusions.value.final.model.final = newModel.finalResearchConclusion || ""
      }
    }
  },
  { deep: true },
)

// Initialize conclusions for all nodes when they're added
watch(
  () => flowNode.value,
  (nodes) => {
    nodes.forEach((node) => {
      initNodeConclusion(node.id)
    })
  },
  { immediate: true },
)

// Add computed property for workflow ended state
const isWorkflowEnded = computed(() => {
  return (
    flowNode.value.length > 0
    && flowNode.value[flowNode.value.length - 1].status === "done"
    && model.value.finalResearchConclusion
  )
})
</script>
