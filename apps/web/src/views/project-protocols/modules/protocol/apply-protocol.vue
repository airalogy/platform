<template>
  <split-layout :chat-props="{ source: 'protocol', airalogyId, role: ChatType.NORMAL }" content-class="px-4">
    <div class="mb-8">
      <div class="text-2xl font-bold">
        {{ title }}
      </div>
      <div class="mt-2 text-gray-500">
        {{ description }}
      </div>
    </div>

    <protocol-steps :protocol-info="protocolInfo" @cancel="handleCancel" />
  </split-layout>
</template>

<script setup lang="ts">
import ProtocolSteps from "@/components/apply-steps/protocol-steps.vue"
import { useRouterPush } from "@/composables/useRouterPush"
import { ChatType } from "@airalogy/shared/enum"
import { useProtocolInfoStore } from "../../hooks/useProtocolInfoStore"
import SplitLayout from "../../layout/split-layout.vue"

defineOptions({
  name: "ApplyProtocol",
  inheritAttrs: false,
})

const { protocolInfo, airalogyId } = useProtocolInfoStore()! || {}
const { routerPushByKey } = useRouterPush()

const title = computed(() => {
  if (protocolInfo.value) {
    return "Update Protocol"
  }
  return "Create Airalogy Protocol"
})
const description = computed(() => {
  if (protocolInfo.value) {
    return "Create an Airalogy Protocol for this Project."
  }
  return "Every project requires an Airalogy Protocol to function. Please follow the steps below to create one."
})

function handleCancel() {
  if (!protocolInfo.value) {
    return
  }
  const { lab, project, uid } = protocolInfo.value
  routerPushByKey("protocol-info", {
    params: {
      labUid: lab.uid,
      protocolUid: uid,
      projectUid: project.uid,
    },
  })
}
</script>
