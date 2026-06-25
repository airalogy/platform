<template>
  <!-- <n-select v-bind="selectProps" /> -->
  <base-input-wrapper :is="NSelect" :component-props="selectProps" v-bind="props" />
</template>

<script setup lang="ts">
import type { SelectProps } from "naive-ui"
import type { InputPropsOptions } from "../../types/input-props"
import { NSelect } from "naive-ui"
import { computed } from "vue"
import { useI18n } from "vue-i18n"
import { useInputProps } from "../../composables/useInputProps"
import BaseInputWrapper from "./base-input-wrapper.vue"

const props = defineProps<InputPropsOptions>()

const { commonProps, handleFieldChange } = useInputProps(props)
const { t, locale } = useI18n()

const selectProps = computed(() => {
  // Convert boolean value to string for NSelect compatibility
  const currentValue = props.model.value
  const stringValue = currentValue === true ? "true" : currentValue === false ? "false" : currentValue

  return {
    ...commonProps.value,
    "value": stringValue,
    "options": [
      { label: t("common.true"), value: "true" },
      { label: t("common.false"), value: "false" },
    ],
    "onUpdate:value": (value: string) => handleFieldChange({
      scope: props.scope,
      prop: props.prop,
      value: value === "true",
      info: props.info,
      assigner: props.assigner,
      dependent: props.dependent,
    }),
  } as SelectProps
})
</script>
