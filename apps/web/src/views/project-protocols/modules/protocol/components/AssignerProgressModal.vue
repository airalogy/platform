<script setup lang="ts">
import IconCheckCircle from "~icons/ion/checkmark-circle"
import IconCloseCircle from "~icons/ion/close-circle"
import IconExpand from "~icons/ion/expand-outline"
import IconSync from "~icons/ion/sync"
import IconTime from "~icons/ion/time-outline"
import { NButton, NCard, NIcon, NModal, NProgress, NScrollbar, NSpin, NTag, NTooltip } from "naive-ui"
import { computed } from "vue"

export interface AssignerNode {
  prop: string
  level: number
  dependsOn: string[] // Fields this assigner depends on
  assignedFields: string[] // Fields this assigner will assign
  status: "pending" | "running" | "completed" | "error"
  error?: string
}

export interface AssignerProgressState {
  visible: boolean
  isDetailMode: boolean
  title: string
  nodes: AssignerNode[]
  currentLevel: number
  totalLevels: number
  isCompleted: boolean
}

const props = defineProps<{
  state: AssignerProgressState
}>()

const emit = defineEmits<{
  (e: "close"): void
  (e: "toggle-detail"): void
}>()

// Group nodes by level
const levelGroups = computed(() => {
  const groups = new Map<number, AssignerNode[]>()
  props.state.nodes.forEach((node) => {
    if (!groups.has(node.level)) {
      groups.set(node.level, [])
    }
    groups.get(node.level)!.push(node)
  })
  return groups
})

// Calculate progress percentage
const progressPercent = computed(() => {
  const completed = props.state.nodes.filter(n => n.status === "completed").length
  const total = props.state.nodes.length
  return total > 0 ? Math.round((completed / total) * 100) : 0
})

// Check if all completed
const allCompleted = computed(() => {
  return props.state.nodes.every(n => n.status === "completed" || n.status === "error")
})

// Status counts
const statusCounts = computed(() => ({
  pending: props.state.nodes.filter(n => n.status === "pending").length,
  running: props.state.nodes.filter(n => n.status === "running").length,
  completed: props.state.nodes.filter(n => n.status === "completed").length,
  error: props.state.nodes.filter(n => n.status === "error").length,
}))

const firstError = computed(() => props.state.nodes.find(n => n.status === "error" && n.error)?.error)

function getStatusColor(status: AssignerNode["status"]) {
  switch (status) {
    case "pending": return "#999"
    case "running": return "#2080f0"
    case "completed": return "#18a058"
    case "error": return "#d03050"
  }
}

function getStatusIcon(status: AssignerNode["status"]) {
  switch (status) {
    case "pending": return IconTime
    case "running": return IconSync
    case "completed": return IconCheckCircle
    case "error": return IconCloseCircle
  }
}
</script>

