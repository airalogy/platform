<template>
  <base-input-wrapper
    :is="NSelect" v-bind="props" ref="selectRef"
    :component-props="{
      ...enumProps,
      class: { 'enum-select-input-has-assigner': hasAssigner, 'enum-select-input': true },
      style: hasAssigner ? { '--enum-select-input-min-width': minWidth, '--enum-select-input-suffix-right': suffixRight } : {} }" assigner-icon-slot="arrow" @schema-change="handleSchemaChange"
  >
    <template #icon>
      <icon-ion-chevron-down style="color: var(--n-arrow-color)!important; margin-left: 8px" />
    </template>
  </base-input-wrapper>
</template>

<script setup lang="ts">
import type { MaybeElement } from "@vueuse/core"
import type { JsonSchema } from "../../types/aimd-types"
import type { IAIMDInputProps } from "../../types/props"
import { NSelect } from "naive-ui"
import { useInputProps } from "../../composables/useInputProps"
import BaseInputWrapper from "../base-input-wrapper.vue"

const props = defineProps<IAIMDInputProps>()

const emit = defineEmits<IEmits>()
interface IEmits {
  (e: "schemaChange", schema: JsonSchema): void
}

const { enumProps, handleSchemaChange: innerHandleSchemaChange, itemRef } = useInputProps(props)

const selectRef = ref<HTMLElement>()

const minWidth = ref("100%")
const suffixRight = ref("18px")
const hasAssigner = computed(() => props.assigner || props.dependent)
onMounted(() => {
  const el = itemRef.value[`${props.scope}_${props.prop}`] as any as MaybeElement

  const { width } = unrefElement(el)?.getBoundingClientRect?.() ?? { width: 0 }
  minWidth.value = `${width + (hasAssigner.value ? 22 : 12)}px`
  suffixRight.value = `${width + (hasAssigner.value ? 22 : 12)}px`
})

function handleSchemaChange(schema: JsonSchema) {
  innerHandleSchemaChange(schema)
  emit("schemaChange", schema)
}
</script>

<style lang="sass" global>
.enum-select-input.enum-select-input-has-assigner
  .n-base-suffix__arrow
    color: var(--n-text-color)!important
    display: inline-flex!important
    width: fit-content!important
    align-items: center

  .n-base-selection-label
    padding-right: 30px!important
    min-width: var(--enum-select-input-min-width)!important

  .n-base-suffix
    right: var(--enum-select-input-suffix-right)!important

  .n-base-selection-placeholder
    right: 40px!important

    .n-base-selection-placeholder__inner
      @apply text-ellipsis
</style>
