<template>
  <div
    :ref="(el) => setPageRef(el, pageNumber)"
    class="page-container flex justify-center"
    :style="{ minHeight: `${pageHeight}px` }"
  >
    <canvas
      v-show="isLoaded"
      :ref="(el) => setCanvasRef(el, pageNumber)"
      class="border border-gray-300 shadow-sm"
    />
    <div
      v-show="!isLoaded"
      class="flex items-center justify-center border border-gray-300 bg-gray-50 shadow-sm"
      :style="{ width: `${pageWidth}px`, height: `${pageHeight}px` }"
    >
      <div v-if="isLoading" class="text-center">
        <div class="mb-2">
          <n-icon size="24" class="animate-spin">
            <icon-ion-refresh />
          </n-icon>
        </div>
        <div class="text-sm text-gray-500">
          Loading page {{ pageNumber }}...
        </div>
      </div>
      <div v-else class="text-sm text-gray-400">
        Page {{ pageNumber }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import IconIonRefresh from "~icons/ion/refresh"
import { NIcon } from "naive-ui"

interface Props {
  pageNumber: number
  pageWidth: number
  pageHeight: number
  isLoaded: boolean
  isLoading: boolean
  setPageRef: (el: any, pageNum: number) => void
  setCanvasRef: (el: any, pageNum: number) => void
}

defineProps<Props>()
</script>

<style scoped lang="sass">
.page-container
  transition: min-height 0.2s ease
</style>
