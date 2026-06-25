<template>
  <div class="border rounded-lg p-4 space-y-3">
    <h3 class="text-lg font-medium">
      Statistics
    </h3>
    <div class="space-y-2">
      <div v-for="(value, key) in metrics" :key="key" class="flex justify-between">
        <span class="text-gray-600">{{ formatKey(key) }}</span>
        <span class="font-medium">{{ value }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Props {
  metrics: Record<string, number>
}

defineProps<Props>()

function formatKey(key: string): string {
  return key.split("_").map(word =>
    word.charAt(0).toUpperCase() + word.slice(1),
  ).join(" ")
}
</script>
