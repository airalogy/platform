<template>
  <div v-if="isRecording || isProcessing" class="flex items-center gap-3 rounded-lg bg-gray-50 px-4 py-3" :class="className">
    <n-spin v-if="isProcessing" size="small" />
    <n-icon v-else :size="20" color="#e63946" class="animate-pulse">
      <icon-tabler-microphone />
    </n-icon>
    <span class="text-sm text-gray-600">
      {{ isProcessing ? processingText : `${recordingText} ${formatDuration(recordingDuration)}` }}
    </span>
  </div>
</template>

<script setup lang="ts">
import IconTablerMicrophone from "~icons/tabler/microphone"
import { NIcon, NSpin } from "naive-ui"

interface Props {
  isRecording: boolean
  isProcessing: boolean
  recordingDuration: number
  recordingText?: string
  processingText?: string
  className?: string
}

const props = withDefaults(defineProps<Props>(), {
  recordingText: "Recording...",
  processingText: "Processing audio...",
  className: "",
})

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins}:${secs.toString().padStart(2, "0")}`
}
</script>

<style lang="sass" scoped>
.animate-pulse
  animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite

@keyframes pulse
  0%, 100%
    opacity: 1
  50%
    opacity: 0.3
</style>
