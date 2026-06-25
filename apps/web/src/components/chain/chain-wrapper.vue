<template>
  <div v-if="workflowData" class="aimd-field aimd-field--no-style mb-2 flex items-center">
    <span class="aimd-field__scope aimd-field__scope--var self-stretch">{{ $t("common.var") }}</span>
    <insert-wbr :text="workflowData.id" class="aimd-field__name self-stretch rounded-br-2" />
    <div class="ml-2 text-lg font-bold">
      {{ workflowData?.title }}
    </div>
  </div>
  <div v-if="workflowNodes" class="group w-full">
    <vue-flow
      v-if="workflowNodes.length > 0"
      class="min-h-60 w-full"
      :nodes="workflowNodes"
      :edges="flowEdges"
      :apply-changes="false"
      :nodes-connectable="false"
      @pane-ready="resetTransform"
      @nodes-initialized="handleNode"
    >
      <template #edge-bidirectional="slotProps">
        <bidirectional-edge
          v-bind="(slotProps as any)"
          direction="bidirectional"
          :mode="props.mode"
        />
      </template>
      <template #node-in-out="{ data, ...slotProps }">
        <bidirectional-node
          v-bind="(slotProps as any)"
          direction="in-out"
          :data="data"
          :mode="props.mode"
          :store-id="props.id"
          @update:data="handleUpdateNode"
          @fork:node="handleFork"
          @update:layout="handleDebouncedUpdateNode"
        />
      </template>
      <template #node-bidirectional-input="{ data, ...slotProps }">
        <bidirectional-node
          v-bind="(slotProps as any)"
          direction="bidirectional-input"
          :data="data"
          slot-props
          :mode="props.mode"
          :store-id="props.id"
          @update:data="handleUpdateNode"
          @fork:node="handleFork"
          @update:layout="handleDebouncedUpdateNode"
        />
      </template>
      <template #node-bidirectional-output="{ data, ...slotProps }">
        <bidirectional-node
          v-bind="(slotProps as any)"
          direction="bidirectional-output"
          :data="data"
          :mode="props.mode"
          :store-id="props.id"
          @update:data="handleUpdateNode"
          @fork:node="handleFork"
          @update:layout="handleDebouncedUpdateNode"
        />
      </template>
      <template #node-single-input="{ data, ...slotProps }">
        <bidirectional-node
          v-bind="(slotProps as any)"
          direction="single-input"
          :data="data"
          :mode="props.mode"
          :store-id="props.id"
          @update:data="handleUpdateNode"
          @fork:node="handleFork"
          @update:layout="handleDebouncedUpdateNode"
        />
      </template>
      <template #node-single-output="{ data, ...slotProps }">
        <bidirectional-node
          v-bind="(slotProps as any)"
          direction="single-output"
          :data="data"
          :mode="props.mode"
          :store-id="props.id"
          @update:data="handleUpdateNode"
          @fork:node="handleFork"
          @update:layout="handleDebouncedUpdateNode"
        />
      </template>
      <!-- <template #connection-line="{ sourceX, sourceY, targetX, targetY }"> </template> -->
      <vue-panel
        position="bottom-right"
        class="opacity-20 transition-opacity group-hover:opacity-100"
      >
        <n-button @click="zoomIn()">
          <template #icon>
            <n-icon :component="ZoomInIcon" />
          </template>
        </n-button>
        <n-button class="mx-2" @click="resetTransform">
          <template #icon>
            <n-icon :component="RefreshIcon" />
          </template>
        </n-button>
        <n-button @click="zoomOut()">
          <template #icon>
            <n-icon :component="ZoomOutIcon" />
          </template>
        </n-button>
      </vue-panel>
    </vue-flow>
    <!-- <n-timeline v-if="history.length > 0" horizontal class="px-6">
      <n-timeline-item v-for="item in history" :key="item.id" :type="item.type" :title="item.data.id"
        :time="item.time" />
    </n-timeline> -->
  </div>

  <fork-node-modal
    v-model:show="isModalShown"
    :mode="props.mode"
    :node="activeNode"
    :is-fork-node="isForkNode"
    @fork:complete="handleForkComplete"
  />
</template>

<script setup lang="tsx">
import type { ProtocolModels } from "@airalogy/shared/types/models"

