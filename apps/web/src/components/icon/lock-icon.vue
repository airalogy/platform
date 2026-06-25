<template>
  <n-icon size="26" :color="props.color">
    <icon-local-lock />
  </n-icon>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{ color?: string }>(), { color: "white" })
</script>

<style scoped></style>
