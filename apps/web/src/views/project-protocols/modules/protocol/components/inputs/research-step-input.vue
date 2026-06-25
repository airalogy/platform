<template>
  <div class="w-full flex flex-1 flex-col gap-2">
    <custom-checkbox
      v-if="model?.raw?.check"
      v-bind="customCheckboxProps"
      :show-label="true"
      class="self-start"
    />
    <n-input v-if="hasAnnotation" v-bind="annotationInputProps" class="w-full" />
  </div>
</template>

<script setup lang="ts">
import type { InputPropsOptions } from "../../types/input-props"
import CustomCheckbox from "@/components/custom/custom-checkbox.vue"
import { useInputProps } from "../../composables/useInputProps"

const props = defineProps<InputPropsOptions>()
const { customCheckboxProps, annotationInputProps } = useInputProps(props)
const hasAnnotation = computed(() => typeof props.model.value === "object" && props.model.value && Object.hasOwn(props.model.value, "annotation"))
</script>
