<template>
  <div class="rs-check-minimal-container">
    <!-- Check component (if exists) -->
    <div v-if="info.hasCheck && info.checkItem" class="mb-2">
      <checkbox-input v-bind="info.checkItem" />
    </div>

    <!-- Annotation component -->
    <annotation-input v-bind="props" />
  </div>
</template>

<script setup lang="ts">
import type { IAIMDInputProps } from "../../types/props"
import AnnotationInput from "./annotation-input.vue"
import CheckboxInput from "./checkbox-input.vue"

defineOptions({
  inheritAttrs: false,
})

const props = defineProps<IAIMDInputProps>()
</script>

<style scoped lang="sass">
.rs-check-minimal-container
  @apply space-y-2
</style>
