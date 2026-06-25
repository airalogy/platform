<template>
  <div class="mb-6">
    <!-- Header Section -->
    <div class="mb-3">
      <h2
        class="mb-2 text-2xl font-semibold"
        :class="[
          isDanger
            ? 'text-red-700'
            : 'text-gray-900',
        ]"
      >
        {{ title }}
      </h2>
      <p v-if="description" class="text-sm text-gray-600">
        {{ description }}
      </p>
    </div>

    <!-- Card Content -->
    <div
      class="border rounded-xl bg-white p-6"
      :class="[
        isDanger
          ? 'border-red-200'
          : 'border-gray-200',
      ]"
    >
      <slot />
      <div
        v-if="$slots.footer"
        class="mt-6 -mx-6 -mb-6 rounded-b-xl px-6 py-4"
        :class="[
          isDanger
            ? 'bg-red-50/40'
            : 'bg-gray-50',
        ]"
      >
        <slot name="footer" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Props {
  title: string
  description?: string
  isDanger?: boolean
}

withDefaults(defineProps<Props>(), {
  description: undefined,
  isDanger: false,
})
</script>
