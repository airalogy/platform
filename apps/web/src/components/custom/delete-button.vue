<template>
  <n-button
    :bordered="false"
    class="scale-80"
    :theme-overrides="((props.themeOverrides || {}) as any)"
    :disabled="props.disabled"
    @click="props.onClick"
  >
    <template #icon>
      <delete-icon />
    </template>
  </n-button>
</template>

<script setup lang="ts">
import type { buttonProps } from "naive-ui/lib/button"

// Generate type-based props
interface IProps {
  onClick: () => void
  disabled?: boolean
  themeOverrides?: (typeof buttonProps)["themeOverrides"]
}
const props = withDefaults(defineProps<IProps>(), {
  onClick: () => {},
  disabled: false,
  themeOverrides: () => ({
    colorHover: "rgb(255,80,83,0.1)",
    colorPressed: "rgb(255,80,83,0.2)",
    colorFocus: "rgb(255,80,83,0.1)",
    textColor: "#A1A4AF",
    textColorHover: "#FF5053",
    textColorPressed: "#FF5053",
    textColorFocus: "#FF5053",
    rippleColor: "#FF5053",
  }),
})
</script>

<style scoped></style>