<template>
  <!-- Compact Mode: Fixed position indicator on the right -->
  <Teleport to="body">
    <Transition name="slide-right">
      <div
        v-if="state.visible && !state.isDetailMode"
        class="compact-progress"
        @click="emit('toggle-detail')"
      >
        <div class="compact-header">
          <n-spin v-if="!allCompleted" :size="14" />
          <n-icon v-else :component="IconCheckCircle" color="#18a058" :size="16" />
          <span class="compact-title">{{ allCompleted ? $t("page.protocol.assignerProgress.completed") : $t("page.protocol.assignerProgress.assigning") }}</span>
          <n-tooltip>
            <template #trigger>
              <n-icon :component="IconExpand" :size="14" class="expand-icon" />
            </template>
            {{ $t("page.protocol.assignerProgress.clickForDetails") }}
          </n-tooltip>
        </div>

        <div class="compact-progress-bar">
          <n-progress
            type="line"
            :percentage="progressPercent"
            :status="allCompleted ? (statusCounts.error > 0 ? 'error' : 'success') : 'default'"
            :show-indicator="false"
            :height="4"
            :border-radius="2"
          />
        </div>

        <div class="compact-stats">
          <span v-if="statusCounts.running > 0" class="stat running">
            <n-icon :component="IconSync" :size="12" class="spinning" />
            {{ statusCounts.running }}
          </span>
          <span class="stat completed">
            <n-icon :component="IconCheckCircle" :size="12" />
            {{ statusCounts.completed }}/{{ state.nodes.length }}
          </span>
          <span v-if="statusCounts.error > 0" class="stat error">
            <n-icon :component="IconCloseCircle" :size="12" />
            {{ statusCounts.error }}
          </span>
        </div>

        <div v-if="statusCounts.error > 0 && firstError" class="compact-error">
          {{ firstError }}
        </div>
      </div>
    </Transition>
  </Teleport>

  <!-- Detail Mode: Full modal -->
  <n-modal
    :show="state.visible && state.isDetailMode"
    :mask-closable="true"
    :close-on-esc="true"
    transform-origin="center"
    @update:show="(v) => !v && emit('toggle-detail')"
  >
    <n-card
      style="width: 600px; max-width: 90vw;"
      :bordered="false"
      size="medium"
      role="dialog"
      aria-modal="true"
      closable
      @close="emit('toggle-detail')"
    >
      <template #header>
        <div class="flex items-center gap-2">
          <n-spin v-if="!allCompleted" :size="18" />
          <n-icon v-else :component="allCompleted && statusCounts.error === 0 ? IconCheckCircle : IconCloseCircle" :color="statusCounts.error > 0 ? '#d03050' : '#18a058'" :size="20" />
          <span>{{ state.title }}</span>
        </div>
      </template>

      <!-- Overall Progress -->
      <div class="mb-4">
        <div class="mb-1 flex justify-between text-sm text-gray-500">
          <span>{{ $t("page.protocol.assignerProgress.overallProgress") }}</span>
          <span>{{ progressPercent }}%</span>
        </div>
        <n-progress
          type="line"
          :percentage="progressPercent"
          :status="allCompleted ? (statusCounts.error > 0 ? 'error' : 'success') : 'default'"
          :show-indicator="false"
          :height="8"
          :border-radius="4"
        />
      </div>

      <!-- Dependency Graph Visualization -->
      <n-scrollbar style="max-height: 400px;">
        <div class="assigner-graph">
          <template v-for="level in state.totalLevels" :key="level">
            <div class="level-row">
              <div class="level-label">
                <n-tag
                  :type="state.currentLevel >= level ? 'primary' : 'default'"
                  size="small"
                  round
                >
                  L{{ level - 1 }}
                </n-tag>
              </div>
              <div class="level-nodes">
                <div
                  v-for="node in levelGroups.get(level - 1) || []"
                  :key="node.prop"
                  class="assigner-node"
                  :class="node.status"
                >
                  <div class="node-header">
                    <n-icon
                      :component="getStatusIcon(node.status)"
                      :color="getStatusColor(node.status)"
                      :size="16"
                      :class="{ spinning: node.status === 'running' }"
                    />
                    <span class="node-name">{{ node.prop }}</span>
                  </div>
                  <div v-if="node.dependsOn.length > 0" class="node-deps">
                    <span class="deps-label">{{ $t("page.protocol.assignerProgress.dependsOn") }}:</span>
                    <span class="deps-list">{{ node.dependsOn.join(', ') }}</span>
                  </div>
                  <div v-if="node.error" class="node-error">
                    {{ node.error }}
                  </div>
                </div>
              </div>
            </div>

            <!-- Connection lines between levels -->
            <div v-if="level < state.totalLevels" class="level-connector">
              <svg width="100%" height="20" class="connector-svg">
                <line
                  x1="50%"
                  y1="0"
                  x2="50%"
                  y2="20"
                  stroke="#e0e0e0"
                  stroke-width="2"
                  stroke-dasharray="4,4"
                />
              </svg>
            </div>
          </template>
        </div>
      </n-scrollbar>

      <!-- Status Summary -->
      <div class="mt-4 flex gap-4 text-sm">
        <div class="flex items-center gap-1">
          <n-icon :component="IconTime" color="#999" :size="14" />
          <span class="text-gray-500">{{ $t("page.protocol.assignerProgress.pending") }}: {{ statusCounts.pending }}</span>
        </div>
        <div class="flex items-center gap-1">
          <n-icon :component="IconSync" color="#2080f0" :size="14" class="spinning" />
          <span class="text-blue-500">{{ $t("page.protocol.assignerProgress.running") }}: {{ statusCounts.running }}</span>
        </div>
        <div class="flex items-center gap-1">
          <n-icon :component="IconCheckCircle" color="#18a058" :size="14" />
          <span class="text-green-500">{{ $t("page.protocol.assignerProgress.completed") }}: {{ statusCounts.completed }}</span>
        </div>
        <div v-if="statusCounts.error > 0" class="flex items-center gap-1">
          <n-icon :component="IconCloseCircle" color="#d03050" :size="14" />
          <span class="text-red-500">{{ $t("page.protocol.assignerProgress.error") }}: {{ statusCounts.error }}</span>
        </div>
      </div>

      <!-- Close button when completed -->
      <div v-if="allCompleted" class="mt-4 flex justify-end">
        <n-button type="primary" @click="emit('close')">
          {{ $t("common.close") }}
        </n-button>
      </div>
    </n-card>
  </n-modal>
