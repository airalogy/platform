<template>
  <div class="inline-block overflow-hidden align-bottom" :class="{ 'bg-white rounded-md b-1': strippedValue }">
    <div class="aimd-field aimd-field--small w-full flex !mt-0" :class="{ 'aimd-field--no-style': strippedValue }">
      <span class="aimd-field__scope" :class="[`aimd-field__scope--${type}`]">{{ type }}</span>
      <span class="aimd-field__name flex-1" v-bind="attrs">{{ name }}</span>
    </div>
    <div v-if="strippedValue" class="w-full px-1">
      {{ strippedValue }}
    </div>
  </div>
</template>

<script setup lang="ts">
interface Props {
  type: string
  name: string
  id?: string
  attrs?: Record<string, string>
}

const props = defineProps<Props>()
const strippedValue = computed(() => {
  const { value } = props.attrs || {}

  if (value) {
    return value.replace(/^"|"$/g, "")
  }

  return value
})
</script>
