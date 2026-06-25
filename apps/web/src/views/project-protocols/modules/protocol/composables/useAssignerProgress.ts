import type { AssignerNode, AssignerProgressState } from "../components/AssignerProgressModal.vue"
import { reactive, readonly } from "vue"

const state = reactive<AssignerProgressState>({
  visible: false,
  isDetailMode: false, // true = full modal, false = compact indicator
  title: "Assigning fields...",
  nodes: [],
  currentLevel: 0,
  totalLevels: 0,
  isCompleted: false,
})

// Track pending hide timeout to prevent race conditions between batches
let hideTimeoutId: ReturnType<typeof setTimeout> | null = null

export function useAssignerProgress() {
  function show(title?: string) {
    // Clear any pending hide timeout from previous batch
    if (hideTimeoutId !== null) {
      clearTimeout(hideTimeoutId)
      hideTimeoutId = null
    }
    state.visible = true
    state.isDetailMode = false // Start in compact mode
    state.title = title || "Assigning fields..."
    state.nodes = []
    state.currentLevel = 0
    state.totalLevels = 0
    state.isCompleted = false
  }

  function hide() {
    state.visible = false
    state.isCompleted = false
  }

  function setNodes(nodes: AssignerNode[]) {
    // Clear any pending hide timeout since we're updating nodes
    if (hideTimeoutId !== null) {
      clearTimeout(hideTimeoutId)
      hideTimeoutId = null
    }
    state.nodes = nodes
    state.totalLevels = Math.max(...nodes.map(n => n.level), -1) + 1
    // Reset completed state since we have new/updated work
    state.isCompleted = false
  }

  /**
   * Add new nodes to existing ones (for queue additions during execution)
   */
  function addNodes(nodes: AssignerNode[]) {
    // Clear any pending hide timeout since we have more work
    if (hideTimeoutId !== null) {
      clearTimeout(hideTimeoutId)
      hideTimeoutId = null
    }
    // Merge new nodes, avoiding duplicates
    for (const node of nodes) {
      const existing = state.nodes.find(n => n.prop === node.prop)
      if (!existing) {
        state.nodes.push(node)
      }
    }
    state.totalLevels = Math.max(...state.nodes.map(n => n.level), -1) + 1
    // Reset completed state since we have more work
    state.isCompleted = false
  }

  function setCurrentLevel(level: number) {
    state.currentLevel = level + 1 // 1-based for display
  }

  function updateNodeStatus(prop: string, status: AssignerNode["status"], error?: string) {
    const node = state.nodes.find(n => n.prop === prop)
    if (node) {
      node.status = status
      node.error = error
    }

    // Check if all completed
    const allDone = state.nodes.every(n => n.status === "completed" || n.status === "error")
    const hasError = state.nodes.some(n => n.status === "error")
    if (allDone) {
      state.isCompleted = true
      // Keep the progress visible when there are errors so the user can inspect them.
      if (!state.isDetailMode && !hasError) {
        // Clear any existing timeout before setting a new one
        if (hideTimeoutId !== null) {
          clearTimeout(hideTimeoutId)
        }
        hideTimeoutId = setTimeout(() => {
          if (!state.isDetailMode) {
            hide()
          }
          hideTimeoutId = null
        }, 2000)
      }
    }
  }

  function updateLevelStatus(level: number, status: AssignerNode["status"]) {
    state.nodes.forEach((node) => {
      if (node.level === level) {
        node.status = status
      }
    })
  }

  function toggleDetailMode() {
    state.isDetailMode = !state.isDetailMode
  }

  function setDetailMode(value: boolean) {
    state.isDetailMode = value
  }

  return {
    state: readonly(state),
    show,
    hide,
    setNodes,
    addNodes,
    setCurrentLevel,
    updateNodeStatus,
    updateLevelStatus,
    toggleDetailMode,
    setDetailMode,
  }
}

// Singleton instance for global access
let instance: ReturnType<typeof useAssignerProgress> | null = null

export function getAssignerProgress() {
  if (!instance) {
    instance = useAssignerProgress()
  }
  return instance
}
