<template>
  <div ref="parentElement" class="relative">
    <div
      :style="contentStyles"
      class="left-0 right-0"
    >
      <slot name="prefix" v-bind="{ position, contentHeight, contentTop, contentLeft, width, left }" />
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useElementBounding, useWindowSize } from "@vueuse/core"
import { computed, ref } from "vue"

interface IProps {
  containerRef?: HTMLElement | null
  offset?: number
  bottom?: number
  height?: number
  fullHeight?: boolean
  floating?: boolean
}

const props = withDefaults(defineProps<IProps>(), {
  containerRef: null,
  offset: 0,
  bottom: 0,
  floating: false,
})

const emit = defineEmits<IEmits>()
interface IEmits {
  (e: "update:height", height: number): void
  (e: "update:top", top: number): void
}
const parentElement = ref<HTMLElement | null>(null)
const { top, bottom, width, left } = useElementBounding(parentElement)

const { height: windowHeight } = useWindowSize()
const fixedHeight = computed(() => Math.floor(windowHeight.value - props.offset))

// const stickyStyle = reactive<Record<string, any>>({
//   position: "absolute",
//   left: 0,
//   top: 0,
//   right: 0,
//   height: 0,
// })

const contentStyles = computed(() => {
  if (!parentElement.value) {
    return {
      position: "absolute" as const,
      height: "0px",
    }
  }

  const isFixed = top.value < 0 || props.floating

  if (isFixed) {
    // Fixed positioning - include all positioning properties
    let height: number
    if (props.floating) {
      height = fixedHeight.value
    }
    else if (bottom.value >= windowHeight.value) {
      height = fixedHeight.value
    }
    else {
      height = Math.floor(bottom.value - props.offset)
    }

    return {
      position: "fixed" as const,
      height: `${height}px`,
      top: "0px",
      left: `${left.value}px`,
      width: `${width.value}px`,
    }
  }
  else {
    // Absolute positioning - minimal properties needed
    const newHeight = bottom.value - top.value - props.offset
    let height: number
    if (newHeight > 0 && bottom.value <= windowHeight.value) {
      height = newHeight
    }
    else {
      height = Math.floor(windowHeight.value - top.value - props.offset)
    }

    return {
      position: "absolute" as const,
      height: `${height}px`,
    }
  }
})

// Individual computed properties for slot bindings
const position = computed(() => contentStyles.value.position)
const contentHeight = computed(() => Number.parseInt(contentStyles.value.height))
const contentTop = computed(() => Number.parseInt((contentStyles.value as any).top || "0"))
const contentLeft = computed(() => Number.parseInt((contentStyles.value as any).left || "0"))
</script>
