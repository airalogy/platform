<template>
  <n-dropdown trigger="click" :options="options" @select="handleDownload">
    <n-button :loading="loading" :disabled="!protocolId || !version">
      <template #icon>
        <n-icon>
          <icon-carbon-download />
        </n-icon>
      </template>
      {{ t("common.download") }}
    </n-button>
  </n-dropdown>
</template>

<script setup lang="ts">
import type { ProtocolExportFormat } from "@/service/api/protocol-export"
import { downloadProtocolExport } from "@/service/api/protocol-export"
import { useClosableMessage } from "@airalogy/composables"
import { useI18n } from "vue-i18n"

const props = defineProps<{ protocolId?: string | number, version?: string }>()
const { t } = useI18n()
const message = useClosableMessage()
const loading = ref(false)
const options = computed(() => [
  { key: "aira", label: t("page.protocol.exportAira") },
  { key: "zip", label: t("page.protocol.exportZip") },
])
async function handleDownload(format: ProtocolExportFormat) {
  if (!props.protocolId || !props.version || loading.value)
    return
  loading.value = true
  try {
    await downloadProtocolExport(props.protocolId, props.version, format)
  }
  catch {
    message.error(t("page.protocol.exportFailed"))
  }
  finally {
    loading.value = false
  }
}
</script>
