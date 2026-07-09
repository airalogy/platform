<template>
  <global-layout>
    <content-layout title="Protocols" :tabs="tabs" :title-icon="ProtocolIcon">
      <template #suffix>
        <div v-if="route.name === 'protocols-my'" class="flex items-center gap-2">
          <import-aira-archive-modal @imported="handleImportArchive" />
          <add-protocol-modal @modal:new-protocol="handleAddProtocol" />
        </div>
      </template>
    </content-layout>
  </global-layout>
</template>

<script setup lang="ts">
import type { ImportAiraArchiveResponse } from "@/service/api/project-protocols"
import type { TabPaneProps } from "naive-ui/es/tabs"
import ProtocolIcon from "@/components/icon/protocol-icon.vue"
import { useRouterPush } from "@/composables/useRouterPush"
import ContentLayout from "@/layouts/content-layout/index.vue"
import GlobalLayout from "@/layouts/global-layout/index.vue"
import { $t } from "@airalogy/shared/locales"
import AddProtocolModal from "./modules/add-protocol-modal.vue"
import ImportAiraArchiveModal from "./modules/import-aira-archive-modal.vue"

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

async function handleImportArchive(result: ImportAiraArchiveResponse) {
  const importedProtocol = result.protocols[0]
  if (!importedProtocol) {
    return
  }

  await routerPushByKey("protocol-info", {
    params: {
      labUid: importedProtocol.lab_uid,
      projectUid: importedProtocol.project_uid,
      protocolUid: importedProtocol.uid,
    },
  })
}
</script>

<style></style>