import type { CascaderOption, DataTableColumns } from "naive-ui"
import { useBoolean, useFormRules, usePagination } from "@/composables"
import { useFlowLayout } from "@/composables/useFlowLayout"
import { useRouterPush } from "@/composables/useRouterPush"

import { fetchProtocols, postForkProtocol } from "@/service/api/project-protocols"
import { fetchProjectList } from "@/service/api/projects"

import { fetchUserLabs } from "@/service/api/users"
import { useAuthStore } from "@/store/modules/auth"
import { useRouteStore } from "@/store/modules/route"
import { useProtocolWorkflowStore } from "@/store/modules/workflow"
import { normalizeWorkflowInfo, normalizeWorkflowProtocols, splitWorkflowEdge } from "@/utils/workflow"
import { useProtocolInfoStore } from "@/views/project-protocols/hooks/useProtocolInfoStore"
import { useClosableMessage } from "@airalogy/composables"
import {
  type Edge,
  MarkerType,
  type Node,
  type NodeChange,
  useVueFlow,
  VueFlow,
  Panel as VuePanel,
} from "@vue-flow/core"
import RefreshIcon from "~icons/tabler/refresh"
import ZoomInIcon from "~icons/tabler/zoom-in"
import ZoomOutIcon from "~icons/tabler/zoom-out"
import BidirectionalEdge from "./bidirectional-edge.vue"
import BidirectionalNode from "./bidirectional-node.vue"
import ForkNodeModal from "./fork-node-modal.vue"

interface IProps {
  id: string
  uid: string
  name: string
  mode: "edit" | "preview" | "report"
  // modelValue?: {
  //   id: string
  //   time: string
  //   type: "default" | "error" | "info" | "success" | "warning"
  //   data: any
  // }[]
}

const props = withDefaults(defineProps<IProps>(), {})

const emit = defineEmits<IEmits>()
interface IEmits {
  (e: "update:moduleValue", value: { id: string, time: string, type: string }[]): void
}
// const history = useVModel(props, "modelValue", emit)

const workflowStore = useProtocolWorkflowStore()

const { protocolInfo } = useProtocolInfoStore()!

const workflowData = computed({
  get: () => workflowStore.getWorkflow(props.id)?.data,
  set: (newData) => {
    workflowStore.setData(props.id, newData)
  },
})
const normalizedWorkflowData = computed(() => normalizeWorkflowInfo(workflowData.value))
const workflowNodes = computed({
  get: () => workflowStore.getWorkflow(props.id)?.workflowNodes,
  set: (newWorkflowNodes) => {
    workflowStore.setWorkflowNodes(props.id, newWorkflowNodes)
  },
})

const {
  fitView,
  zoomIn,
  zoomOut,
  hooks,
  findNode,
  onEdgeMouseEnter,
  onEdgeMouseLeave,
  onNodeClick,
  getNodes,
  onEdgeClick,
  updateNodeInternals,
} = useVueFlow()

const flowEdges = ref<Edge<{ direction: any }>[]>([])

const { layout } = useFlowLayout()

const { bool: isModalShown, setTrue: showModal, setFalse: hideModal } = useBoolean()

const nodeList = ref<Node[]>([])

const handleDebouncedUpdateNode = useDebounceFn((direction: "TB" | "LR" = "LR") => {
  updateNodeInternals()
}, 500)

function handleLayout(direction: "TB" | "LR" = "LR") {
  if (!workflowNodes.value) {
    return
  }

  const nodes = layout(workflowNodes.value, flowEdges.value, direction)
  workflowNodes.value = nodes
  workflowStore.setWorkflowNodes(props.id, nodes)
}

function handleNode(currNodes: Node[]) {
  handleLayout("LR")
  nodeList.value = currNodes
  hooks.value.nodesChange.on(async (payload: NodeChange[]) => {
    if (payload.length > 0 && payload.some(({ type }) => type === "dimensions")) {
      handleLayout()
      await fitView()
    }
  })
}
const activeNode = ref<Node | null>(null)

function resetTransform() {
  return fitView()
}

const apiKey = ref<string | null>(null)
const mappings = ref<Record<"source" | "target", string>[] | null>(null)
const initialized = ref(false)

