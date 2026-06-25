<template>
  <div class="audio-player flex items-center gap-2 border rounded bg-gray-50 p-2" :class="sizeClasses">
    <audio
      ref="audioRef"
      :src="props.audioUrl"
      @loadeddata="handleAudioLoad"
      @loadedmetadata="handleAudioLoad"
      @timeupdate="handleTimeUpdate"
      @ended="handleEnded"
      @durationchange="handleDurationChange"
    />

    <div class="w-full flex items-center gap-2">
      <n-button circle :size="buttonSize" @click="togglePlay">
        <template #icon>
          <n-icon>
            <svg v-if="isPlaying" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
              <path fill="currentColor" d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" />
            </svg>
            <svg v-else xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
              <path fill="currentColor" d="M8 5v14l11-7z" />
            </svg>
          </n-icon>
        </template>
      </n-button>

      <span class="text-sm" :class="timeClasses">{{ currentTimeFormatted }} / {{ durationFormatted }}</span>

      <div class="flex-1">
        <n-slider
          :value="progress"
          :step="0.1"
          :max="100"
          :format-tooltip="formatTooltip"
          @update:value="handleSeek"
        />
      </div>

      <slot name="actions" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { NButton, NIcon, NSlider } from "naive-ui"
import { computed } from "vue"
import { useAudioPlayer } from "../composables/useAudioPlayer"

interface Props {
  audioUrl: string
  size?: "small" | "medium" | "large"
}

const props = withDefaults(defineProps<Props>(), {
  size: "medium",
})

const buttonSize = computed(() => {
  switch (props.size) {
    case "small": return "tiny"
    case "large": return "medium"
    default: return "small"
  }
})

const sizeClasses = computed(() => ({
  "h-10": props.size === "small",
  "h-[50px]": props.size === "medium",
  "h-16": props.size === "large",
}))

const timeClasses = computed(() => ({
  "min-w-[60px]": props.size === "small",
  "min-w-[70px]": props.size === "medium",
  "min-w-[80px]": props.size === "large",
}))

const {
  audioRef,
  isPlaying,
  currentTimeFormatted,
  durationFormatted,
  progress,
  formatTooltip,
  togglePlay,
  handleTimeUpdate,
  handleAudioLoad,
  handleEnded,
  handleSeek,
  handleDurationChange,
} = useAudioPlayer()
</script>

<style lang="sass" scoped>
.audio-player
  width: 100%
  border-radius: 8px
  transition: all 0.3s ease

:deep(.n-slider)
  width: 100%
  min-width: 150px
  .n-slider-rail
    background-color: rgba(128, 128, 128, 0.2)
  .n-slider-fill
    background-color: var(--primary-color)
  .n-slider-handle
    width: 10px
    height: 10px
    background-color: var(--primary-color)
    &:hover
      box-shadow: 0 0 0 4px rgba(var(--primary-color-rgb), 0.2)
</style>
