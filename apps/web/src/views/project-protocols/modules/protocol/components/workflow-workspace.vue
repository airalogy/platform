<template>
  <div v-if="workflowData" class="workflow-workspace p-6 space-y-6">
    <n-alert type="info" :show-icon="false">
      {{ $t("page.protocol.workflow.workspaceHint") }}
    </n-alert>

    <div class="grid gap-6 xl:grid-cols-[minmax(22rem,28rem)_minmax(0,1fr)]">
      <n-card :title="$t('page.protocol.workflow.structureTitle')" size="small">
        <template #header-extra>
          <n-tag size="small" round>
            {{ $t("page.protocol.workflow.protocolCount", { count: workflowData.protocols.length }) }}
          </n-tag>
        </template>

        <n-form label-placement="top">
          <n-form-item :label="$t('common.title')">
            <n-input
              v-model:value="workflowData.title"
              :disabled="props.readonly"
              :placeholder="$t('page.protocol.workflow.titlePlaceholder')"
            />
          </n-form-item>

          <n-form-item :label="$t('page.protocol.workflow.defaultGoalLabel')">
            <n-input
              v-model:value="workflowData.default_research_goal"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 4 }"
              :disabled="props.readonly"
              :placeholder="$t('page.protocol.workflow.defaultGoalPlaceholder')"
            />
          </n-form-item>

          <n-form-item :label="$t('page.protocol.workflow.defaultStrategyLabel')">
            <n-input
              v-model:value="workflowData.default_research_strategy"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 4 }"
              :disabled="props.readonly"
              :placeholder="$t('page.protocol.workflow.defaultStrategyPlaceholder')"
            />
          </n-form-item>

          <n-form-item :label="$t('page.protocol.workflow.logicLabel')">
            <n-input
              v-model:value="logicText"
              type="textarea"
              :autosize="{ minRows: 4, maxRows: 8 }"
              :disabled="props.readonly"
              :placeholder="$t('page.protocol.workflow.logicPlaceholder')"
            />
          </n-form-item>

          <div class="mb-4 flex flex-wrap gap-2">
            <n-select
              v-model:value="selectedProtocolUid"
              class="min-w-0 flex-1"
              filterable
              clearable
              :disabled="props.readonly"
              :placeholder="$t('page.protocol.workflow.selectProtocolPlaceholder')"
              :options="availableProtocolOptions"
            />
            <n-button
              type="primary"
              secondary
              :disabled="props.readonly || !selectedProtocolUid"
              @click="handleAddSelectedProtocol"
            >
              {{ $t("page.protocol.workflow.addProtocol") }}
            </n-button>
            <n-button
              tertiary
              :disabled="props.readonly || !currentProtocolOption"
              @click="handleAddCurrentProtocol"
            >
              {{ $t("page.protocol.workflow.addCurrentProtocol") }}
            </n-button>
          </div>

          <div class="space-y-2">
            <div
              v-for="(protocol, index) in workflowData.protocols"
              :key="protocol.airalogy_protocol_id"
              class="border border-gray-200 rounded-xl p-3"
            >
              <div class="mb-2 flex items-start gap-2">
                <n-tag type="info" size="small" round>
                  {{ $t("page.protocol.workflow.protocolIndex", { index: protocol.protocol_index }) }}
                </n-tag>
                <div class="min-w-0 flex-1">
                  <div class="truncate font-medium">
                    {{ protocol.protocol_name }}
                  </div>
                  <div class="truncate text-xs text-gray-500">
                    {{ protocol.airalogy_protocol_id }}
                  </div>
                </div>
                <div class="flex gap-1">
                  <n-button
                    quaternary
                    circle
                    size="small"
                    :disabled="props.readonly || index === 0"
                    @click="moveProtocol(index, -1)"
                  >
                    <template #icon>
                      <n-icon>
                        <icon-tabler-arrow-up />
                      </n-icon>
                    </template>
                  </n-button>
                  <n-button
                    quaternary
                    circle
                    size="small"
                    :disabled="props.readonly || index === workflowData.protocols.length - 1"
                    @click="moveProtocol(index, 1)"
                  >
                    <template #icon>
                      <n-icon>
                        <icon-tabler-arrow-down />
                      </n-icon>
                    </template>
                  </n-button>
                  <n-button
                    quaternary
                    circle
                    size="small"
                    type="error"
                    :disabled="props.readonly"
                    @click="removeProtocol(index)"
                  >
                    <template #icon>
                      <n-icon>
                        <icon-tabler-trash />
                      </n-icon>
                    </template>
                  </n-button>
                </div>
              </div>
            </div>

            <n-empty
              v-if="workflowData.protocols.length === 0"
              :description="$t('page.protocol.workflow.emptyProtocols')"
              size="small"
            />
          </div>

          <n-form-item class="mt-4" :label="$t('page.protocol.workflow.initialProtocolLabel')">
            <n-select
              v-model:value="workflowData.default_initial_protocol_index"
              :disabled="props.readonly || workflowData.protocols.length === 0"
              :options="initialProtocolOptions"
            />
          </n-form-item>

          <div class="mb-2 flex items-center justify-between">
            <span class="text-sm font-medium">{{ $t("page.protocol.workflow.edgesLabel") }}</span>
            <n-button
              tertiary
              size="small"
              :disabled="props.readonly || workflowData.protocols.length < 2"
              @click="addEdge"
            >
              {{ $t("common.add") }}
            </n-button>
          </div>

          <div class="space-y-2">
            <div
              v-for="(edge, index) in edgeRows"
              :key="`${index}-${edge.source}-${edge.target}`"
              class="flex items-center gap-2 border border-gray-200 rounded-xl p-3"
            >
              <n-select
                class="min-w-0 flex-1"
                :disabled="props.readonly"
                :value="edge.source"
                :options="initialProtocolOptions"
                @update:value="value => updateEdge(index, { source: value || null })"
              />
              <n-select
                class="w-28"
                :disabled="props.readonly"
                :value="edge.operator"
                :options="edgeOperatorOptions"
                @update:value="value => updateEdge(index, { operator: value || '->' })"
              />
              <n-select
                class="min-w-0 flex-1"
                :disabled="props.readonly"
                :value="edge.target"
                :options="initialProtocolOptions"
                @update:value="value => updateEdge(index, { target: value || null })"
              />
              <n-button
                quaternary
                circle
                size="small"
                type="error"
                :disabled="props.readonly"
                @click="removeEdge(index)"
              >
                <template #icon>
                  <n-icon>
                    <icon-tabler-trash />
                  </n-icon>
                </template>
              </n-button>
            </div>

            <n-empty
              v-if="edgeRows.length === 0"
              :description="$t('page.protocol.workflow.emptyEdges')"
              size="small"
            />
          </div>
        </n-form>
      </n-card>

      <div class="space-y-6">
        <n-card :title="$t('page.protocol.workflow.runtimeTitle')" size="small">
          <template #header-extra>
            <n-button
              tertiary
              size="small"
              :disabled="props.readonly"
              @click="resetWorkflowRuntime(true)"
            >
              {{ $t("page.protocol.workflow.resetRuntime") }}
            </n-button>
          </template>

          <div v-if="workflowData.protocols.length > 0" class="space-y-6">
            <chain-wrapper
              :id="props.workflowId"
              :uid="protocolUid || workflowData.id"
              :name="workflowData.title"
              mode="edit"
            />

            <protocol-workflow :workflow-id="props.workflowId" />
          </div>
          <n-empty
            v-else
            :description="$t('page.protocol.workflow.runtimeEmpty')"
            size="small"
          />
        </n-card>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { FlowNode, WorkflowModel } from "@/store/modules/workflow"