provide("chain-state", { apiKey, mappings, initialized })
watch(
  normalizedWorkflowData,
  (info) => {
    if (!info) {
      return
    }

    const { edges } = info
    const protocols = normalizeWorkflowProtocols(info.protocols || [])
    const protocolMap = new Map(protocols.map(protocol => [protocol.protocolIndex, protocol]))
    const graphDataMap = new Map<
      string,
      { bidirectional: { id: string, type: "from" | "to" }[], from: string[], to: string[] }
    >()

    edges.forEach((it) => {
      const parsed = splitWorkflowEdge(it)
      if (!parsed) {
        return
      }

      const { source: rawSource, target: rawTarget, operator } = parsed
      const sourceIndex = Number(rawSource)
      const targetIndex = Number(rawTarget)
      const source = Number.isInteger(sourceIndex) && protocolMap.has(sourceIndex)
        ? protocolMap.get(sourceIndex)!.airalogyProtocolId
        : rawSource
      const target = Number.isInteger(targetIndex) && protocolMap.has(targetIndex)
        ? protocolMap.get(targetIndex)!.airalogyProtocolId
        : rawTarget

      if (!source || !target) {
        return
      }

      if (operator === "<->") {
        const prevSource = graphDataMap.get(source)
        const prevTarget = graphDataMap.get(target)

        if (prevSource) {
          prevSource.bidirectional.push({ id: target, type: "from" })
        }
        else {
          graphDataMap.set(source, {
            bidirectional: [{ id: target, type: "from" }],
            from: [],
            to: [],
          })
        }

        if (prevTarget) {
          prevTarget.bidirectional.push({ id: source, type: "to" })
        }
        else {
          graphDataMap.set(target, {
            bidirectional: [{ id: source, type: "to" }],
            from: [],
            to: [],
          })
        }

        return
      }

      // flowEdgeList.push({
      //   id: `${source}-${target}`,
      //   source,
      //   target,
      //   type: "smoothstep",
      //   markerEnd: MarkerType.Arrow,
      // })

      const prevSource = graphDataMap.get(source)
      const prevTarget = graphDataMap.get(target)

      if (
        prevSource
        && prevTarget
        && prevSource.from.findIndex(node => node === target) !== -1
        && prevTarget.to.findIndex(node => node === source) !== -1
      ) {
        prevSource.bidirectional.push({ id: target, type: "from" })
        prevTarget.bidirectional.push({ id: source, type: "to" })
      }

      if (prevSource) {
        prevSource.to.push(target)
      }
      else {
        graphDataMap.set(source, {
          bidirectional: [],
          from: [],
          to: [target],
        })
      }

      if (prevTarget) {
        prevTarget.from.push(source)
      }
      else {
        graphDataMap.set(target, {
          bidirectional: [],
          from: [source],
          to: [],
        })
      }
    })

    const flowEdgeList: (Edge & { pathOptions?: { parallel?: boolean } })[] = []
    // 创建边缘
    const edgesSet = new Set()

    graphDataMap.forEach(({ to, from, bidirectional }, nodeId) => {
      //   to.forEach(target => {
      //     const toId = `${nodeId}-${target}`
      //     const fromId = `${target}-${nodeId}`
      //     if (!edgesSet.has(toId) && !edgesSet.has(fromId)) {
      //       edgesSet.add(toId)
      //       flowEdgeList.push({
      //         id: toId,
      //         source: nodeId,
      //         target,
      //         type: "smoothstep",
      //         markerEnd: MarkerType.Arrow,
      //       })
      //     }
      //   })

      //   from.forEach(source => {
      //     const toId = `${source}-${nodeId}`
      //     const fromId = `${nodeId}-${source}`
      //     if (!edgesSet.has(toId) && !edgesSet.has(fromId)) {
      //       edgesSet.add(toId)
      //       flowEdgeList.push({
      //         id: toId,
      //         source: source,
      //         target: nodeId,
      //         type: "smoothstep",
      //         markerEnd: MarkerType.Arrow,
      //       })
      //     }
      //   })

      // 处理双向边, 只允许单向edge (但是渲染双向)
      bidirectional.forEach(({ id: toId, type }) => {
        if (toId === nodeId || type === "from") {
          return
        }

        const toKey = `${nodeId}-${toId}`
        const fromKey = `${toId}-${nodeId}`

        if (edgesSet.has(toKey) || edgesSet.has(fromKey)) {
          // NOPE
          return
        }

        edgesSet.add(toKey)
        edgesSet.add(fromKey)

        flowEdgeList.push({
          id: toKey,
          source: nodeId,
          target: toId,
          type: "bidirectional",
          markerEnd: MarkerType.Arrow,
          pathOptions: { parallel: true },
          style: (edge) => {
            if (!edge.targetNode.selected && !edge.sourceNode.selected && !edge.data.stroke) {
              return {}
            }

            return {
              stroke: edge.data.stroke || "#10b981",
              strokeWidth: 3,
              zIndex: edge.data.zIndex,
            }
          },
        })
      })

      // 处理到节点的边
      to.forEach((target) => {
        const toKey = `${nodeId}-${target}`

        if (edgesSet.has(toKey)) {
          return
        }

        edgesSet.add(toKey)
        flowEdgeList.push({
          id: toKey,
          source: nodeId,
          target,
          type: "bidirectional",
          markerEnd: MarkerType.Arrow,
          style: (edge) => {
            if (!edge.targetNode.selected && !edge.sourceNode.selected && !edge.data.stroke) {
              return {}
            }

            return {
              stroke: edge.data.stroke || "#10b981",
              strokeWidth: 3,
              zIndex: edge.data.zIndex,
            }
          },
        })
      })

      // 处理从节点的边
      from.forEach((source) => {
        const toKey = `${source}-${nodeId}`
        if (edgesSet.has(toKey)) {
          return
        }

        edgesSet.add(toKey)
        flowEdgeList.push({
          id: toKey,
          source,
          target: nodeId,
          type: "bidirectional",
          markerEnd: MarkerType.Arrow,
          style: (edge) => {
            if (!edge.targetNode.selected && !edge.sourceNode.selected && !edge.data.stroke) {
              return {}
            }

            return {
              stroke: edge.data.stroke || "#10b981",
              strokeWidth: 3,
              zIndex: edge.data.zIndex,
            }
          },
        })
      })
    })

    flowEdges.value = flowEdgeList
    const flowNodeList: Node[] = []

    protocols.forEach(({ airalogyProtocolId, protocolName, protocolIndex }, idx) => {
      const nodeId = airalogyProtocolId || String(protocolIndex)
      const node: Node = {
        id: nodeId,
        position: { x: 200 * idx, y: 0 },
        data: { label: protocolName, id: nodeId, source: null, target: null, sequence: protocolIndex },
        draggable: false,
        type: "in-out",
        parentNode: undefined,
      }

      const target = graphDataMap.get(nodeId)
      if (target) {
        if (target.bidirectional.length === 0) {
          if (target.from.length === 0 && target.to.length !== 0) {
            node.type = "single-output"
          }
          else if (target.to.length === 0 && target.from.length !== 0) {
            node.type = "single-input"
          }
          else {
            // NOPE
          }
        }
        else if (target.bidirectional.length === 1) {
          const { type } = target.bidirectional[0]
          if (type === "from" && target.from.length === 0) {
            node.type = "bidirectional-input"
          }
          else if (type === "to" && target.from.length === 0) {
            node.type = "bidirectional-output"
          }
        }
      }

      flowNodeList.push(node)
    })

    workflowNodes.value = flowNodeList
  },
  { immediate: true },
)

