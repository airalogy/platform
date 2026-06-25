<template>
  <n-icon size="40" :color="props.color">
    <icon-local-lab />
  </n-icon>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{ color?: string }>(), { color: "white" })
</script>

<style scoped></style>
