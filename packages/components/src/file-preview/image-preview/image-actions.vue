<template>
  <div class="flex items-center gap-1 rounded-lg bg-white bg-opacity-90 p-2 shadow-lg backdrop-blur-sm">
    <!-- Rotate Counterclockwise -->
    <n-popover trigger="hover" placement="top" :delay="300">
      <template #trigger>
        <n-button
          circle
          size="small"
          quaternary
          @click="$emit('rotateCounterclockwise')"
        >
          <template #icon>
            <n-icon :size="16" class="rotate-180 transform">
              <icon-ion-refresh-outline />
            </n-icon>
          </template>
        </n-button>
      </template>
      <div class="text-center">
        <div class="font-medium">
          Rotate Left
        </div>
        <div class="mt-1 text-xs text-gray-500">
          Rotate counterclockwise
        </div>
      </div>
    </n-popover>

    <!-- Rotate Clockwise -->
    <n-popover trigger="hover" placement="top" :delay="300">
      <template #trigger>
        <n-button
          circle
          size="small"
          quaternary
          @click="$emit('rotateClockwise')"
        >
          <template #icon>
            <n-icon :size="16">
              <icon-ion-refresh-outline />
            </n-icon>
          </template>
        </n-button>
      </template>
      <div class="text-center">
        <div class="font-medium">
          Rotate Right
        </div>
        <div class="mt-1 text-xs text-gray-500">
          Rotate clockwise
        </div>
      </div>
    </n-popover>

    <!-- Zoom Out -->
    <n-popover trigger="hover" placement="top" :delay="300">
      <template #trigger>
        <n-button
          circle
          size="small"
          quaternary
          @click="$emit('zoomOut')"
        >
          <template #icon>
            <n-icon :size="16">
              <icon-ion-remove-outline />
            </n-icon>
          </template>
        </n-button>
      </template>
      <div class="text-center">
        <div class="font-medium">
          Zoom Out
        </div>
        <div class="mt-1 text-xs text-gray-500">
          <span class="kbd">-</span> or <span class="kbd">Wheel ↓</span>
        </div>
      </div>
    </n-popover>

    <!-- Reset Size -->
    <n-popover trigger="hover" placement="top" :delay="300">
      <template #trigger>
        <n-button
          circle
          size="small"
          quaternary
          @click="$emit('resetSize')"
        >
          <template #icon>
            <n-icon :size="16">
              <icon-ion-resize-outline />
            </n-icon>
          </template>
        </n-button>
      </template>
      <div class="text-center">
        <div class="font-medium">
          Fit
        </div>
        <div class="mt-1 text-xs text-gray-500">
          <span class="kbd">0</span>
        </div>
      </div>
    </n-popover>

    <!-- Zoom In -->
    <n-popover trigger="hover" placement="top" :delay="300">
      <template #trigger>
        <n-button
          circle
          size="small"
          quaternary
          @click="$emit('zoomIn')"
        >
          <template #icon>
            <n-icon :size="16">
              <icon-ion-add-outline />
            </n-icon>
          </template>
        </n-button>
      </template>
      <div class="text-center">
        <div class="font-medium">
          Zoom In
        </div>
        <div class="mt-1 text-xs text-gray-500">
          <span class="kbd">+</span> or <span class="kbd">Wheel ↑</span>
        </div>
      </div>
    </n-popover>

    <!-- Download -->
    <n-popover v-if="showDownload" trigger="hover" placement="top" :delay="300">
      <template #trigger>
        <n-button
          circle
          size="small"
          quaternary
          @click="$emit('download')"
        >
          <template #icon>
            <n-icon :size="16">
              <icon-ion-download-outline />
            </n-icon>
          </template>
        </n-button>
      </template>
      <div class="text-center">
        <div class="font-medium">
          Download Image
        </div>
        <div class="mt-1 text-xs text-gray-500">
          Save image to device
        </div>
      </div>
    </n-popover>
  </div>
</template>

<script setup lang="ts">
import { NButton, NIcon, NPopover } from "naive-ui"

// Icons
import IconIonAddOutline from "~icons/ion/add-outline"
import IconIonDownloadOutline from "~icons/ion/download-outline"
import IconIonRefreshOutline from "~icons/ion/refresh-outline"
import IconIonRemoveOutline from "~icons/ion/remove-outline"
import IconIonResizeOutline from "~icons/ion/resize-outline"

interface Props {
  showDownload?: boolean
}

interface Emits {
  (e: "rotateCounterclockwise"): void
  (e: "rotateClockwise"): void
  (e: "zoomOut"): void
  (e: "resetSize"): void
  (e: "zoomIn"): void
  (e: "download"): void
}

const props = withDefaults(defineProps<Props>(), {
  showDownload: true,
})

const emit = defineEmits<Emits>()
</script>

<style scoped lang="sass">
.kbd
  display: inline-block
  padding: 2px 4px
  font-size: 10px
  font-family: monospace
  color: #374151
  background-color: #f3f4f6
  border: 1px solid #d1d5db
  border-radius: 3px
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1)
  font-weight: 600
  text-transform: uppercase
  letter-spacing: 0.5px

.dark .kbd
  color: #d1d5db
  background-color: #374151
  border-color: #6b7280
</style>
