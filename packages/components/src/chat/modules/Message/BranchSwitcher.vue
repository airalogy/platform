<template>
  <div
    v-if="totalBranches > 1"
    class="flex items-center justify-end gap-1 text-xs"
  >
    <n-button
      :disabled="currentBranchIndex <= 0"
      quaternary
      size="tiny"
      @click="handlePreviousBranch"
    >
      <template #icon>
        <n-icon size="12">
          <icon-ion-chevron-back />
        </n-icon>
      </template>
    </n-button>

    <span class="mx-2 whitespace-nowrap">
      {{ currentBranchIndex + 1 }} / {{ totalBranches }}
    </span>

    <n-button
      :disabled="currentBranchIndex >= totalBranches - 1"
      quaternary
      size="tiny"
      @click="handleNextBranch"
    >
      <template #icon>
        <n-icon size="12">
          <icon-ion-chevron-forward />
        </n-icon>
      </template>
    </n-button>
  </div>
</template>

<script setup lang="ts">
import IconIonChevronBack from "~icons/ion/chevron-back"
import IconIonChevronForward from "~icons/ion/chevron-forward"
import { NButton, NIcon } from "naive-ui"

interface Props {
  branches?: Chat.ChatMessage[]
  activeBranchIndex?: number
}

interface Emit {
  (ev: "switchBranch", branch: Chat.ChatMessage, branchIndex: number): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emit>()

// Branch navigation computed properties
const totalBranches = computed(() => {
  return (props.branches?.length || 1)
})

const currentBranchIndex = computed(() => {
  return props.activeBranchIndex || 0
})

// Branch navigation functions
function handlePreviousBranch() {
  if (!props.branches || currentBranchIndex.value <= 0) {
    return
  }

  const previousBranchIndex = currentBranchIndex.value - 1
  const previousBranch = props.branches[previousBranchIndex]
  if (previousBranch) {
    emit("switchBranch", previousBranch, previousBranchIndex)
  }
}

function handleNextBranch() {
  if (!props.branches || currentBranchIndex.value >= props.branches.length - 1) {
    return
  }

  const nextBranchIndex = currentBranchIndex.value + 1
  const nextBranch = props.branches[nextBranchIndex]
  if (nextBranch) {
    emit("switchBranch", nextBranch, nextBranchIndex)
  }
}
</script>