// watch(workflowNodes, (nodes) => {
//   console.log(nodes)
// }, { immediate: true })

// onMounted(async () => {
//   initialized.value = false
//   try {
//     const { data } = await getUserAPIKey()
//     if (data && data.api_key) {
//       apiKey.value = data.api_key
//     }
//   } catch (e) {
//     // nope
//   } finally {
//     initialized.value = true
//   }
// })

// watch(flowNodes, nodes => {
//   console.log(nodes)
//   if (nodes.every(it => it.data.source)) {
//     debugger
//     handleLayout()
//   }
// })

function handleUpdateNode(data: {
  id: string
  label: string
  source: ProtocolModels.ProjectProtocolInfo | null
}) {
  if (!workflowNodes.value) {
    return
  }

  const { id } = data
  const node = workflowNodes.value.find(it => it.id === id)
  if (node) {
    node.data = data
  }

  void nextTick(async () => {
    if (!workflowNodes.value) {
      return
    }

    if (workflowNodes.value.every(it => it.data.source)) {
      handleLayout()
      await fitView()
    }
  })
}

const { routerPushByKey } = useRouterPush()
const { addCacheRoutes } = useRouteStore()
const { bool: isForkNode, setTrue: setForkNode, setFalse: resetForkNode } = useBoolean()
const message = useClosableMessage()

