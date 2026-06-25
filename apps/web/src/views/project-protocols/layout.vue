<template>
  <global-layout>
    <content-layout title="Protocols" :tabs="tabs" :title-icon="ProtocolIcon">
      <template #suffix>
        <add-protocol-modal v-if="route.name === 'protocols-my'" @modal:new-protocol="handleAddProtocol" />
      </template>
    </content-layout>
  </global-layout>
</template>

<script setup lang="ts">
import type { TabPaneProps } from "naive-ui/es/tabs"
import ProtocolIcon from "@/components/icon/protocol-icon.vue"
import { useRouterPush } from "@/composables/useRouterPush"
import ContentLayout from "@/layouts/content-layout/index.vue"
import GlobalLayout from "@/layouts/global-layout/index.vue"
import { $t } from "@airalogy/shared/locales"
import AddProtocolModal from "./modules/add-protocol-modal.vue"

defineOptions({
  name: "ProtocolsLayout",
})

withDefaults(defineProps<Props>(), {
  showPadding: false,
})

interface Props {
  /** Show padding for content */
  showPadding?: boolean
}

const tabs: TabPaneProps[] = [
  { name: "protocols-my", tab: $t("page.protocol.tab.my") },
]

const route = useRoute()
const { routerPushByKey } = useRouterPush()

async function handleAddProtocol(item: {
  id: string
  uid: string
  labUid: string
  labId: string
  projectUid: string
  name: string
}) {
  const { uid, labUid, projectUid } = item

  await routerPushByKey("protocol-info", {
    params: { labUid, projectUid, protocolUid: uid },
  })
}
</script>

<style></style>
