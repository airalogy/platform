<template>
  <aimd-record-report
    :aimd="props.aimd"
    :mermaid-component="MermaidBlock"
    :record="props.record"
    :resolve-url="resolveRecordFile"
    body-class="markdown-body"
  />
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types"
import { resolveProtocolFile } from "@/utils/resolveProtocolFile"
import { AimdRecordReport } from "@airalogy/aimd-renderer/vue"
import MermaidBlock from "@airalogy/components/markdown-editor/modules/mermaid/mermaid-block.vue"

interface Props {
  aimd: string
  record: object
  protocolId?: string | number
}

const props = defineProps<Props>()

async function resolveRecordFile(src: string) {
  const record = props.record as Partial<ProtocolModels.RecordInfo>
  const protocolId = record.metadata?.airalogy_protocol_id || props.protocolId
  if (!protocolId) {
    return null
  }

  return resolveProtocolFile(src, protocolId)
}
</script>
