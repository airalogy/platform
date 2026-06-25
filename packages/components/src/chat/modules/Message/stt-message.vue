<template>
  <div class="flex flex-col gap-2" :class="[inversion ? 'ml-auto' : 'mr-auto']">
    <div class="relative ml-auto w-fit flex items-center rounded-lg bg-gray-100 p-3 text-sm text-gray-600">
      <span v-if="done" class="absolute left-2 rounded bg-blue-100 px-1 text-xs text-blue-600 -top-2">
        Transcription
      </span>
      <span v-if="done" class="w-fit">{{ text }}</span>
      <span v-else>Transcribing...</span>
      <n-button
        quaternary
        size="tiny"
        class="ml-2 shrink-0"
        @click="toggleAudio"
      >
        <template #icon>
          <icon-mage-sound-waves v-if="!isExpanded" />
          <icon-material-symbols-close v-else />
        </template>
      </n-button>
    </div>
    <div v-show="isExpanded" class="transition-all duration-300">
      <audio-player
        :audio-url="audioUrl"
        size="small"
        button-size="tiny"
        @play-end="handlePlayEnd"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import AudioPlayer from "../AudioPlayer.vue"

interface Props {
  text?: string
  audioUrl: string
  inversion?: boolean
  done?: boolean
}

defineProps<Props>()

const isExpanded = ref(false)

function toggleAudio() {
  isExpanded.value = !isExpanded.value
}

function handlePlayEnd() {
  isExpanded.value = false
}
</script>
