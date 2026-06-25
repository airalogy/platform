<template>
  <div class="assigner-flow-chart" :style="{ height: containerHeight }">
    <n-spin :show="loading" content-class="w-full h-full">
      <vue-flow
        v-if="flowNodes.length > 0"
        :id="flowId"
        class="vue-flow-container"
        :nodes="flowNodes"
        :edges="flowEdges"
        :default-viewport="{ zoom: 1, x: 0, y: 0 }"
        :min-zoom="0.2"
        :max-zoom="4"
        :snap-to-grid="true"
        :snap-grid="[15, 15]"
        fit-view-on-init
        @pane-ready="onPaneReady"
        @nodes-initialized="onNodesInitialized"
        @pane-click="handlePaneClick"
      >
        <template #node-assigner-node="slotProps">
          <assigner-graph-node
            v-bind="slotProps"
            @node-click="(nodeId: string, nodeType: string, event: MouseEvent) => handleNodeClick(nodeId, nodeType, event)"
          />
        </template>

        <vue-panel position="bottom-right" class="zoom-panel">
          <div class="zoom-info">
            {{ Math.round(viewport.zoom * 100) }}%
          </div>
        </vue-panel>
      </vue-flow>
      <n-empty v-else-if="!loading" description="No assigner graph available" />
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import type { Edge, Node } from "@vue-flow/core"
import { useFlowLayout } from "@/composables/useFlowLayout"
import { MarkerType, useVueFlow, VueFlow, Panel as VuePanel } from "@vue-flow/core"
import AssignerGraphNode from "./AssignerGraphNode.vue"

defineOptions({ name: "AssignerFlowChart" })

const props = withDefaults(defineProps<Props>(), {
  nodeSchemaMap: () => ({}),
  height: "600px",
  loading: false,
})

const emit = defineEmits<{
  (e: "nodeClick", nodeId: string, nodeType: string, event: MouseEvent): void
}>()

interface GraphNode {
  name: string
  type: "assigned_field" | "dependent_field" | "assigner"
}

type GraphEdge = [string, string]

interface AssignerGraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

interface NodeSchemaInfo {
  title?: string
  type?: string
  format?: string
  description?: string
}

interface NodeData {
  name: string
  title?: string
  type: "assigned_field" | "dependent_field" | "assigner"
  schemaInfo?: NodeSchemaInfo
  showTitle: boolean
  isHighlighted: boolean
  isDimmed: boolean
}

interface Props {
  flowId: string
  assignerGraph: AssignerGraphData | null
  nodeSchemaMap?: Record<string, NodeSchemaInfo>
  height?: string
  loading?: boolean
}

// Use toRef for flowId to ensure reactivity
const flowIdRef = toRef(props, "flowId")

// Display mode
const showTitle = ref(false)

// Selection state
const selectedNodeId = ref<string | null>(null)

// Container height
const containerHeight = computed(() => props.height)

// Vue Flow instance
const {
  fitView,
  zoomIn,
  zoomOut,
  viewport,
  findNode,
  getNodes,
  getEdges,
  updateNode,
} = useVueFlow(flowIdRef.value)

// Layout helper
const { layout } = useFlowLayout(flowIdRef.value)

// Build adjacency map for relationships
const adjacencyMap = computed(() => {
  const map = new Map<string, { inputs: string[], outputs: string[] }>()

  if (!props.assignerGraph) {
    return map
  }

  const { nodes, edges } = props.assignerGraph

  nodes.forEach((node) => {
    map.set(node.name, { inputs: [], outputs: [] })
  })

  edges.forEach(([from, to]) => {
    map.get(from)?.outputs.push(to)
    map.get(to)?.inputs.push(from)
  })

  return map
})

// Sanitize node ID
function sanitizeNodeId(id: string): string {
  return id.replace(/\W/g, "_")
}

