<template>
  <n-button v-bind="props.buttonProps" :disabled="!Boolean(protocolUid)" @click="handleRedirect">
    <template v-if="props.showIcon" #icon>
      <slot name="icon">
        <icon-local-add-circle class="text-4" />
      </slot>
    </template>
    <span v-if="showTrigger">
      {{ props.trigger }}
    </span>
  </n-button>
</template>

<script setup lang="ts">
import { useRouterPush } from "@/composables/useRouterPush"
import { useClosableMessage } from "@airalogy/composables"

import { type ButtonProps, NButton } from "naive-ui/es/button"

defineOptions({ name: "AddLogModal" })

const props = withDefaults(defineProps<IProps>(), {
  showIcon: true,
  buttonProps: () => ({ type: "primary" }),
  trigger: "Add",
  showTrigger: true,
  protocolUid: null,
})

interface IProps {
  showIcon?: boolean
  buttonProps?: ButtonProps & { class?: string | string[] }
  labUid?: string | null
  projectUid?: string | null
  protocolUid?: string | null
  showTrigger?: boolean
  trigger?: string
}

const { routerPushByKey } = useRouterPush()
const message = useClosableMessage()

function handleRedirect() {
  const { protocolUid, labUid, projectUid } = props

  if (!protocolUid || !labUid || !projectUid) {
    message.error("invalid id params")
    return
  }

  void routerPushByKey("add-protocol-record", {
    params: { protocolUid, labUid, projectUid },
  })
}
</script>

<style scoped lang="sass"></style>
