<template>
  <n-icon :size="props.size">
    <icon-local-record-pending v-if="props.pending" />
    <icon-local-record v-else />
  </n-icon>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{ pending?: boolean, size?: number }>(), { pending: false, size: 40 })
</script>

<style scoped></style>