import type { IProtocolWorkflow, PathData, WorkflowProtocolNode } from "@/types/workflow"
import type { ProtocolModels } from "@airalogy/shared/types"
import ChainWrapper from "@/components/chain/chain-wrapper.vue"
import ProtocolWorkflow from "@/components/chain/protocol-workflow.vue"
import { WorkflowStatus, WorkflowStep } from "@/enum/workflow"
import { fetchProtocols } from "@/service/api/project-protocols"
import { getWorkflow as fetchWorkflow } from "@/service/api/workflow"
import { useProtocolWorkflowStore } from "@/store/modules/workflow"
import { splitWorkflowEdge } from "@/utils/workflow"
import { useProtocolInfoStore } from "@/views/project-protocols/hooks/useProtocolInfoStore"
import { useClosableMessage } from "@airalogy/composables"
import { getRealAiralogyId } from "@airalogy/shared/utils/parseAiralogyId"
import { useI18n } from "vue-i18n"

interface Props {
  workflowId: string
  readonly?: boolean
}

interface WorkflowEdgeRow {
  operator: "->" | "<->"
  source: null | number
  target: null | number
}

const props = withDefaults(defineProps<Props>(), {
  readonly: false,
})

const { t } = useI18n()
const message = useClosableMessage()
const workflowStore = useProtocolWorkflowStore()
const { protocolInfo, protocolUid } = useProtocolInfoStore()!

