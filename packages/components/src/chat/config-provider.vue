<template>
  <slot />
</template>

<script setup lang="ts">
import type { ChatProviderContext, ChatProviderProps } from "./providers/useChatProvider"
import { createDefaultCurrentEditorProtocolContext, createDefaultCurrentRecorderRecordContext, createDefaultRendererContext, defaultReject, useProvideChatProvider } from "./providers/useChatProvider"

defineOptions({
  name: "ChatConfigProvider",
})

const props = withDefaults(defineProps<ChatProviderProps>(), {
  baseUrl: "",
  mode: "query",
  postToolResultChat: defaultReject,
  uploadAttachment: defaultReject,
  protocolId: "",
  stopStream: defaultReject,
  contextDialog: () => ({ show: false, options: [], selected: [] }),
  contextDialogEventHandlers: () => ({}),
  contextOptions: () => [],
  currentEditorProtocolContext: createDefaultCurrentEditorProtocolContext,
  currentRecorderRecordContext: createDefaultCurrentRecorderRecordContext,
  createRendererContext: createDefaultRendererContext,
  token: "",
  userInfo: () => ({}),
})

const emit = defineEmits<IEmits>()
interface IEmits {
  (e: "update:baseUrl", val: ChatProviderContext["baseUrl"]): void
  (e: "update:mode", val: ChatProviderContext["mode"]): void
  (e: "update:postToolResultChat", val: ChatProviderContext["postToolResultChat"]): void
  (e: "update:uploadAttachment", val: ChatProviderContext["uploadAttachment"]): void
  (e: "update:protocolId", val: ChatProviderContext["protocolId"]): void
  (e: "update:stopStream", val: ChatProviderContext["stopStream"]): void
  (e: "update:contextDialog", val: ChatProviderContext["contextDialog"]): void
  (e: "update:contextDialogEventHandlers", val: ChatProviderContext["contextDialogEventHandlers"]): void
  (e: "update:contextOptions", val: ChatProviderContext["contextOptions"]): void
  (e: "update:currentEditorProtocolContext", val: ChatProviderContext["currentEditorProtocolContext"]): void
  (e: "update:currentRecorderRecordContext", val: ChatProviderContext["currentRecorderRecordContext"]): void
  (e: "update:createRendererContext", val: ChatProviderContext["createRendererContext"]): void
  (e: "update:token", val: ChatProviderContext["token"]): void
  (e: "update:userInfo", val: ChatProviderContext["userInfo"]): void
}

const config = useVModels(props, emit, { deep: true })

useProvideChatProvider(config)
</script>
