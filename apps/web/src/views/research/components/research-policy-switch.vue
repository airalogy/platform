<template>
  <div class="flex items-start justify-between gap-4">
    <div class="min-w-0">
      <div class="aira-type-label">
        {{ label }}
      </div>
      <p class="aira-type-meta mb-0 mt-1">
        {{ hint }}
      </p>
    </div>
    <n-switch
      :value="modelValue"
      :disabled="disabled"
      @update:value="$emit('update:modelValue', $event)"
    />
  </div>
</template>

<script setup lang="ts">
defineProps<{
  modelValue: boolean
  disabled?: boolean
  label: string
  hint: string
}>()

defineEmits<{ (event: "update:modelValue", value: boolean): void }>()
</script>
