<template>
  <n-icon size="20" :color="props.color">
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
      <g opacity="0.6">
        <path
          d="M9.23099 15.3846C12.6297 15.3846 15.3848 12.6294 15.3848 9.23075C15.3848 5.83207 12.6297 3.0769 9.23099 3.0769C5.83232 3.0769 3.07715 5.83207 3.07715 9.23075C3.07715 12.6294 5.83232 15.3846 9.23099 15.3846Z"
          :stroke="props.color"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
        <path
          d="M16.9233 16.9231L13.5771 13.5769"
          :stroke="props.color"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </g>
    </svg>
  </n-icon>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{ color?: string }>(), { color: "white" })
</script>

<style scoped></style>
