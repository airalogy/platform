<template>
  <div class="assigner-graph-wrapper">
    <!-- Toolbar -->
    <div class="graph-toolbar">
      <div class="toolbar-left">
        <n-button-group size="small">
          <n-button @click="handleZoomIn">
            <template #icon>
              <n-icon :component="ZoomInIcon" />
            </template>
          </n-button>
          <n-button @click="handleFitView">
            <template #icon>
              <n-icon :component="FitIcon" />
            </template>
          </n-button>
          <n-button @click="handleZoomOut">
            <template #icon>
              <n-icon :component="ZoomOutIcon" />
            </template>
          </n-button>
        </n-button-group>

        <n-divider vertical />

        <n-button size="small" :type="mainChartRef?.showTitle ? 'primary' : 'default'" @click="handleToggleDisplayMode">
          <template #icon>
            <n-icon :component="mainChartRef?.showTitle ? TitleIcon : NameIcon" />
          </template>
          {{ mainChartRef?.showTitle ? $t("common.title") : $t("common.name") }}
        </n-button>
      </div>

      <div class="toolbar-right">
        <n-button size="small" @click="showFullscreen = true">
          <template #icon>
            <n-icon :component="FullscreenIcon" />
          </template>
          {{ $t("common.fullscreen") }}
        </n-button>
      </div>
    </div>

    <!-- Legend -->
    <div v-if="assignerGraph" class="graph-legend">
      <div class="legend-items">
        <div class="legend-item">
          <div class="legend-box dependent-field" />
          <span>{{ $t("page.protocol.assignerGraph.dependentField") }}</span>
        </div>
        <div class="legend-item">
          <div class="legend-box assigner" />
          <span>{{ $t("page.protocol.assignerGraph.assigner") }}</span>
        </div>
        <div class="legend-item">
          <div class="legend-box assigned-field" />
          <span>{{ $t("page.protocol.assignerGraph.assignedField") }}</span>
        </div>
      </div>
    </div>

    <!-- Flow Graph -->
    <div class="graph-container">
      <assigner-flow-chart
        ref="mainChartRef"
        flow-id="main-flow"
        :assigner-graph="assignerGraph"
        :node-schema-map="nodeSchemaMap"
        :loading="isLoading"
        height="600px"
        @node-click="handleNodeClick"
      />
    </div>

    <!-- Fullscreen Modal -->
    <n-modal
      v-model:show="showFullscreen"
      preset="card"
      :title="$t('page.protocol.assignerGraph.fullscreenTitle')"
      :bordered="false"
      :segmented="{ content: true }"
      style="width: 95vw; height: 95vh"
      size="huge"
    >
      <template #header-extra>
        <n-space>
          <n-button size="small" :type="modalChartRef?.showTitle ? 'primary' : 'default'" @click="handleModalToggleDisplayMode">
            <template #icon>
              <n-icon :component="modalChartRef?.showTitle ? TitleIcon : NameIcon" />
            </template>
            {{ modalChartRef?.showTitle ? $t("common.title") : $t("common.name") }}
          </n-button>
          <n-button-group size="small">
            <n-button @click="handleModalZoomIn">
              <template #icon>
                <n-icon :component="ZoomInIcon" />
              </template>
            </n-button>
            <n-button @click="handleModalFitView">
              <template #icon>
                <n-icon :component="FitIcon" />
              </template>
            </n-button>
            <n-button @click="handleModalZoomOut">
              <template #icon>
                <n-icon :component="ZoomOutIcon" />
              </template>
            </n-button>
          </n-button-group>
        </n-space>
      </template>

      <div class="fullscreen-graph-container">
        <assigner-flow-chart
          v-if="modalFlowReady"
          ref="modalChartRef"
          flow-id="modal-flow"
          :assigner-graph="assignerGraph"
          :node-schema-map="nodeSchemaMap"
          height="calc(95vh - 120px)"
          @node-click="handleModalNodeClick"
        />
      </div>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types"
