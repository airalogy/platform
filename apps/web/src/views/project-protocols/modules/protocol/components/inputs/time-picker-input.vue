<template>
  <!-- <custom-time-picker v-bind="timePickerProps as any" class="w-full flex-1" /> -->
  <base-input-wrapper :is="CustomTimePicker" :component-props="timePickerProps" v-bind="props" />
</template>

<script setup lang="ts">
import type { InputPropsOptions } from "../../types/input-props"
import CustomTimePicker from "@/components/custom/custom-time-picker/index.vue"
import { useInputProps } from "../../composables/useInputProps"
import BaseInputWrapper from "./base-input-wrapper.vue"

const props = defineProps<InputPropsOptions>()

const { timePickerProps } = useInputProps(props)
</script>
