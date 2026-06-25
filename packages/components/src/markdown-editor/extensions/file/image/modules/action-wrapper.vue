<template>
  <div
    class="[backdrop-filter:saturate(1.8)_blur(20px)] absolute right-3 top-3 flex flex-row border-[0.5px] rounded bg-[var(--mt-bg-secondary)] px-0.5"
    :class="[
      modelValue ? 'opacity-100' : 'opacity-0 group-hover/node-image:opacity-100',
    ]"
  >
    <slot />
  </div>
</template>

<script setup lang="ts">
defineProps<{
  modelValue?: boolean
}>()
</script>
