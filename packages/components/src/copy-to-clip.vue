<template>
  <n-button text icon-placement="right" type="default" v-bind="buttonProps" @click="handleCopy">
    <span v-if="props.showText" class="whitespace-pre-wrap text-left">
      {{ props.text }}
    </span>
    <template #icon>
      <n-icon v-bind="iconProps">
        <icon-tabler-check v-if="isCopied" />
        <icon-tabler-copy v-else />
      </n-icon>
    </template>
    <slot />
  </n-button>
</template>

<script setup lang="ts">
import type { ButtonProps, IconProps } from "naive-ui"
import { useBoolean, useClosableMessage } from "@airalogy/composables"
import { copyToClip } from "@airalogy/shared/utils"

interface IProps {
  text: string
  showSuccess?: boolean
  showText?: boolean
  iconProps?: IconProps
  buttonProps?: ButtonProps
}

interface IEmits {
  (e: "copy"): void
}

const props = withDefaults(defineProps<IProps>(), {
  showText: true,
  buttonProps: () => ({}),
})

const emit = defineEmits<IEmits>()
const message = useClosableMessage()
const { bool: isCopied, setTrue, setFalse } = useBoolean(false)
function handleCopy() {
  copyToClip(props.text)
  emit("copy")
  if (props.showSuccess) {
    message.success("Copied to clipboard")
  }
  setTrue()
  setTimeout(() => {
    setFalse()
  }, 1000)
}
</script>
