<template>
  <div class="custom-empty flex flex-col items-center justify-center">
    <img
      :src="image"
      alt="empty placeholder"
      class="object-contain" :class="[
        size === 'small' && 'h-32',
        size === 'medium' && 'h-40',
        size === 'large' && 'h-48',
      ]"
    >
    <p
      class="mt-4 text-center text-6 text-gray-500"
      :class="[
        size === 'small' && 'text-5',
        size === 'medium' && 'text-6',
        size === 'large' && 'text-7',
      ]"
    >
      {{ description }}
    </p>
    <div v-if="$slots.default" class="mt-4">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
interface Props {
  description?: string
  size?: "small" | "medium" | "large"
  image?: string
}

withDefaults(defineProps<Props>(), {
  description: "No Data",
  size: "medium",
  image: "/images/empty_placeholder.svg",
})
</script>

<style scoped>
.custom-empty {
  padding: 1.25rem;
}
</style>