const selectedProtocolUid = ref<string | null>(null)
const protocolCatalog = ref<ProtocolModels.ProjectProtocolInfo[]>([])
const remoteWorkflowLoadAttempted = ref(false)

const workflowInfo = computed(() => workflowStore.getWorkflow(props.workflowId))
const workflowData = computed({
  get: () => workflowInfo.value?.data,
  set: (value) => {
    workflowStore.setData(props.workflowId, value)
  },
})

const currentProtocolOption = computed(() => {
  if (!protocolInfo.value?.uid) {
    return null
  }

  return protocolInfo.value
})

function getWorkflowProtocolId(protocol: ProtocolModels.ProjectProtocolInfo) {
  if (protocol.airalogy_id) {
    return getRealAiralogyId(protocol)
  }

  return protocol.uid
}

function protocolMatchesWorkflowId(protocol: ProtocolModels.ProjectProtocolInfo, id?: string | null) {
  if (!id) {
    return false
  }

  return protocol.uid === id
    || protocol.airalogy_id === id
    || getWorkflowProtocolId(protocol) === id
}

const availableProtocolOptions = computed(() => {
  const selectedIds = new Set((workflowData.value?.protocols || []).map(protocol => protocol.airalogy_protocol_id))

  return protocolCatalog.value
    .filter(protocol =>
      !selectedIds.has(protocol.uid)
      && !selectedIds.has(protocol.airalogy_id)
      && !selectedIds.has(getWorkflowProtocolId(protocol)),
    )
    .map(protocol => ({
      label: `${protocol.name} (${protocol.uid})`,
      value: protocol.uid,
    }))
})

const initialProtocolOptions = computed(() =>
  (workflowData.value?.protocols || []).map(protocol => ({
    label: `${protocol.protocol_index}. ${protocol.protocol_name}`,
    value: protocol.protocol_index,
  })),
)

const edgeOperatorOptions: Array<{ label: string, value: WorkflowEdgeRow["operator"] }> = [
  { label: "->", value: "->" },
  { label: "<->", value: "<->" },
]

const edgeRows = computed<WorkflowEdgeRow[]>(() =>
  (workflowData.value?.edges || []).map((edge) => {
    const parsed = splitWorkflowEdge(edge)

    return {
      source: parsed ? Number(parsed.source) || null : null,
      target: parsed ? Number(parsed.target) || null : null,
      operator: parsed?.operator === "<->" ? "<->" : "->",
    }
  }),
)

const logicText = computed({
  get: () => {
    if (!workflowData.value) {
      return ""
    }

    return Array.isArray(workflowData.value.logic)
      ? workflowData.value.logic.join("\n")
      : workflowData.value.logic || ""
  },
  set: (value: string) => {
    if (!workflowData.value) {
      return
    }

    workflowData.value = {
      ...workflowData.value,
      logic: value,
    }
  },
})

function createDefaultWorkflow(): IProtocolWorkflow {
  const currentProtocol = currentProtocolOption.value
  const defaultProtocols = currentProtocol
    ? [{
        protocol_index: 1,
        protocol_name: currentProtocol.name,
        airalogy_protocol_id: getWorkflowProtocolId(currentProtocol),
      }]
    : []

  return {
    id: props.workflowId,
    title: currentProtocol ? `${currentProtocol.name} Workflow` : "Workflow",
    protocols: defaultProtocols,
    edges: [],
    logic: "",
    default_research_goal: null,
    default_research_strategy: null,
    default_initial_protocol_index: defaultProtocols.length > 0 ? 1 : null,
  }
}

function getDefaultModel() {
  return {
    goal: workflowData.value?.default_research_goal || "",
    strategy: workflowData.value?.default_research_strategy || "",
    researchable: undefined,
    finalResearchConclusion: "",
    record: {},
  }
}

