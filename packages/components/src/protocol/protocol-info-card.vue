<template>
  <n-card size="small" class="protocol-info-card">
    <n-descriptions label-placement="left" title="Protocol Details">
      <n-descriptions-item label="Protocol Name">
        {{ protocolInfo.name }}
      </n-descriptions-item>
      <n-descriptions-item label="Protocol ID">
        {{ protocolInfo.id }}
      </n-descriptions-item>
      <n-descriptions-item label="Version">
        {{ protocolInfo.version }}
      </n-descriptions-item>
    </n-descriptions>
  </n-card>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types"
import { NCard, NDescriptions, NDescriptionsItem } from "naive-ui"

interface Props {
  protocolInfo: ProtocolModels.ProtocolMetaData
}

defineProps<Props>()
</script>