// Get original node name from sanitized ID
function getOriginalNodeName(sanitizedId: string): string {
  if (!props.assignerGraph) {
    return sanitizedId
  }

  const node = props.assignerGraph.nodes.find(
    n => sanitizeNodeId(n.name) === sanitizedId,
  )
  return node?.name || sanitizedId
}

// Get node type by name
function getNodeType(nodeName: string): string | null {
  if (!props.assignerGraph) {
    return null
  }
  const node = props.assignerGraph.nodes.find(n => n.name === nodeName)
  return node?.type || null
}

// Recursively get all upstream nodes
function getAllUpstreamNodes(nodeName: string, visited: Set<string>): void {
  if (visited.has(nodeName)) {
    return
  }
  visited.add(nodeName)

  const adj = adjacencyMap.value.get(nodeName)
  if (adj) {
    adj.inputs.forEach((inputName) => {
      getAllUpstreamNodes(inputName, visited)
    })
  }
}

// Recursively get all downstream nodes
function getAllDownstreamNodes(nodeName: string, visited: Set<string>): void {
  if (visited.has(nodeName)) {
    return
  }
  visited.add(nodeName)

  const adj = adjacencyMap.value.get(nodeName)
  if (adj) {
    adj.outputs.forEach((outputName) => {
      getAllDownstreamNodes(outputName, visited)
    })
  }
}

// Get highlighted node names (using original names)
function getHighlightedNames(nodeId: string | null): Set<string> {
  if (!nodeId) {
    return new Set()
  }

  const highlighted = new Set<string>()
  const originalName = getOriginalNodeName(nodeId)
  const nodeType = getNodeType(originalName)

  // For assigner nodes, only highlight direct connections
  if (nodeType === "assigner") {
    highlighted.add(originalName)
    const adj = adjacencyMap.value.get(originalName)
    if (adj) {
      adj.inputs.forEach(name => highlighted.add(name))
      adj.outputs.forEach(name => highlighted.add(name))
    }
  }
  else {
    // For field nodes (assigned_field or dependent_field), recursively get all upstream and downstream nodes
    // Use separate visited sets for upstream and downstream to avoid interference
    const upstreamVisited = new Set<string>()
    const downstreamVisited = new Set<string>()

    getAllUpstreamNodes(originalName, upstreamVisited)
    getAllDownstreamNodes(originalName, downstreamVisited)

    // Merge both sets into highlighted
    upstreamVisited.forEach(name => highlighted.add(name))
    downstreamVisited.forEach(name => highlighted.add(name))
  }

  return highlighted
}

// Initial nodes
const flowNodes = computed<Node<NodeData>[]>(() => {
  if (!props.assignerGraph) {
    return []
  }

  const { nodes } = props.assignerGraph

  return nodes.map((node, index) => {
    const schemaInfo = props.nodeSchemaMap[node.name]

    return {
      id: sanitizeNodeId(node.name),
      type: "assigner-node",
      position: { x: 0, y: index * 80 },
      data: {
        name: node.name,
        type: node.type,
        schemaInfo,
        showTitle: false,
        isHighlighted: false,
        isDimmed: false,
      },
      draggable: false,
    }
  })
})

// Initial edges
const flowEdges = computed<Edge[]>(() => {
  if (!props.assignerGraph) {
    return []
  }

  const { edges } = props.assignerGraph

  return edges.map(([from, to]) => {
    const fromId = sanitizeNodeId(from)
    const toId = sanitizeNodeId(to)

    return {
      id: `edge-${fromId}-${toId}`,
      source: fromId,
      target: toId,
      type: "default",
      animated: false,
      style: {
        stroke: "#9ca3af",
        strokeWidth: 1,
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: "#9ca3af",
        width: 12,
        height: 12,
      },
    }
  })
})