function buildRestoredRuntime(pathData: PathData) {
  const flowNodes: FlowNode[] = []
  const record: WorkflowModel["record"] = {}
  const nodeById = new Map<string, FlowNode>()

  function getNodeId(data: Record<string, any>, index: number) {
    return data.id || `${data.airalogy_protocol_id || "workflow-node"}-${index}`
  }

  function findNode(data: Record<string, any>) {
    if (data.id && nodeById.has(data.id)) {
      return nodeById.get(data.id)!
    }

    const airalogyProtocolId = data.airalogy_protocol_id
    if (!airalogyProtocolId) {
      return null
    }

    for (let index = flowNodes.length - 1; index >= 0; index -= 1) {
      if (flowNodes[index].airalogy_protocol_id === airalogyProtocolId) {
        return flowNodes[index]
      }
    }

    return null
  }

  function upsertNode(data: Record<string, any>, index: number, type: FlowNode["type"]) {
    const existing = findNode(data)
    if (existing) {
      return existing
    }

    const id = getNodeId(data, index)
    const node: FlowNode = {
      ...data,
      id,
      airalogy_protocol_id: data.airalogy_protocol_id || "",
      protocol_index: data.protocol_index || null,
      node: null,
      initialValue: null,
      status: "init",
      type,
    }
    flowNodes.push(node)
    nodeById.set(id, node)
    return node
  }

  pathData.steps.forEach((step, index) => {
    const data = step.data || {}

    if (step.step === WorkflowStep.ADD_NEXT_PROTOCOL) {
      upsertNode(data, index, step.mode === "user" ? "manual" : "generated")
      return
    }

    if (step.step === WorkflowStep.ADD_INITIAL_VALUES_FOR_FIELDS_IN_NEXT_PROTOCOL) {
      const node = upsertNode(data, index, "generated")
      node.initialValue = data.values || null
      node.status = "generated"
      return
    }

    if (step.step === WorkflowStep.ADD_RECORD) {
      const node = upsertNode(data, index, step.mode === "ai" ? "generated" : "manual")
      const recordData = data.record_data || {}
      node.record_id = data.airalogy_record_id || recordData.airalogy_record_id || recordData.airalogy_id || undefined
      node.status = "conclusion"
      record[node.id] = {
        data: recordData,
        status: node.status,
        initialValue: node.initialValue,
        conclusion: record[node.id]?.conclusion || "",
        isConclusionGenerated: record[node.id]?.isConclusionGenerated || false,
        id: node.record_id,
      }
      return
    }

    if (step.step === WorkflowStep.ADD_PHASED_RESEARCH_CONCLUSION) {
      const node = findNode(data) || flowNodes[flowNodes.length - 1]
      if (!node) {
        return
      }
      node.status = "done"
      node.intermediateConclusion = data.conclusion || ""
      record[node.id] = {
        data: record[node.id]?.data || null,
        status: "done",
        initialValue: node.initialValue,
        conclusion: data.conclusion || "",
        isConclusionGenerated: step.mode !== "user",
        id: record[node.id]?.id || node.record_id,
      }
    }
  })

  return { flowNodes, record }
}

async function loadPersistedWorkflow() {
  if (workflowData.value || remoteWorkflowLoadAttempted.value || !props.workflowId) {
    return false
  }

  remoteWorkflowLoadAttempted.value = true
  const { data } = await fetchWorkflow(props.workflowId, false)
  if (!data) {
    return false
  }

  const goalStep = data.path_data.steps.findLast(step => step.step === "add_research_goal")
  const strategyStep = data.path_data.steps.findLast(step => step.step === "add_research_strategy")
  const { flowNodes, record } = buildRestoredRuntime(data.path_data)

  workflowStore.setData(props.workflowId, data.workflow_info)
  workflowStore.setPath(props.workflowId, data.path_data)
  workflowStore.setFlowNodes(props.workflowId, flowNodes)
  workflowStore.setModel(props.workflowId, {
    goal: goalStep?.data?.goal || data.workflow_info.default_research_goal || "",
    strategy: strategyStep?.data?.strategy || data.workflow_info.default_research_strategy || "",
    researchable: data.path_data.researchable,
    finalResearchConclusion: data.path_data.final_research_conclusion || "",
    record,
  })

  return true
}

function resetWorkflowRuntime(syncDefaults = false) {
  const currentModel = workflowInfo.value?.model

  workflowStore.setFlowNodes(props.workflowId, [])
  workflowStore.setPath(props.workflowId, {
    path_status: WorkflowStatus.RESEARCH_GOAL,
    researchable: false,
    steps: [],
  })
  workflowStore.setModel(props.workflowId, {
    ...getDefaultModel(),
    goal: syncDefaults
      ? workflowData.value?.default_research_goal || ""
      : currentModel?.goal || workflowData.value?.default_research_goal || "",
    strategy: syncDefaults
      ? workflowData.value?.default_research_strategy || ""
      : currentModel?.strategy || workflowData.value?.default_research_strategy || "",
  })
}

