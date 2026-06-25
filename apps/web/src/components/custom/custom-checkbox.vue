<template>
  <n-checkbox ref="checkboxRef" v-bind="{ ...(props as CheckboxProps), ...$attrs }">
    <span
      :class="
        [labelClass, scopedLabelClass,
         {
           [`${scopedLabelClass}--checked`]: props.hasValue && props.checked,
           [`${scopedLabelClass}--not-checked`]: props.hasValue && !props.checked,
         },
        ]"
    >
      <template v-if="props.hasValue">
        <template v-if="props.checked"> {{ props.truthyLabel || $t("common.checkPassed") }} </template>
        <template v-else> {{ props.falsyLabel || $t("common.checkFailed") }} </template>
      </template>
      <template v-else-if="props.showLabel"> {{ props.defaultLabel || $t("common.toBeChecked") }}</template>
    </span>
    <slot />
  </n-checkbox>

  <teleport v-if="selector && props.hasValue" :to="selector">
    <icon-local-cross-mark class="cross-check-icon check-icon" />
  </teleport>
</template>

<script setup lang="ts">
import type { CheckboxProps, checkboxProps } from "naive-ui/es/checkbox"
import type { OnUpdateChecked } from "naive-ui/es/checkbox/src/interface"
import type { MaybeArray } from "naive-ui/lib/_utils"
import { NCheckbox } from "naive-ui/es/checkbox"

export interface IProps {
  "size"?: "small" | "medium" | "large"
  "checked"?: string | number | boolean
  "defaultChecked"?: string | number | boolean
  "value"?: string | number
  "disabled"?: boolean | undefined
  "indeterminate"?: boolean
  "label"?: string
  "focusable"?: boolean
  "checkedValue"?: string | boolean | number
  "uncheckedValue"?: string | boolean | number
  // eslint-disable-next-line vue/prop-name-casing
  "onUpdate:checked"?: MaybeArray<OnUpdateChecked>
  "privateInsideTable"?: boolean
  "onChange"?: MaybeArray<OnUpdateChecked>
  "themeOverrides"?: typeof checkboxProps.themeOverrides
  "onFocus"?: (...args: any[]) => void
  "onBlur"?: (...args: any[]) => void
  "hasValue"?: boolean
  "scope": string
  "truthyLabel"?: string
  "falsyLabel"?: string
  "defaultLabel"?: string
  "showLabel"?: boolean
  "labelClass"?: string
}

const props = defineProps<IProps>()
const emits = defineEmits<IEmits>()

interface IEmits {
  (e: "update:modelValue", value: boolean): void
}

const checkboxRef = ref<typeof NCheckbox | null>(null)
const selector = ref<string | null>(null)
const scopedLabelClass = computed(() => `${props.scope.replace("_", "-")}__label`)

defineExpose({ getRef: () => checkboxRef })

onMounted(() => {
  if (checkboxRef.value?.$el) {
    selector.value = `#${checkboxRef.value.$el.id} .n-checkbox-icon`
  }
})
</script>

<style scoped lang="sass">
:deep(.check-icon)
  position: absolute
  top: 0
  left: 0
  right: 0
  bottom: 0

.cross-check-icon
  position: absolute
  opacity: 1!important
  transform: scale(1)!important
  font-size: 16px
  --n-check-mark-color: rgba(255, 80, 83, 0.8)

:not(.n-checkbox--checked) .cross-check-icon
  --n-check-mark-color-disabled: rgba(255, 80, 83, 0.8)

.n-checkbox:hover .cross-check-icon
    --n-check-mark-color: rgba(255, 80, 83, 1)
.n-checkbox--checked .cross-check-icon
  transform: scale(0.5)
  opacity: 0!important

.research-variable__label, .research-step__label, .research-check__label
  font-weight: bold
  margin: 0 6px
  white-space: nowrap
  &--not-checked
    color: rgba(219, 22, 22, 0.8)

.research-step__label--checked
  color: rgb(255, 157, 0, 0.8)
.research-variable__label--checked,.research-check__label--checked
  color: rgb(24, 160, 88)
</style>
