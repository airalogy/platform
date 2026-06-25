<template>
  <div class="shiki-viewer">
    <n-spin :show="isLoading" size="small" stroke="#fff">
      <div
        ref="contentRef"
        class="shiki-viewer__content min-h-20"
        :class="{ 'shiki-viewer__content--collapsed': isCollapsed && shouldShowMoreButton }"
        :style="{ maxHeight: isCollapsed ? `${maxHeight}px` : 'none' }"
      >
        <slot />
      </div>
    </n-spin>

    <n-button
      v-if="shouldShowMoreButton"
      size="small"
      class="shiki-viewer__button"
      :theme-overrides="buttonThemeOverrides"
      quaternary
      @click="toggleCollapse"
    >
      <template #icon>
        <n-icon :theme-overrides="iconThemeOverrides">
          <icon-tabler-chevron-down v-if="isCollapsed" />
          <icon-tabler-chevron-up v-else />
        </n-icon>
      </template>
      {{ isCollapsed ? 'Show More' : 'Show Less' }}
    </n-button>
  </div>
</template>

<script setup lang="ts">
import type { GlobalThemeOverrides } from "naive-ui"

const props = withDefaults(defineProps<{
  isLoading: boolean
  maxHeight?: number
  defaultCollapsed?: boolean
}>(), {
  maxHeight: 300,
  defaultCollapsed: true,
})

const isCollapsed = ref(props.defaultCollapsed)
const contentHeight = ref(0)

const shouldShowMoreButton = computed(() => {
  return contentHeight.value > props.maxHeight
})

function toggleCollapse() {
  isCollapsed.value = !isCollapsed.value
}

const contentRef = ref<HTMLElement | null>(null)

// Measure content height after content updates
watch(() => props.isLoading, async (newLoading) => {
  if (newLoading) {
    return
  }
  const el = unrefElement(contentRef)
  if (el) {
    contentHeight.value = el.scrollHeight
  }
}, { immediate: true })

// Add button theme overrides
const buttonThemeOverrides: GlobalThemeOverrides["Button"] = {
  heightSmall: "28px",
  fontSizeSmall: "0.85rem",
  color: "#2f363d",
  colorHover: "#444d56",
  colorQuaternary: "#2f363d",
  colorQuaternaryHover: "#444d56",
  textColor: "#d1d5da",
  textColorHover: "#d1d5da",
  border: "1px solid #444d56",
  borderHover: "1px solid #586069",
  iconMargin: "4px",
  iconSizeSmall: "1rem",
  padding: "2px 12px",
}

// Add icon theme overrides
const iconThemeOverrides: GlobalThemeOverrides["Icon"] = {
  color: "#6a737d",
  colorHover: "#959da5",
}
</script>

<style lang="sass" scoped>
.shiki-viewer
  border-radius: 0.5rem
  overflow: hidden
  position: relative
  border: 1px solid #1b1f23
  background: #24292e

  &__content
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1)

    :deep(.shiki)
      margin: 0
      padding: 1.25rem 0
      font-family: 'Fira Code', monospace
      font-size: 0.9rem
      line-height: 1.5
      overflow-x: auto
      counter-reset: line
      &::-webkit-scrollbar
        height: 8px
        background-color: rgba(0, 0, 0, 0.1)

      &::-webkit-scrollbar-thumb
        background-color: rgba(255, 255, 255, 0.2)
        border-radius: 4px

        &:hover
          background-color: rgba(255, 255, 255, 0.3)

      .line
        display: inline-block
        width: 100%
        padding-left: 1rem

        &::before
          counter-increment: line
          content: counter(line)
          display: inline-block
          width: 1.5rem
          margin-right: 1rem
          text-align: right
          color: #6a737d
          user-select: none

    &--collapsed
      overflow: hidden
      mask-image: linear-gradient(to bottom, black 85%, transparent 100%)

  &__button
    position: absolute
    bottom: 8px
    left: 50%
    transform: translateX(-50%)
    z-index: 1
    display: flex
    align-items: center
</style>