async function ensureWorkflowState() {
  if (await loadPersistedWorkflow()) {
    return
  }

  if (!workflowData.value) {
    workflowData.value = createDefaultWorkflow()
  }
  else if (
    workflowData.value.protocols.length === 0
    && currentProtocolOption.value
  ) {
    workflowData.value = createDefaultWorkflow()
  }

  if (!workflowInfo.value?.model) {
    workflowStore.setModel(props.workflowId, getDefaultModel())
  }
}

function remapEdges(
  edges: IProtocolWorkflow["edges"],
  oldProtocols: WorkflowProtocolNode[],
  nextProtocols: WorkflowProtocolNode[],
) {
  const oldProtocolIdByIndex = new Map(oldProtocols.map(protocol => [protocol.protocol_index, protocol.airalogy_protocol_id]))
  const nextProtocolIndexById = new Map(nextProtocols.map(protocol => [protocol.airalogy_protocol_id, protocol.protocol_index]))

  return edges.flatMap((edge) => {
    const parsed = splitWorkflowEdge(edge)
    if (!parsed) {
      return []
    }

    const sourceId = oldProtocolIdByIndex.get(Number(parsed.source))
    const targetId = oldProtocolIdByIndex.get(Number(parsed.target))

    if (!sourceId || !targetId) {
      return []
    }

    const sourceIndex = nextProtocolIndexById.get(sourceId)
    const targetIndex = nextProtocolIndexById.get(targetId)

    if (!sourceIndex || !targetIndex) {
      return []
    }

    return [`${sourceIndex} ${parsed.operator} ${targetIndex}` as IProtocolWorkflow["edges"][number]]
  })
}

function remapDefaultInitialProtocolIndex(
  oldProtocols: WorkflowProtocolNode[],
  nextProtocols: WorkflowProtocolNode[],
  currentDefaultIndex?: number | null,
) {
  const defaultProtocolId = oldProtocols.find(protocol => protocol.protocol_index === currentDefaultIndex)?.airalogy_protocol_id

  if (!defaultProtocolId) {
    return nextProtocols[0]?.protocol_index || null
  }

  return nextProtocols.find(protocol => protocol.airalogy_protocol_id === defaultProtocolId)?.protocol_index
    || nextProtocols[0]?.protocol_index
    || null
}

function commitProtocols(protocols: WorkflowProtocolNode[]) {
  if (!workflowData.value) {
    return
  }

  const oldProtocols = workflowData.value.protocols || []
  const nextProtocols = protocols.map((protocol, index) => ({
    ...protocol,
    protocol_index: index + 1,
  }))

  workflowData.value = {
    ...workflowData.value,
    protocols: nextProtocols,
    edges: remapEdges(workflowData.value.edges || [], oldProtocols, nextProtocols),
    default_initial_protocol_index: remapDefaultInitialProtocolIndex(
      oldProtocols,
      nextProtocols,
      workflowData.value.default_initial_protocol_index,
    ),
  }

  resetWorkflowRuntime()
}

function handleAddProtocol(protocol: ProtocolModels.ProjectProtocolInfo) {
  if (!workflowData.value) {
    return
  }

  if (workflowData.value.protocols.some(item => protocolMatchesWorkflowId(protocol, item.airalogy_protocol_id))) {
    message.warning(t("page.protocol.workflow.protocolAlreadyAdded"))
    return
  }

  commitProtocols([
    ...workflowData.value.protocols,
    {
      protocol_index: workflowData.value.protocols.length + 1,
      protocol_name: protocol.name,
      airalogy_protocol_id: getWorkflowProtocolId(protocol),
    },
  ])
}

function handleAddSelectedProtocol() {
  if (!selectedProtocolUid.value) {
    return
  }

  const protocol = protocolCatalog.value.find(item =>
    item.uid === selectedProtocolUid.value
    || protocolMatchesWorkflowId(item, selectedProtocolUid.value),
  )
  if (!protocol) {
    return
  }

  handleAddProtocol(protocol)
  selectedProtocolUid.value = null
}

function handleAddCurrentProtocol() {
  if (!currentProtocolOption.value) {
    return
  }

  handleAddProtocol(currentProtocolOption.value)
}

