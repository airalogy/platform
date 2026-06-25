<template>
  <base-input-wrapper :is="CustomInputNumber" :component-props="numberProps" v-bind="props" />
</template>

<script setup lang="ts">
import type { InputPropsOptions } from "../../types/input-props"
import CustomInputNumber from "@/components/custom/custom-input-number/custom-input-number.vue"
import { useInputProps } from "../../composables/useInputProps"
import BaseInputWrapper from "./base-input-wrapper.vue"

const props = defineProps<InputPropsOptions>()
const { numberProps } = useInputProps(props)
</script>
