<template>
  <base-input-wrapper :is="CustomRecordIdInput" :component-props="inputProps" v-bind="props" />
</template>

<script setup lang="ts">
import type { InputPropsOptions } from "../../types/input-props"
import CustomRecordIdInput from "@/components/custom/custom-record-id-input.vue"
import { useInputProps } from "../../composables/useInputProps"
import BaseInputWrapper from "./base-input-wrapper.vue"

const props = defineProps<InputPropsOptions>()

const { inputProps } = useInputProps(props)
</script>
