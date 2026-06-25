<template>
  <n-form-item-row v-if="props.block">
    <n-input class="my-1.5 rounded-3 bg-[#F7F8F9] py-2.5 text-4" v-bind="props">
      <template #prefix>
        <slot name="prefix" />
      </template>
      <template #suffix>
        <slot name="suffix" />
      </template>
    </n-input>
  </n-form-item-row>
  <n-form-item-col v-else v-bind="props.col">
    <n-input class="my-1.5 rounded-3 bg-[#F7F8F9] py-2.5 text-4" v-bind="props">
      <template #prefix>
        <slot name="prefix" />
      </template>
      <template #suffix>
        <slot name="suffix" />
      </template>
    </n-input>
  </n-form-item-col>
</template>

<script setup lang="ts">
import type { FormItemColProps, InputProps } from "naive-ui"

interface IProps extends /* @vue-ignore */ InputProps {
  placeholder: InputProps["placeholder"]
  type: InputProps["type"]
  maxlength?: InputProps["maxlength"]
  block?: boolean
  col?: FormItemColProps
}

const props = withDefaults(defineProps<IProps>(), { block: true })
</script>

<style scoped lang="sass"></style>
