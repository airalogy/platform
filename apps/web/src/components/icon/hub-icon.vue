<template>
  <n-icon :size="props.size" :color="props.color">
    <icon-local-hub />
  </n-icon>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{ color?: string, size?: number }>(), { color: "white", size: 40 })
</script>

<style scoped></style>
