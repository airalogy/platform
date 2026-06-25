<template>
  <n-tooltip trigger="hover">
    <template #trigger>
      <div class="inline-block px-1" :class="triggerWrapperClass">
        <slot v-bind="{ isActive, themeOverrides, handleClick, icon, label, triggerClass, disabled: props.disabled }">
          <n-button
            :quaternary="!isActive"
            :secondary="isActive"
            :type="isActive ? 'primary' : 'default'"
            size="medium"
            :theme-overrides="themeOverrides"
            :class="triggerClass"
            v-bind="buttonProps"
            :disabled="props.disabled"
            @click="handleClick"
          >
            <template v-if="icon" #icon>
              <n-icon :component="icon" v-bind="iconProps" />
            </template>
            <span v-if="label">{{ label }}</span>
            <n-icon v-if="showArrow" class="text-[#e5e7eb]">
              <icon-ion-chevron-down />
            </n-icon>
          </n-button>
        </slot>
      </div>
    </template>
    {{ tooltip }}
  </n-tooltip>
</template>

<script setup lang="ts">
import type { ButtonProps, GlobalThemeOverrides, IconProps } from "naive-ui"
import type { Component } from "vue"

interface IProps {
  tooltip: string
  enableTooltip?: boolean
  isActive?: boolean
  readonly?: boolean
  command?: (...args: any) => void
  emitter?: () => void
  icon?: Component | null
  label?: string
  showArrow?: boolean
  triggerWrapperClass?: string
  triggerClass?: string
  buttonProps?: ButtonProps
  iconProps?: IconProps
  disabled?: boolean
}

const props = withDefaults(defineProps<IProps>(), {
  enableTooltip: true,
  isActive: false,
  readonly: false,
  command: () => {},
  showArrow: false,
  iconProps: () => ({}),
})

const { icon, tooltip, command, isActive, label, triggerClass, triggerWrapperClass } = toRefs(props)

const themeOverrides: GlobalThemeOverrides["Button"] = {
  heightMedium: "32px",
  paddingMedium: "8px",
}

function handleClick() {
  if (props.readonly || typeof command.value !== "function")
    return
  command.value()
}
</script>
