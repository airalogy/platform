<template>
  <div class="timer" :class="[{ 'timer--circle': !isExpanded }]" :style="{ width: computedSize, height: computedSize }">
    <div v-if="isExpanded">
      <div>{{ formattedTime }}</div>
      <n-input v-model:value="durationInput" placeholder="Enter duration (e.g., PT1H30M)" />
      <tooltip-button tooltip="Set the timer duration" @click="setTimer">
        Set
      </tooltip-button>
      <tooltip-button tooltip="Start the timer" @click="startTimer">
        Start
      </tooltip-button>
      <tooltip-button tooltip="Pause the timer" @click="pauseTimer">
        Pause
      </tooltip-button>
      <tooltip-button tooltip="Reset the timer" @click="resetTimer">
        Reset
      </tooltip-button>
    </div>
    <div v-else>
      <div>{{ remainingTime }}</div>
    </div>
    <tooltip-button :tooltip="isExpanded ? 'Collapse the timer view' : 'Expand the timer view'" @click="toggleView">
      {{ isExpanded ? 'Collapse' : 'Expand' }}
    </tooltip-button>
  </div>
</template>

<script setup lang="ts">
import { NInput } from "naive-ui"
import { computed, defineProps, ref } from "vue"
import TooltipButton from "./tooltip-button.vue"

interface TimerState {
  isRunning: boolean
  isPaused: boolean
  duration: number // in seconds
  remaining: number // in seconds
}

const props = defineProps<{ size?: "small" | "normal" | "large" }>()

const sizeMap = {
  small: "100px",
  normal: "150px",
  large: "200px",
} as const

const computedSize = computed(() => sizeMap[props.size || "normal"])

const timerState = ref<TimerState>({
  isRunning: false,
  isPaused: false,
  duration: 0,
  remaining: 0,
})

const isExpanded = ref(true)
const durationInput = ref("")

const formattedTime = computed(() => {
  const hours = Math.floor(timerState.value.remaining / 3600)
  const minutes = Math.floor((timerState.value.remaining % 3600) / 60)
  const seconds = timerState.value.remaining % 60
  return `${hours}h ${minutes}m ${seconds}s`
})

const remainingTime = computed(() => `${timerState.value.remaining}s`)

function parseDuration(input: string): number {
  // Simple ISO 8601 duration parsing (e.g., PT1H30M)
  const match = input.match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/)
  if (!match)
    return 0
  const hours = Number.parseInt(match[1] || "0", 10)
  const minutes = Number.parseInt(match[2] || "0", 10)
  const seconds = Number.parseInt(match[3] || "0", 10)
  return hours * 3600 + minutes * 60 + seconds
}

function setTimer() {
  timerState.value.duration = parseDuration(durationInput.value)
  timerState.value.remaining = timerState.value.duration
}

function startTimer() {
  if (timerState.value.isRunning)
    return
  timerState.value.isRunning = true
  timerState.value.isPaused = false
  // Start timer logic here
}

function pauseTimer() {
  if (!timerState.value.isRunning || timerState.value.isPaused)
    return
  timerState.value.isPaused = true
  // Pause timer logic here
}

function resetTimer() {
  timerState.value.isRunning = false
  timerState.value.isPaused = false
  timerState.value.remaining = timerState.value.duration
}

function toggleView() {
  isExpanded.value = !isExpanded.value
}
</script>

<style scoped>
.timer {
  display: flex;
  flex-direction: column;
  align-items: center;
  transition: all 0.3s ease;
}

.timer--circle {
  border-radius: 50%;
  justify-content: center;
  overflow: hidden;
}
</style>
