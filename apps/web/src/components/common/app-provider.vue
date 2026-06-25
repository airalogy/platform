<template>
  <n-loading-bar-provider>
    <n-dialog-provider>
      <n-notification-provider>
        <n-message-provider>
          <context-holder />
          <slot />
        </n-message-provider>
      </n-notification-provider>
    </n-dialog-provider>
  </n-loading-bar-provider>
</template>

<script setup lang="ts">
import { useProvideChatConfigStore } from "@/composables"
import { useProvideChatProvider } from "@airalogy/components/chat/providers/useChatProvider"
import { useDialog, useLoadingBar, useMessage, useNotification } from "naive-ui"
import { createTextVNode, defineComponent } from "vue"

defineOptions({
  name: "AppProvider",
})

function register() {
  window.$dialog = useDialog()
  window.$loadingBar = useLoadingBar()
  window.$message = useMessage()
  window.$notification = useNotification()
}

const configs = useProvideChatConfigStore()
useProvideChatProvider(configs)
const ContextHolder = defineComponent({
  name: "ContextHolder",
  setup() {
    register()

    return () => createTextVNode()
  },
})
</script>

<style scoped>
</style>
