<template>
  <n-tooltip
    :trigger="props.trigger"
    :placement="props.placement"
    :disabled="props.tooltipDisabled && props.disabled"
  >
    <template #trigger>
      <n-button v-bind="{ ...buttonProps, ...$attrs }" :disabled="disabled" @click="$emit('click', $event)">
        <template v-if="icon" #icon>
          <n-icon :component="icon" v-bind="iconProps" />
        </template>

        <template v-else-if="$slots.icon" #icon>
          <slot name="icon" />
        </template>

        <slot />
      </n-button>
    </template>
    <slot name="tooltip">
      {{ props.tooltip }}
    </slot>
  </n-tooltip>
</template>

<script setup lang="ts">
import type { ButtonProps, IconProps, PopoverPlacement, PopoverTrigger } from "naive-ui"
import type { Component, FunctionalComponent, HTMLAttributes } from "vue"
import { NIcon } from "naive-ui"

interface Props {
  tooltip?: string
  trigger?: PopoverTrigger
  placement?: PopoverPlacement
  disabled?: boolean
  icon?: Component | FunctionalComponent
  iconProps?: IconProps & { class?: HTMLAttributes["class"] }
  buttonProps?: ButtonProps & { class?: HTMLAttributes["class"] }
  tooltipDisabled?: boolean
}

defineOptions({
  inheritAttrs: false,
})

const props = withDefaults(defineProps<Props>(), {
  trigger: "hover",
  placement: "top",
  type: "default",
  size: "medium",
  disabled: false,
  icon: undefined,
  iconProps: undefined,
  buttonProps: undefined,
  tooltipDisabled: true,
})

defineEmits<{
  (e: "click", event: MouseEvent): void
}>()
</script>