import FitIcon from "~icons/tabler/arrows-maximize"
import NameIcon from "~icons/tabler/code"
import FullscreenIcon from "~icons/tabler/maximize"
import TitleIcon from "~icons/tabler/text-caption"
import ZoomInIcon from "~icons/tabler/zoom-in"
import ZoomOutIcon from "~icons/tabler/zoom-out"
import { useProtocolInfoStore } from "../../hooks/useProtocolInfoStore"
import AssignerFlowChart from "./components/AssignerFlowChart.vue"

defineOptions({ name: "AssignerGraph" })

const store = useProtocolInfoStore()
const protocolInfo = computed(() => store?.protocolInfo.value ?? null)

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

// Chart refs
const mainChartRef = ref<InstanceType<typeof AssignerFlowChart> | null>(null)
const modalChartRef = ref<InstanceType<typeof AssignerFlowChart> | null>(null)

// Fullscreen state
const showFullscreen = ref(false)
const modalFlowReady = ref(false)

// Get assigner_graph from protocolInfo store
const assignerGraph = computed<AssignerGraphData | null>(() => {
  if (!protocolInfo.value) {
    return null
  }
  return (protocolInfo.value as any).assigner_graph || null
})

// Build node schema info map from json_schema
const nodeSchemaMap = computed<Record<string, NodeSchemaInfo>>(() => {
  if (!protocolInfo.value?.json_schema) {
    return {}
  }

  const map: Record<string, NodeSchemaInfo> = {}
  const jsonSchema = protocolInfo.value.json_schema as ProtocolModels.JsonSchema

  Object.values(jsonSchema).forEach((schema) => {
    if (schema?.properties) {
      Object.entries(schema.properties).forEach(([name, prop]: [string, any]) => {
        map[name] = {
          title: prop.title,
          type: prop.type,
          format: prop.format,
          description: prop.description,
        }
      })
    }
  })

  return map
})

// Loading state
const isLoading = computed(() => {
  return !protocolInfo.value
})

// Main chart handlers
function handleZoomIn() {
  mainChartRef.value?.zoomIn()
}

function handleZoomOut() {
  mainChartRef.value?.zoomOut()
}

function handleFitView() {
  mainChartRef.value?.fitView()
}

function handleToggleDisplayMode() {
  mainChartRef.value?.toggleDisplayMode()
}

function handleNodeClick(nodeId: string, nodeType: string, event: MouseEvent) {
  // Handle node click if needed
}

// Modal chart handlers
function handleModalZoomIn() {
  modalChartRef.value?.zoomIn()
}

function handleModalZoomOut() {
  modalChartRef.value?.zoomOut()
}

function handleModalFitView() {
  modalChartRef.value?.fitView()
}

function handleModalToggleDisplayMode() {
  modalChartRef.value?.toggleDisplayMode()
}

function handleModalNodeClick(nodeId: string, nodeType: string, event: MouseEvent) {
  // Handle modal node click if needed
}

// Watch for modal open to initialize flow
watch(showFullscreen, (newVal) => {
  if (newVal) {
    // Reset modal flow state
    modalFlowReady.value = false

    // Wait for modal animation to complete before rendering flow
    setTimeout(() => {
      modalFlowReady.value = true
    }, 300)
  }
  else {
    // Clean up when modal closes
    modalFlowReady.value = false
  }
})
</script>

<style scoped lang="sass">
.assigner-graph-wrapper
  @apply flex flex-col relative
  height: 100%
  min-height: 500px

.graph-toolbar
  @apply flex items-center justify-between px-4 py-2 bg-gray-50 border-b border-gray-200 flex-shrink-0

.toolbar-left
  @apply flex items-center gap-2

.toolbar-right
  @apply flex items-center gap-2

.graph-legend
  @apply px-4 py-2 bg-white border-b border-gray-200 flex-shrink-0

.legend-items
  @apply flex gap-6 flex-wrap

.legend-item
  @apply flex items-center gap-2 text-sm text-gray-600

.legend-box
  @apply w-8 h-5 rounded border

.legend-box.assigned-field
  @apply bg-green-50 border-green-500

.legend-box.dependent-field
  @apply bg-blue-50 border-blue-400

.legend-box.assigner
  @apply bg-pink-50 border-pink-500 rounded-full

.graph-container
  @apply flex-1 relative w-full
  height: 600px
  min-height: 600px

.fullscreen-graph-container
  @apply w-full
  height: calc(95vh - 120px)
</style>
