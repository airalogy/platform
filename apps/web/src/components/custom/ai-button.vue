<template>
  <n-tooltip trigger="hover" v-bind="props.tooltipProps">
    {{ props.tooltip }}
    <template #trigger>
      <n-button
        round text-color="#fff" v-bind="props.buttonProps" class="ai-button__wrapper"
        :class="props.buttonClass"
      >
        <slot />
        <template #icon>
          <n-icon size="12">
            <icon-ion-sparkles />
          </n-icon>
        </template>
      </n-button>
    </template>
  </n-tooltip>
</template>

<script setup lang="ts">
import type { ButtonProps, TooltipProps } from "naive-ui"

interface IProps {
  tooltip?: string
  tooltipProps?: TooltipProps
  buttonProps?: ButtonProps
  buttonClass?: string
}

const props = withDefaults(defineProps<IProps>(), {
  tooltip: "AI Generate",
  tooltipProps: () => ({}),
  buttonProps: () => ({ type: "primary" }),
  buttonClass: undefined,
})
</script>

<style scoped lang="sass">
.ai-button__wrapper
  background-image: linear-gradient(to right, #1A79FF 0%, #7A4BFF 100%)
  padding: 4px 24px
  font-size: 14px
</style>
