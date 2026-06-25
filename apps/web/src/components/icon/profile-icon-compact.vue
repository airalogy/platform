<template>
  <n-icon size="18" :color="props.color">
    <svg width="18" height="18" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M12 14.4v-1.2a2.4 2.4 0 00-2.4-2.4H4.8a2.4 2.4 0 00-2.4 2.4v1.2M7.2 8.4a2.4 2.4 0 100-4.8 2.4 2.4 0 000 4.8zM15.6 14.4v-1.2a2.4 2.4 0 00-1.8-2.322M11.4 3.678a2.4 2.4 0 010 4.65"
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
