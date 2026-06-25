<template>
  <tooltip-button
    :icon="MicrophoneIcon"
    :tooltip="isRecording ? stopTooltip : startTooltip"
    :button-props="{
      quaternary: true,
      type: isRecording ? 'error' : 'default',
      size: buttonSize,
      themeOverrides: {
        heightSmall: 'fit-content',
        paddingSmall: '8px',
        borderRadiusSmall: '8px',
      },
      ...buttonProps,
    }"
    :icon-props="{ size: iconSize, ...iconProps, class: 'thin-icon' }"
    :class="{ 'animate-pulse': isRecording }"
    @click="handleVoiceClick"
  />
</template>

<script setup lang="ts">
import type { ButtonProps, IconProps } from "naive-ui"
import MicrophoneIcon from "~icons/tabler/microphone"
import { useChatInfoStore } from "../../composables/useChatInfoStore"

interface Props {
  startTooltip?: string
  stopTooltip?: string
  buttonSize?: "tiny" | "small" | "medium" | "large"
  iconSize?: number
  buttonProps?: Partial<ButtonProps>
  iconProps?: Partial<IconProps>
}

const props = withDefaults(defineProps<Props>(), {
  startTooltip: "Start Voice Recording",
  stopTooltip: "Recording... Click to stop",
  buttonSize: "small",
  iconSize: 20,
})

const emit = defineEmits<{
  (e: "recordingStopped"): void
}>()

const { isRecording, startRecording, stopRecording } = useChatInfoStore()!

async function handleVoiceClick() {
  if (isRecording.value) {
    await stopRecording()
    emit("recordingStopped")
  }
  else {
    await startRecording()
  }
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

<style>
.thin-icon svg {
  color: currentColor;
}
.thin-icon svg * {
  stroke-width: 1.5 !important;
}
</style>
