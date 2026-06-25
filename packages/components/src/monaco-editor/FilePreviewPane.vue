<template>
  <n-tabs
    class="preview--light size-full flex flex-col bg-white"
    :class="[isFullScreen ? 'preview--full-screen' : '']"
    type="segment"
    :theme-overrides="{ tabFontSizeMedium: '14px', tabPaddingMediumSegment: '3px 6px', tabBorderRadius: '6px' }"
    pane-class="overflow-y-auto rounded-lg !p-3 bg-white"
    :disabled="props.disabled"
    @update-value="handleChangeMode"
  >
    <template #prefix>
      <!-- Header with file explorer path and controls -->
      <slot name="prefix" />

      <!-- File Explorer Path Input - Enhanced version -->
      <file-path-explorer class="flex-1" />
    </template>
    <template #suffix>
      <slot name="suffix" />
      <n-button quaternary size="tiny" @click="handleExpand">
        <template #icon>
          <n-icon>
            <icon-ion-arrow-shrink v-if="isFullScreen" />
            <icon-ion-arrow-expand v-else />
          </n-icon>
        </template>
      </n-button>
    </template>
    <n-tab-pane name="preview" tab="Preview" display-directive="show">
      <slot name="preview" />
    </n-tab-pane>
    <n-tab-pane name="raw" tab="Raw" display-directive="show">
      <slot name="raw" />
    </n-tab-pane>

    <!-- Content Area -->
    <!-- <div class="flex-1 overflow-y-auto rounded-lg p-3" :class="themeStore.darkMode ? 'bg-[#202327]/80' : 'bg-white'" /> -->
  </n-tabs>
</template>

<script setup lang="ts">
import { useThemeStore } from "@airalogy/composables"
import IconIonArrowExpand from "~icons/ion/arrow-expand"
import IconIonArrowShrink from "~icons/ion/arrow-shrink"
import { NButton, NIcon } from "naive-ui"
import FilePathExplorer from "./FilePathExplorer.vue"
import { useFilePreviewStore } from "./store/filePreviewStore"

interface Props {
  isFullScreen?: boolean
  isPreviewMode?: boolean
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isFullScreen: false,
  isPreviewMode: true,
  disabled: false,
})

const emit = defineEmits<{
  (e: "update:isFullScreen", val: boolean): void
  (e: "update:isPreviewMode", val: boolean): void
  (e: "openPreviewAsText",): void
}>()

// Store instances
const themeStore = useThemeStore()
const filePreviewStore = useFilePreviewStore()

function handleChangeMode(val: string) {
  emit("update:isPreviewMode", val === "preview")
}

function handleExpand() {
  emit("update:isFullScreen", !props.isFullScreen)
}

function handleOpenPreviewAsText() {
  emit("openPreviewAsText")
}
</script>

<style scoped lang="sass">
.preview--full-screen
  position: absolute
  top: 0
  left: 0
  right: 0
  bottom: 0
  z-index: 1000

:deep(.preview--dark .n-tabs-nav)
  background-color: rgb(32 35 39 / 0.8)

:deep(.n-tabs-nav)
  background:#f5f5f5
  @apply h-8 flex items-center justify-between gap-x-2 px-2

:deep(.n-tabs-nav__prefix)
  @apply gap-x-2 flex-grow-1 !p-0

:deep(.n-tabs-nav__suffix)
  @apply gap-x-2 !p-0

:deep(.n-tabs-rail)
  width: fit-content!important
  height: 2rem
  padding: 3px
</style>
