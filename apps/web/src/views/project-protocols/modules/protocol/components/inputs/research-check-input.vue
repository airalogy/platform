<template>
  <custom-checkbox
    class="my-auto mr-4 self-start"
    v-bind="customCheckboxProps"
    :show-label="false"
  />
  <n-input v-if="hasAnnotation" v-bind="annotationInputProps" class="w-full flex-1" />
</template>

<script setup lang="ts">
import type { InputPropsOptions } from "../../types/input-props"
import customCheckbox from "@/components/custom/custom-checkbox.vue"
import { useInputProps } from "../../composables/useInputProps"

const props = defineProps<InputPropsOptions>()
const { customCheckboxProps, annotationInputProps } = useInputProps(props)
const hasAnnotation = computed(() => typeof props.model.value === "object" && props.model.value && Object.hasOwn(props.model.value, "annotation"))

// const themeOverrides = computed(() => (typeof props.model.value?.checked === "boolean" ? props.model.value.checked ? themeOverridesRecord.checkbox.checked : themeOverridesRecord.checkbox.unchecked : themeOverridesRecord.checkbox.init))
</script>
