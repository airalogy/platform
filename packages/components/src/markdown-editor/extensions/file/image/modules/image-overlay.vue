<script setup lang="ts">
import { NSpin } from "naive-ui"
</script>

<template>
  <div
    class="transition-opacity' absolute inset-0 flex flex-row items-center justify-center rounded bg-[var(--mt-overlay)] opacity-100"
  >
    <n-spin :size="28" />
  </div>
</template>
