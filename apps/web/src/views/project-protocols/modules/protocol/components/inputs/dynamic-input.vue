<template>
  <!-- <n-dynamic-input v-bind="dynamicInputProps" class="flex-1" /> -->
  <base-input-wrapper :is="NDynamicInput" :component-props="dynamicInputProps" v-bind="props" />
</template>

<script setup lang="ts">
import type { InputPropsOptions } from "../../types/input-props"
import { NDynamicInput } from "naive-ui"
import { useInputProps } from "../../composables/useInputProps"
import BaseInputWrapper from "./base-input-wrapper.vue"

const props = defineProps<InputPropsOptions>()

const { dynamicInputProps } = useInputProps(props)
</script>
