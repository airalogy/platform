<template>
  <base-input-wrapper :is="NSelect" :component-props="selectProps" v-bind="props" assigner-icon-slot="arrow">
    <template v-if="props.assigner || props.dependent" #icon>
      <icon-ion-chevron-down style="color: var(--n-arrow-color)!important; margin-left: 8px" />
    </template>
  </base-input-wrapper>
</template>

<script setup lang="ts">
import type { InputPropsOptions } from "../../types/input-props"
import { NSelect } from "naive-ui"
import { useInputProps } from "../../composables/useInputProps"
import BaseInputWrapper from "./base-input-wrapper.vue"

const props = defineProps<InputPropsOptions & {
  enumInfo?: any
}>()

const { commonProps, handleFieldChange } = useInputProps(props)

const suffixRight = computed(() => commonProps.value.loading ? "1em" : "calc(1em + 8px)")
const selectProps = computed(() => {
  const enumValue = Array.isArray(props.enumInfo) ? props.enumInfo : props.enumInfo?.enum

  return {
    ...commonProps.value,
    "value": props.model.value,
    "options": enumValue?.map((it: string) => ({ label: it, value: it })) ?? [],
    "onUpdate:value": (value: string) => handleFieldChange({
      scope: props.scope,
      prop: props.prop,
      value,
      info: props.info,
      assigner: props.assigner,
      dependent: props.dependent,
    }),
  }
})
</script>

<style scoped lang="sass">
:deep(.n-base-suffix__arrow)
  color: var(--n-text-color)!important
  display: inline-flex!important
  width: fit-content!important

:deep(.n-base-selection-placeholder)
  padding-right: 60px!important
:deep(.n-base-selection-placeholder__inner)
  width: fit-content!important

:deep(.n-base-suffix)
  right: v-bind(suffixRight)!important
</style>