</template>

<style scoped>
/* Compact Progress Indicator */
.compact-progress {
  position: fixed;
  right: 16px;
  top: 80px;
  z-index: 2000;
  background: white;
  border-radius: 12px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  padding: 12px 16px;
  min-width: 180px;
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid #e8e8e8;
}

.compact-progress:hover {
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.2);
  transform: translateY(-2px);
}

.compact-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.compact-title {
  font-size: 13px;
  font-weight: 500;
  flex: 1;
}

.expand-icon {
  opacity: 0.5;
  transition: opacity 0.2s;
}

.compact-progress:hover .expand-icon {
  opacity: 1;
}

.compact-progress-bar {
  margin-bottom: 8px;
}

.compact-error {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.4;
  color: #d03050;
  white-space: pre-wrap;
  word-break: break-word;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.compact-stats {
  display: flex;
  gap: 12px;
  font-size: 12px;
}

.stat {
  display: flex;
  align-items: center;
  gap: 4px;
}

.stat.running {
  color: #2080f0;
}

.stat.completed {
  color: #18a058;
}

.stat.error {
  color: #d03050;
}

/* Slide animation */
.slide-right-enter-active,
.slide-right-leave-active {
  transition: all 0.3s ease;
}

.slide-right-enter-from,
.slide-right-leave-to {
  opacity: 0;
  transform: translateX(100px);
}

/* Detail Modal Styles */
.assigner-graph {
  padding: 8px 0;
}

.level-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.level-label {
  width: 40px;
  flex-shrink: 0;
  padding-top: 8px;
}

.level-nodes {
  flex: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.assigner-node {
  background: #f8f8f8;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 8px 12px;
  min-width: 120px;
  transition: all 0.3s ease;
}

.assigner-node.pending {
  background: #fafafa;
  border-color: #e0e0e0;
}

.assigner-node.running {
  background: #f0f7ff;
  border-color: #2080f0;
  box-shadow: 0 0 0 2px rgba(32, 128, 240, 0.1);
}

.assigner-node.completed {
  background: #f0fff4;
  border-color: #18a058;
}

.assigner-node.error {
  background: #fff0f0;
  border-color: #d03050;
}

.node-header {
  display: flex;
  align-items: center;
  gap: 6px;
}

.node-name {
  font-weight: 500;
  font-size: 13px;
}

.node-deps {
  margin-top: 4px;
  font-size: 11px;
  color: #999;
}

.deps-label {
  color: #bbb;
}

.deps-list {
  color: #666;
}

.node-error {
  margin-top: 4px;
  font-size: 11px;
  color: #d03050;
  white-space: pre-wrap;
  word-break: break-word;
}

.level-connector {
  padding-left: 52px;
}

.connector-svg {
  display: block;
}

.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
