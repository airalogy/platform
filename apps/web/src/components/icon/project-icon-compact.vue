<template>
  <n-icon size="18" :color="props.color">
    <svg width="18" height="18" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M13.2 3.6H4.8a1.2 1.2 0 00-1.2 1.2v8.4a1.2 1.2 0 001.2 1.2h8.4a1.2 1.2 0 001.2-1.2V4.8a1.2 1.2 0 00-1.2-1.2zM3.6 7.2h10.8M7.2 14.4V7.2"
        stroke="#9A9A9A"
        stroke-width="1.2"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    </svg>
  </n-icon>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{ color?: string }>(), { color: "white" })
</script>

<style scoped></style>
