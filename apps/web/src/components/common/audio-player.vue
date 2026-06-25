<template>
  <n-flex vertical class="audio-player" :style="{ flexBasis: compact ? 'unset' : '100%' }">
    <audio ref="audioRef" preload="metadata" />
    <n-flex align="center" flex>
      <n-button
        :secondary="!playing"
        :type="error ? 'error' : 'primary'"
        :focusable="false"
        :disabled="waiting || error"
        :loading="waiting && !error"
        :title="compact ? caption : undefined"
        @click="playPause"
      >
        <template #icon>
          <n-icon v-if="error" :component="ErrorIcon" />
          <n-icon v-else-if="playing" :component="PauseIcon" />
          <n-icon v-else :component="PlayIcon" />
        </template>
      </n-button>
      <div v-if="!compact" class="text-tiny">
        {{ currentTimeString }} / {{ durationString }}
      </div>
      <n-flex
        v-if="!compact"
        align="center"
        :wrap="false"
        style="width: auto; flex-grow: 2; flex-basis: 200px"
      >
        <n-slider
          v-model:value="currentTime"
          :step="1"
          :min="0"
          :max="duration"
          :format-tooltip="(seconds: number) => secondsToTimeString(seconds)"
          :disabled="error"
          style="width: auto; flex-grow: 2; flex-basis: 200px"
        />
        <n-button
          v-if="externalLink"
          quaternary
          circle
          size="small"
          :focusable="false"
          @click="openTab(externalLink!)"
        >
          <template #icon>
            <n-icon :component="LinkIcon" />
          </template>
        </n-button>
        <n-button
          quaternary
          circle
          size="small"
          :focusable="false"
          :disabled="error"
          @click="download"
        >
          <template #icon>
            <n-icon :component="DownloadIcon" />
          </template>
        </n-button>
      </n-flex>
    </n-flex>
    <div
      v-if="caption && !compact"
      class="text-tiny caption translucent"
      :class="{ translucent: error }"
      :style="fontStyle"
    >
      {{ caption }}
    </div>
  </n-flex>
</template>

<script setup lang="ts">
import { useClosableMessage } from "@airalogy/composables"
import { useMediaControls } from "@vueuse/core"
import DownloadIcon from "~icons/ion/download"
import ErrorIcon from "~icons/ion/error"
import LinkIcon from "~icons/ion/link"

import PauseIcon from "~icons/ion/pause"
import PlayIcon from "~icons/ion/play"
import { NButton, NFlex, NIcon, NSlider } from "naive-ui"
import { onMounted, watch } from "vue"
import { computed, type CSSProperties, ref } from "vue"

interface IProps {
  src: string
  externalLink?: string
  caption?: string
  instanceId?: string
  fontStyle?: CSSProperties
  compact?: boolean
}

const props = defineProps<IProps>()

const emit = defineEmits(["play", "ended"])
defineExpose({ play, pause })
const message = useClosableMessage()

const audioRef = ref<HTMLAudioElement>()
const error = ref(false)
const { playing, waiting, currentTime, duration, ended, onSourceError } = useMediaControls(
  audioRef,
  {
    src: props.src,
  },
)

function secondsToTimeString(seconds: number) {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${`${s}`.padStart(2, "0")}`
}

const currentTimeString = computed(() => secondsToTimeString(currentTime.value || 0))
const durationString = computed(() => secondsToTimeString(duration.value || 0))

function playPause() {
  !playing.value ? play() : pause()
}

function play(reset?: boolean) {
  reset && (currentTime.value = 0)
  playing.value = true
  emit("play", props.instanceId)
}

function pause() {
  playing.value = false
}

function download() {
  window.open(props.src, "_blank", "noopener noreferrer")
}

function openTab(url: string) {
  window.open(url, "_blank", "noopener noreferrer")
}

watch(ended, (after) => {
  after && emit("ended", props.instanceId)
})

onMounted(() => {
  onSourceError(() => {
    playing.value = false
    error.value = true
    message.error("Failed to load audio")
  })
})
</script>

<style scoped>
.audio-player {
  padding: 8px 0;
}
.caption {
  white-space: pre-wrap;
}
</style>
