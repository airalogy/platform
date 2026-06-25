<template>
  <n-card
    size="small" bordered
    :content-class="['overflow-auto !flex-auto !min-w-full min-h-8', collapsed ? 'hidden' : 'resize', props.contentClass || ''].join(' ')"
    :content-style="contentStyle"
  >
    <template #header>
      <div class="w-full flex items-center justify-between overflow-hidden">
        <div class="flex items-center gap-2 overflow-hidden">
          <n-icon :size="16">
            <icon-material-symbols-iframe-outline />
          </n-icon>
          <n-tooltip v-if="$slots.title || props.contentProps.src" trigger="hover">
            <template #trigger>
              <!-- <span class="min-w-10 text-sm font-medium">{{ props.contentProps.src }}</span> -->
              <span class="shrink-1 ellipsis-text">
                <slot name="title">
                  {{ props.contentProps.src }}
                </slot>
              </span>
            </template>
            <copy-to-clip :text="props.contentProps.src || props.tooltip" show-success color="#ffffff" />
          </n-tooltip>
        </div>

        <div class="flex items-center gap-2">
          <n-button v-if="props.contentProps.src" size="small" quaternary @click="handleOpenExternal">
            <template #icon>
              <n-icon><icon-ion-open-outline /></n-icon>
            </template>
            Open in Tab
          </n-button>
        </div>
      </div>
    </template>
    <template #header-extra>
      <n-button
        size="small"
        quaternary
        :aria-label="collapsed ? 'Expand preview' : 'Collapse preview'"
        @click="handleToggleCollapse"
      >
        <template #icon>
          <n-icon>
            <icon-ion-chevron-forward-outline v-if="collapsed" />
            <icon-ion-chevron-down-outline v-else />
          </n-icon>
        </template>
      </n-button>
    </template>
    <div class="embedded__wrapper">
      <component :is="props.component" v-bind="props.contentProps" ref="contentRef" class="embedded__content" />
    </div>
  </n-card>
</template>

<script setup lang="ts">
import type { Component, IframeHTMLAttributes } from "vue"
import CopyToClip from "@airalogy/components/copy-to-clip.vue"
import { useBoolean } from "@airalogy/composables"

interface IProps {
  contentProps: Partial<IframeHTMLAttributes>
  contentClass?: any
  contentStyle?: any
  collapsed?: boolean
  component: string | Component
  tooltip?: string
}
const props = withDefaults(defineProps<IProps>(), {
  collapsed: false,
  tooltip: "",
})

const contentRef = ref<HTMLIFrameElement>()

const { bool: collapsed, toggle: handleToggleCollapse } = useBoolean(props.collapsed)

function handleOpenExternal() {
  if (props.contentProps.src) {
    window.open(props.contentProps.src, "_blank")
  }
}

defineExpose({
  content: contentRef,
})
</script>

<style scoped lang="sass">
@use "sass:math"
@use "@styles/sass/mixins.sass" as *

.embedded
  &__wrapper
    @apply relative size-full overflow-hidden
    @include aspect-ratio(math.div(16, 9))

:deep(.embedded__content)
  @apply absolute-lt size-full
</style>