function moveProtocol(index: number, delta: number) {
  if (!workflowData.value) {
    return
  }

  const nextIndex = index + delta
  if (nextIndex < 0 || nextIndex >= workflowData.value.protocols.length) {
    return
  }

  const nextProtocols = [...workflowData.value.protocols]
  const [protocol] = nextProtocols.splice(index, 1)
  nextProtocols.splice(nextIndex, 0, protocol)
  commitProtocols(nextProtocols)
}

function removeProtocol(index: number) {
  if (!workflowData.value) {
    return
  }

  const nextProtocols = workflowData.value.protocols.filter((_, targetIndex) => targetIndex !== index)
  commitProtocols(nextProtocols)
}

function commitEdges(rows: WorkflowEdgeRow[]) {
  if (!workflowData.value) {
    return
  }

  workflowData.value = {
    ...workflowData.value,
    edges: rows.flatMap((row) => {
      if (!row.source || !row.target || row.source === row.target) {
        return []
      }

      return [`${row.source} ${row.operator} ${row.target}` as IProtocolWorkflow["edges"][number]]
    }),
  }

  resetWorkflowRuntime()
}

function addEdge() {
  const protocols = workflowData.value?.protocols || []
  if (protocols.length < 2) {
    return
  }

  commitEdges([
    ...edgeRows.value,
    {
      source: protocols[0]?.protocol_index || null,
      target: protocols[1]?.protocol_index || null,
      operator: "->",
    },
  ])
}

function updateEdge(index: number, patch: Partial<WorkflowEdgeRow>) {
  const rows = [...edgeRows.value]
  rows[index] = {
    ...rows[index],
    ...patch,
  }
  commitEdges(rows)
}

function removeEdge(index: number) {
  const rows = [...edgeRows.value]
  rows.splice(index, 1)
  commitEdges(rows)
}

async function fetchProjectProtocols() {
  if (!protocolInfo.value?.project_id) {
    protocolCatalog.value = currentProtocolOption.value ? [currentProtocolOption.value] : []
    syncWorkflowProtocolIds()
    return
  }

  const { data } = await fetchProtocols({
    projectId: protocolInfo.value.project_id,
    page: 1,
    pageSize: 9999,
  })

  const protocols = data?.protocols || []

  if (
    currentProtocolOption.value
    && protocols.findIndex(protocol => protocol.uid === currentProtocolOption.value?.uid) === -1
  ) {
    protocolCatalog.value = [currentProtocolOption.value, ...protocols]
    syncWorkflowProtocolIds()
    return
  }

  protocolCatalog.value = protocols
  syncWorkflowProtocolIds()
}

function syncWorkflowProtocolIds() {
  if (!workflowData.value || protocolCatalog.value.length === 0) {
    return
  }

  let changed = false
  const protocols = workflowData.value.protocols.map((workflowProtocol) => {
    const protocol = protocolCatalog.value.find(item =>
      protocolMatchesWorkflowId(item, workflowProtocol.airalogy_protocol_id),
    )
    if (!protocol) {
      return workflowProtocol
    }

    const airalogyProtocolId = getWorkflowProtocolId(protocol)
    if (airalogyProtocolId === workflowProtocol.airalogy_protocol_id) {
      return workflowProtocol
    }

    changed = true
    return {
      ...workflowProtocol,
      protocol_name: workflowProtocol.protocol_name || protocol.name,
      airalogy_protocol_id: airalogyProtocolId,
    }
  })

  if (changed) {
    workflowData.value = {
      ...workflowData.value,
      protocols,
    }
  }
}

watch(
  () => protocolInfo.value?.project_id,
  async () => {
    await ensureWorkflowState()
    await fetchProjectProtocols()
  },
  { immediate: true },
)

watch(
  () => [workflowData.value?.default_research_goal, workflowData.value?.default_research_strategy],
  ([goal, strategy]) => {
    const model = workflowInfo.value?.model
    if (!model) {
      return
    }

    if (!model.goal && goal) {
      model.goal = goal
    }

    if (!model.strategy && strategy) {
      model.strategy = strategy
    }
  },
  { immediate: true },
)

watch(
  () => workflowData.value?.default_initial_protocol_index,
  (value, previousValue) => {
    if (previousValue !== undefined && value !== previousValue) {
      resetWorkflowRuntime()
    }
  },
)
</script>

<style scoped lang="sass">
.workflow-workspace
  :deep(.n-card-header)
    align-items: center
</style>