const authStore = useAuthStore()
const hasFetched = ref(false)

interface FormModel {
  uid: string
  name: string
  combinedId: string | null
}

const initModel = computed<FormModel>(() => {
  if (!activeNode.value) {
    return {
      uid: "",
      name: "",
      combinedId: null,
    }
  }

  const { data } = activeNode.value

  return {
    uid: data.id,
    name: data.label,
    combinedId: null,
  }
})

const model = ref<FormModel>({ ...initModel.value })

watch(activeNode, () => {
  model.value = { ...initModel.value }
})

const defaultOptions = ref<CascaderOption[] | null>(null)
const options = ref<CascaderOption[]>([])

const { defaultRequiredRule } = useFormRules()

const rules: Record<keyof FormModel, App.Global.FormRule[]> = {
  uid: [
    defaultRequiredRule,
    {
      min: 1,
      max: 40,
      message: "Research node id must be between 1 and 40 characters long",
      trigger: ["change", "blur"],
    },
    {
      pattern: /^[\w-]*$/,
      message:
        "Research node id can only contain letters (a-z, A-Z), numbers (0-9), or hyphens (_-)",
      trigger: ["change", "blur"],
    },
    {
      validator: (rule, value, callback) => {
        if (/^[_-]|[_-]$/.test(value)) {
          return new Error("Research node name should not start or end with a hyphen")
        }
        if (/[_-]{2,}/.test(value)) {
          return new Error("Hyphens cannot appear consecutively")
        }
        return true
      },
      trigger: ["change", "blur"],
    },
  ],
  name: [
    defaultRequiredRule,
    {
      min: 1,
      max: 40,
      message: "Research node display name must be between 1 and 40 characters long",
      trigger: ["change", "blur"],
    },
    {
      validator: (rule, value, callback) => {
        if (/^[_-]|[_-]$/.test(value)) {
          return new Error("Research node display name should not start or end with a hyphen")
        }
        if (/[_-]{2,}/.test(value)) {
          return new Error("Hyphens cannot appear consecutively")
        }
        return true
      },
      trigger: ["change", "blur"],
    },
  ],
  combinedId: [defaultRequiredRule],
}

async function fetchLabs(show: boolean) {
  if (!show || hasFetched.value) {
    return
  }

  // TODO: order and pagination
  try {
    const data = await fetchUserLabs(authStore.userInfo.id, {
      page: 1,
      pageSize: 9999,
    })

    if (data) {
      const filteredOptions = data.labs.map((it) => {
        const { name, id, uid } = it

        // return { label: `${name} (${uid})`, value: id, depth: 1, isLeaf: false }
        return { label: `${name} (${uid})`, value: uid, depth: 1, isLeaf: false, id }
      })

      if (filteredOptions.length > 0) {
        options.value = filteredOptions
      }
      else if (defaultOptions.value && defaultOptions.value.length > 0) {
        options.value = defaultOptions.value
      }
    }
    await nextTick(() => {
      hasFetched.value = true
    })
  }
  catch (e) {
    message.error((e as Error).message)
  }
}

async function handleLoad(option: CascaderOption) {
  const { value, id: labId } = option

  try {
    const data = await fetchProjectList({
      labId: labId as string,
      page: 1,
      pageSize: 9999,
    })
    if (data) {
      const children = data.projects.map(({ uid, name, id }) => {
        // return { label: `${name} (${uid})`, value: `${value}_${uid}`, depth: 2, isLeaf: true }
        return {
          label: `${name} (${uid})`,
          value: `${value}|${id}`,
          depth: 2,
          isLeaf: true,
          uid,
          id,
        }
      })
      await nextTick(() => {
        option.children = children
      })
    }
  }
  catch (e) {
    message.error((e as Error).message)
  }
}

function handleFork(nodeId: string) {
  showModal()
  const node = findNode(nodeId)

  if (node) {
    activeNode.value = node
    setForkNode()
  }
  else {
    activeNode.value = null
  }
}

