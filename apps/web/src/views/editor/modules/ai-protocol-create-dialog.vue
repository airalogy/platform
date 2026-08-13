<template>
  <n-modal
    v-model:show="showModal"
    preset="card"
    :title="$t('editor.aiCreate.dialogTitle')"
    :bordered="false"
    size="huge"
    class="max-w-4xl w-90vw"
    content-class="max-h-80vh overflow-y-auto"
    :mask-closable="false"
  >
    <n-alert type="info" :bordered="false" class="mb-4">
      {{ $t("editor.aiCreate.dialogDescription") }}
    </n-alert>

    <n-form-item :label="$t('editor.aiCreate.nameLabel')" required>
      <n-input
        v-model:value="protocolName"
        data-testid="ai-protocol-name"
        :placeholder="$t('editor.aiCreate.namePlaceholder')"
        maxlength="80"
        :disabled="props.loading"
      />
    </n-form-item>

    <protocol-generator
      :generate-aimd="props.generateAimd"
      :extract-instruction-file="props.extractInstructionFile"
      :disabled="props.loading || !protocolName.trim()"
      :on-save-file="handleGeneratedProtocol"
    />
  </n-modal>
</template>

<script setup lang="ts">
import type { ChatModelConfig } from "@airalogy/shared"
import { useClosableMessage } from "@/composables"
import ProtocolGenerator from "@airalogy/components/monaco-editor/modules/panel/protocol-generator.vue"
import { $t } from "@airalogy/shared/locales"

interface ExtractedInstructionFile {
  filename: string
  text: string
  was_trimmed: boolean
  content_type: string
}

const props = withDefaults(defineProps<{
  show: boolean
  loading?: boolean
  generateAimd: (
    payload: { instruction: string, model: ChatModelConfig },
    requestId?: string,
  ) => Promise<{ data: string | null, error: any }>
  extractInstructionFile?: (
    file: File,
  ) => Promise<{ data: ExtractedInstructionFile | null, error: any }>
  createProtocol: (payload: { name: string, content: string }) => Promise<void>
}>(), {
  loading: false,
  extractInstructionFile: undefined,
})

const emit = defineEmits<{
  (e: "update:show", value: boolean): void
}>()

const message = useClosableMessage()
const showModal = ref(props.show)
const protocolName = ref($t("editor.aiCreate.defaultName"))

async function handleGeneratedProtocol(content: string) {
  const name = protocolName.value.trim()
  if (!name) {
    message.warning($t("editor.aiCreate.nameRequired"))
    return
  }

  await props.createProtocol({ name, content })
  showModal.value = false
}

watch(() => props.show, (value) => {
  showModal.value = value
})

watch(showModal, (value) => {
  emit("update:show", value)
})
</script>
