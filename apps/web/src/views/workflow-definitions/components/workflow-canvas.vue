<template>
  <div class="workflow-canvas" data-testid="workflow-canvas">
    <vue-flow
      :id="flowId" :nodes="nodes" :edges="edges" :nodes-draggable="!disabled" :nodes-connectable="!disabled"
      :delete-key-code="null" :min-zoom="0.2" :max-zoom="2" fit-view-on-init
      @connect="onConnect"
      @node-click="onNodeClick"
      @node-drag-stop="onDragStop"
    >
      <template #node-workflow="{ id, data }">
        <div class="workflow-canvas-card" :class="{ 'workflow-canvas-card--selected': id === selectedId }">
          <handle type="target" :position="Position.Left" :connectable="!disabled" />
          <div class="aira-type-meta aira-text-secondary">
            {{ $t("page.workflowDefinitions.cardNumber", { number: data.number }) }}
          </div>
          <strong>{{ data.title }}</strong>
          <div class="aira-type-meta mt-1">
            {{ data.protocol }} · {{ data.version }}
          </div>
          <handle type="source" :position="Position.Right" :connectable="!disabled" />
        </div>
      </template>
      <panel position="bottom-right">
        <div class="flex gap-1 rounded bg-white p-1 shadow">
          <n-button size="small" :aria-label="$t('page.workflowDefinitions.zoomOut')" @click="zoomOut()">
            −
          </n-button>
          <n-button size="small" :aria-label="$t('page.workflowDefinitions.zoomIn')" @click="zoomIn()">
            +
          </n-button>
          <n-button size="small" @click="fitView({ padding: 0.18 })">
            {{ $t("page.workflowDefinitions.fitView") }}
          </n-button>
        </div>
      </panel>
    </vue-flow>
  </div>
</template>

<script setup lang="ts">
import type { WorkflowAnalysisPublication } from "@/service/api/workflow-analysis-methods"
import type { WorkflowContext, WorkflowGraph } from "@/service/api/workflow-definitions"
import type { Connection, NodeDragEvent, NodeMouseEvent } from "@vue-flow/core"
import { createWorkflowId, workflowConditionText } from "@/utils/workflow-editor"
import { Handle, MarkerType, Panel, Position, useVueFlow, VueFlow } from "@vue-flow/core"
import { computed } from "vue"
import "@vue-flow/core/dist/style.css"
import "@vue-flow/core/dist/theme-default.css"

const props = defineProps<{ graph: WorkflowGraph, protocols: WorkflowContext["protocols"], methods?: WorkflowAnalysisPublication[], disabled: boolean, selectedId: string | null }>()
const emit = defineEmits<{
  connect: [source: string, target: string]
  select: [id: string]
  positions: [nodes: Array<{ node_id: string, position: { x: number, y: number } }>]
}>()
const flowId = `workflow-${createWorkflowId()}`
const { fitView, zoomIn, zoomOut } = useVueFlow(flowId)
const nodes = computed(() => props.graph.nodes.map((node, index) => {
  const protocol = node.kind === "protocol" ? props.protocols.find(protocol => protocol.id === node.protocol_id) : undefined
  const method = node.kind === "analysis" ? props.methods?.find(method => method.id === node.method_publication_id) : undefined
  return {
    id: node.node_id,
    type: "workflow",
    position: { ...node.position },
    data: { number: index + 1, title: node.title, protocol: node.kind === "protocol" ? protocol?.name ?? node.protocol_id : method?.title ?? node.method_publication_id, version: node.kind === "protocol" ? protocol?.versions.find(version => version.id === node.protocol_version_id)?.version ?? node.protocol_version_id : method?.digest.slice(0, 8) },
  }
}))
const edges = computed(() => props.graph.edges.map(edge => ({ id: edge.edge_id, source: edge.source_node_id, target: edge.target_node_id, markerEnd: MarkerType.ArrowClosed, label: edge.condition ? workflowConditionText(edge.condition) : undefined, style: edge.condition ? { strokeDasharray: "6 4" } : undefined })))
function onConnect(connection: Connection) {
  emit("connect", connection.source, connection.target)
}
function onNodeClick(event: NodeMouseEvent) {
  emit("select", event.node.id)
}
function onDragStop(event: NodeDragEvent) {
  emit("positions", event.nodes.map(node => ({ node_id: node.id, position: node.position })))
}
</script>

<style scoped>
.workflow-canvas { height: 540px; min-width: 0; border: 1px solid #e5e7eb; border-radius: 12px; background: #f8fafc; }
.workflow-canvas-card { width: 244px; min-height: 92px; padding: 14px; border: 1px solid #cbd5e1; border-radius: 10px; background: white; overflow-wrap: anywhere; }
.workflow-canvas-card--selected { border-color: #0084e2; box-shadow: 0 0 0 2px #0084e233; }
.workflow-canvas-card strong { display: block; font-size: 15px; line-height: 1.5; }
</style>