function handleRedirect() {
  const { data } = activeNode.value || {}
  const { id: rnId } = data || {}

  if (!data || !data.source) {
    return
  }

  const { id, research_node, name } = data.source

  addCacheRoutes("AddResearchRecord" as App.Global.RouteKey)
  hideModal()

  void nextTick(() => {
    void routerPushByKey("add-protocol-record-from-workflow", {
      params: { protocolId: id },
      query: {
        protocol: research_node.id,
        target: rnId,
        chain: props.id,
      },
    })
  })
}

const checkedRowKeys = ref([])

const total = ref<number>(0)

const { currentPage, currentPageSize } = usePagination({
  options: { page: 1, pageSize: 6, total },
  fetchData: handleGetResearches,
})

const columns: DataTableColumns<ProtocolModels.ProjectProtocolInfo> = [
  {
    type: "selection",
    multiple: false,
  },
  {
    title: "Name",
    key: "name",
  },
  {
    title: "id",
    key: "uid",
  },
]

const nodeListData = ref<ProtocolModels.ProjectProtocolInfo[]>([])

const projectId = computed(() => model.value.combinedId?.split?.("|")?.[1])

async function handleGetResearches() {
  if (!projectId.value) {
    return
  }

  try {
    const res = await fetchProtocols({
      projectId: projectId.value,
      page: currentPage.value,
      pageSize: currentPageSize.value,
    })
    if (res.data) {
      const { protocols, total_count } = res.data
      nodeListData.value = protocols
      total.value = total_count
    }
  }
  catch (e) {
    // NOPE
  }
}

watch(projectId, async (val) => {
  total.value = 0
  currentPage.value = 0

  if (val) {
    await handleGetResearches()
  }
  else {
    nodeListData.value = []
  }
})
// watch(
//   protocolInfo,
//   async node => {
//     if (!node?.id) {
//       return
//     }

//     try {
//       const { data, error } = await getResearchEnvVariables(node.id)
//       if (!data || !data.env_vars || error) {
//         return
//       }

//       // const config = parseYaml(data.env_vars)
//       if (config.mappings) {
//         mappings.value = config.mappings
//       }
//     } catch (e) {
//       // NOPE
//     } finally {
//       initialized.value = true
//     }
//   },
//   { immediate: true },
// )

async function handleSubmitFork() {
  const { name, uid } = model.value
  if (!name || !uid) {
    return
  }

  if (!activeNode.value || !protocolInfo.value) {
    return
  }

  // const { source } = activeNode.value.data
  // if (!source) {
  //   return
  // }

  // const { id } = source as Api.Research.ForkedResearchResponse
  // const { project_id } = protocolInfo.value

  const targetId = checkedRowKeys.value[0]
  if (!targetId) {
    return
  }

  try {
    const res = await postForkProtocol({
      parentProtocolId: targetId,
      protocolName: name,
      projectId: protocolInfo.value.project_id,
      protocolUid: uid,
    })
    if (res) {
      message.success(`Successfully forked research ${name}`)

      activeNode.value.data.target = res
      hideModal()
    }
  }
  catch (e) {
    // NOPE
  }
}

watch(isModalShown, (val) => {
  if (!val) {
    model.value = { ...initModel.value }
  }
})

onMounted(() => {
  onEdgeMouseEnter(({ edge }) => {
    edge.data.zIndex = 9999
    edge.data.stroke = "orange"
  })

  onEdgeMouseLeave(({ edge }) => {
    if (edge.selected) {
      return
    }

    edge.data.zIndex = undefined
    edge.data.stroke = undefined
  })

  onEdgeClick(({ edge }) => {
    if (edge.selected) {
      edge.selected = false
    }
    else {
      edge.selected = true
      edge.data.stroke = undefined
    }
  })

  onNodeClick(({ node }) => {
    getNodes.value.forEach((it) => {
      if (it.id === node.id) {
        it.selected = true
      }
      else {
        it.selected = false
      }
    })
  })
})

function handleForkComplete(res: ProtocolModels.ProtocolResponseInfo, node: Node | null) {
  if (!node || !workflowNodes.value) {
    return
  }

  const targetNode = findNode(node.id)
  if (targetNode) {
    targetNode.data.target = res
    // Refresh layout and view
    void nextTick(async () => {
      handleLayout()
      await fitView()
    })
  }
}
</script>

<style scoped lang="sass">
.card__wrapper
  --n-padding-bottom: 0!important
  --n-action-color: transparent!important
:deep(.vue-flow__node)
  padding: 0
</style>
