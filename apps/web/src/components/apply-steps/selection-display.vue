<template>
  <div class="flex flex-col gap-2">
    <div
      v-for="item in items" :key="item.type"
      class="flex items-center gap-2 text-sm"
    >
      <span class="w-16 text-[var(--text-3)] capitalize">{{ item.type }}:</span>
      <span class="font-medium">{{ item.label }}</span>
      <span v-if="item.showValue" class="text-[var(--text-3)]">({{ item.value }})</span>
    </div>
  </div>
</template>

<script setup lang="ts">
export interface SelectionItem {
  label: string
  value: string
  id?: string
  type: "lab" | "project" | "name" | "id" | "version" | "research"
  showValue?: boolean
}

interface Props {
  items: SelectionItem[]
}

defineProps<Props>()
</script>
