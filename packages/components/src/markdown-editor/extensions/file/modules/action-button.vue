<template>
  <n-tooltip placement="bottom" trigger="hover">
    <template #trigger>
      <n-button
        quaternary
        class="h-7 w-7 flex items-center justify-center text-gray-500 hover:text-gray-900"
        @click.prevent="(e: Event) => $emit('click', e)"
      >
        <template #icon>
          <div :class="iconClass" class="size-4" />
        </template>
      </n-button>
    </template>
    {{ tooltip }}
  </n-tooltip>
</template>

<script setup lang="ts">
defineProps<{
  iconClass?: string
  tooltip?: string
}>()

defineEmits<{
  (e: "click", event: Event): void
}>()
</script>
