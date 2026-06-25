<template>
  <n-button
    v-auth="{ requireLogin, checkAuth }"
    v-bind="$attrs"
    :loading="loading"
    @click="handleClick"
  >
    <template v-if="icon && label" #icon>
      <n-icon :component="icon" v-bind="iconProps" />
    </template>
    {{ label }}
    <template v-if="icon && !label">
      <n-icon :component="icon" v-bind="iconProps" />
    </template>
  </n-button>
</template>

<script lang="ts" setup>
import type { DialogProps, IconProps } from "naive-ui"
import type { Component } from "vue"
import { useDialog } from "naive-ui"

interface Props {
  label?: string
  icon?: Component
  requireLogin?: boolean
  checkAuth?: () => boolean
  confirmProps?: DialogProps
  loading?: boolean
  iconProps?: IconProps
}

interface Emits {
  (e: "action"): void
}

const props = withDefaults(defineProps<Props>(), {
  requireLogin: true,
})
const emit = defineEmits<Emits>()

const dialog = useDialog()

async function handleClick() {
  if (props.confirmProps) {
    dialog.warning({
      ...props.confirmProps,
      positiveText: "Confirm",
      negativeText: "Cancel",
      onPositiveClick: () => emit("action"),
    })
    return
  }

  emit("action")
}
</script>
