<template>
  <!-- <n-date-picker v-bind="datePickerProps" class="w-full flex-1" /> -->
  <base-input-wrapper :is="NDatePicker" :component-props="datePickerProps" v-bind="props" />
</template>

<script setup lang="ts">
import type { InputPropsOptions } from "../../types/input-props"
import { NDatePicker } from "naive-ui"
import { useInputProps } from "../../composables/useInputProps"
import BaseInputWrapper from "./base-input-wrapper.vue"

const props = defineProps<InputPropsOptions>()

const { datePickerProps } = useInputProps(props)
</script>
