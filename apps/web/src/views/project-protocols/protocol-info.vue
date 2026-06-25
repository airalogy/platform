<template>
  <split-layout :chat-props="{ source: 'protocol', airalogyId, role: ChatType.NORMAL }">
    <n-tabs
      type="segment"
      animated
      placement="top"
      :theme-overrides="{ tabPaddingVerticalMediumLine: '8px 0 20px 5px' }"
      class="protocol-content h-fit min-h-[calc(100vh-18rem)] p-4"
    >
      <n-tab-pane name="research_markdown" tab="Markdown">
        <report-template v-if="protocolInfo" :item="protocolInfo" />
      </n-tab-pane>
      <n-tab-pane name="fields" :tab="$t('common.fields')">
        <protocol-fields v-if="protocolInfo" :item="protocolInfo" />
      </n-tab-pane>
      <n-tab-pane name="history" :tab="$t('common.history')">
        <protocol-history v-if="protocolInfo" :item="protocolInfo" />
      </n-tab-pane>
      <n-tab-pane name="assigner_graph" :tab="$t('common.assigner')" :disabled="!(protocolInfo as any)?.assigner_graph">
        <assigner-graph />
      </n-tab-pane>
    </n-tabs>
  </split-layout>
</template>

<script setup lang="ts">
import type { IRecordDataKey } from "@airalogy/aimd-core/types"
import type { ProtocolModels } from "@airalogy/shared/types"
import { useBoolean } from "@/composables"
import { bubbleMenuEventKey } from "@/utils/template/eventKey"

import { ChatType } from "@airalogy/shared/enum"
import { $t } from "@airalogy/shared/locales"
import { useProtocolInfoStore } from "./hooks/useProtocolInfoStore"
import SplitLayout from "./layout/split-layout.vue"
import AssignerGraph from "./modules/protocol/assigner-graph.vue"
import ProtocolFields from "./modules/protocol/protocol-fields.vue"
import ProtocolHistory from "./modules/protocol/protocol-history.vue"
import ReportTemplate from "./modules/protocol/report-template.vue"

defineOptions({ name: "ProtocolProtocols" })

const props = withDefaults(defineProps<IProps>(), {
  protocol: null,
  defaultSpiltSize: 0.35,
})

const emits = defineEmits<Emits>()

const { protocolInfo, airalogyId } = useProtocolInfoStore()! || {}

const { bool: isCollapsed, setFalse: expand } = useBoolean(false)
interface IProps {
  protocol?: ProtocolModels.ProtocolInfo | null
  defaultSpiltSize?: number
}

const splitSize = ref(props.defaultSpiltSize)

interface Emits {
  (e: "update:field", payload: { scope: IRecordDataKey, prop: string, value: any, payload?: any }): void
  (e: "update:splitSize", payload: string | number): void
  (e: "expand:sider"): void
}
const bubbleMenuEventBus = useEventBus<"triggerChatAction" | "sendToChat" | "addToChat", { event: "sendToChat" | "addToChat", value: string } | string>(bubbleMenuEventKey)

bubbleMenuEventBus.on((event, payload) => {
  if (event === "triggerChatAction" && typeof payload === "object") {
    const { event: eventType, value } = payload
    isCollapsed.value = false
    void nextTick(() => {
      bubbleMenuEventBus.emit(eventType, value)
    })
  }
})

watch(
  () => splitSize.value,
  (val) => {
    if (isCollapsed.value && val > 0) {
      expand()
      emits("expand:sider")
    }
    emits("update:splitSize", val)
  },
)
</script>

<style scoped lang="sass">
:deep(.n-tabs-nav-scroll-wrapper)
  &:before, &:after
    content: none
:deep(.n-tabs-tab.n-tabs-tab--active)
  background: transparent!important
  color: #333333
</style>