// Update nodes and edges highlight state
function updateHighlightState(nodeId: string | null) {
  const highlightedNames = getHighlightedNames(nodeId)
  const hasSelection = nodeId !== null

  // Update nodes
  getNodes.value.forEach((node) => {
    const originalName = getOriginalNodeName(node.id)
    const isHighlighted = highlightedNames.has(originalName)

    updateNode(node.id, {
      data: {
        ...node.data,
        isHighlighted: hasSelection && isHighlighted,
        isDimmed: hasSelection && !isHighlighted,
      },
    })
  })

  // Update edges
  getEdges.value.forEach((edge) => {
    const fromName = getOriginalNodeName(edge.source)
    const toName = getOriginalNodeName(edge.target)
    const isHighlighted = highlightedNames.has(fromName) && highlightedNames.has(toName)

    // Directly modify edge properties
    edge.animated = hasSelection && isHighlighted
    edge.style = {
      stroke: hasSelection && isHighlighted ? "#f59e0b" : "#9ca3af",
      strokeWidth: hasSelection && isHighlighted ? 2 : 1,
      opacity: hasSelection && !isHighlighted ? 0.15 : 1,
    }
    edge.markerEnd = {
      type: MarkerType.ArrowClosed,
      color: hasSelection && isHighlighted ? "#f59e0b" : "#9ca3af",
      width: 12,
      height: 12,
    }
  })
}

// Update showTitle state
function updateShowTitleState(showTitleValue: boolean) {
  getNodes.value.forEach((node) => {
    updateNode(node.id, {
      data: {
        ...node.data,
        showTitle: showTitleValue,
      },
    })
  })
}

// Event handlers
function handleNodeClick(nodeId: string, nodeType: string, event: MouseEvent) {
  if (selectedNodeId.value === nodeId) {
    clearSelection()
  }
  else {
    selectedNodeId.value = nodeId
    updateHighlightState(nodeId)
  }
  emit("nodeClick", nodeId, nodeType, event)
}

function handlePaneClick() {
  clearSelection()
}

function clearSelection() {
  selectedNodeId.value = null
  updateHighlightState(null)
}

// Lifecycle handlers
function onPaneReady() {
  setTimeout(() => {
    fitView({ padding: 0.1, includeHiddenNodes: true })
  }, 100)
}

async function onNodesInitialized() {
  await layoutNodes()
  await nextTick()
  fitView({ padding: 0.1, includeHiddenNodes: true })
}

// Layout nodes using dagre
function layoutNodes() {
  if (!props.assignerGraph || flowNodes.value.length === 0) {
    return
  }

  const nodes = getNodes.value
  const edges = getEdges.value

  if (nodes.length === 0) {
    return
  }

  const layoutedNodes = layout(nodes, edges, "LR")

  layoutedNodes.forEach((layoutedNode) => {
    const node = findNode(layoutedNode.id)
    if (node) {
      node.position = layoutedNode.position
    }
  })
}

// Exposed methods
function handleZoomIn() {
  zoomIn()
}

function handleZoomOut() {
  zoomOut()
}

function handleFitView() {
  fitView({ padding: 0.1, includeHiddenNodes: true })
}

function toggleDisplayMode() {
  showTitle.value = !showTitle.value
  updateShowTitleState(showTitle.value)
}

// Expose API
defineExpose({
  zoomIn: handleZoomIn,
  zoomOut: handleZoomOut,
  fitView: handleFitView,
  toggleDisplayMode,
  showTitle: computed(() => showTitle.value),
  viewport,
})
</script>

<style scoped lang="sass">
.assigner-flow-chart
  @apply relative w-full
  min-height: 400px

  :deep(.n-spin-container)
    @apply w-full h-full

  :deep(.n-spin-content)
    @apply w-full h-full

.vue-flow-container
  @apply w-full
  height: 100%
  min-height: inherit
  background: #f9fafb

.zoom-panel
  @apply bg-white rounded px-2 py-1 shadow text-xs text-gray-500

.zoom-info
  @apply font-mono

:deep(.vue-flow__node)
  @apply p-0

:deep(.vue-flow__background)
  @apply bg-gray-50

:deep(.vue-flow__controls)
  @apply hidden
</style>
