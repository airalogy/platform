<template>
  <div :class="classes">
    <slot />
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue"

interface Props {
  isResizing?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isResizing: false,
})

const classes = computed(() => [
  "absolute top-1/2 h-10 max-h-full w-1.5 -translate-y-1/2 transform cursor-col-resize rounded border border-solid border-[var(--mt-transparent-foreground)] bg-[var(--mt-bg-secondary)] p-px transition-all",
  "opacity-0 [backdrop-filter:saturate(1.8)_blur(20px)]",
  {
    "opacity-80": props.isResizing,
    "group-hover:opacity-80": !props.isResizing,
  },
  "before:absolute before:inset-y-0 before:-left-1 before:-right-1",
])
</script>
