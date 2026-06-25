<template>
  <!-- <custom-checkbox v-bind="customCheckboxProps" class="my-auto self-start">
    {{ model.value }}
  </custom-checkbox> -->
  <base-input-wrapper :is="CustomCheckbox" :component-props="customCheckboxProps" v-bind="props">
    {{ model.value }}
  </base-input-wrapper>
</template>

<script setup lang="ts">
import type { InputPropsOptions } from "../../types/input-props"
import CustomCheckbox from "@/components/custom/custom-checkbox.vue"
import { useInputProps } from "../../composables/useInputProps"
import BaseInputWrapper from "./base-input-wrapper.vue"

const props = defineProps<InputPropsOptions>()

const { customCheckboxProps } = useInputProps(props)
</script>
