<template>
  <n-form-item v-if="mode === 'fork'" :label="props.showLabel ? 'Protocol Name' : ''" path="protocolName" required>
    <n-tooltip trigger="focus" placement="top-start">
      <template #trigger>
        <n-input v-model:value="(activeModel as FormModel).protocolName" />
      </template>
      The name of the protocol
    </n-tooltip>
  </n-form-item>

  <template v-if="props.showMetadata">
    <div v-if="props.showLabel" class="pb-1.5 pl-0.5 text-4">
      Metadata
    </div>
    <protocol-metadata-form
      v-model="metadataForm"
      :original-toml="originalToml"
      :check-loading="props.checkLoading"
      :check-id="props.checkId"
      :aimd-content="aimdContent"
      class="py-2"
      path-prefix="metadata"
      :lab-uid="labUid"
      :project-uid="projectUid"
      :protocol-info="protocolInfo"
      :skip-upload="props.skipUpload"
      :disable-default="props.disableDefault"
      @update:toml="handleUpdateToml"
      @reset="resetMetadata"
    />
  </template>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types/models"
import ProtocolMetadataForm from "@airalogy/components/monaco-editor/modules/panel/protocol-metadata-form.vue"
import { onMounted } from "vue"
import { type FormModel, useApplyProtocol } from "./composables/useApplyProtocolState"

interface IProps {
  metadata?: ProtocolModels.ProtocolMetaData
  originalToml?: string
  showMetadata?: boolean
  checkLoading?: boolean
  checkId?: boolean
  aimdContent?: string
  labUid?: string | null
  projectUid?: string | null
  showLabel?: boolean
  skipUpload?: boolean
  disableDefault?: boolean
}

defineOptions({
  name: "ProtocolDetails",
  inheritAttrs: false,
})

const props = withDefaults(defineProps<IProps>(), {
  metadata: () => ({
    id: "",
    version: "",
    // airalogy_protocol_id: "",
    name: "",
    authors: [],
    maintainers: [],
    disciplines: [],
    keywords: [],
    license: "",
  }),
  showMetadata: false,
  checkLoading: false,
  checkId: true,
  showLabel: true,
  skipUpload: false,
  disableDefault: true,
})

const emit = defineEmits<IEmits>()
const { activeModel, mode, uploadModel, protocolData, protocolInfo } = useApplyProtocol()
interface IEmits {
  (e: "update:metadata", metadata: ProtocolModels.ProtocolMetaData): void
}

// Initialize metadata form with default values or parse existing metadata
const metadataForm = useVModel(props, "metadata", emit)
const originalToml = computed(() => {
  if (protocolData.value) {
    return protocolData.value.toml_config
  }
  return props.originalToml || ""
})

const aimdContent = computed(() => {
  if (protocolData.value) {
    return protocolData.value.protocol
  }
  return ""
})

// Parse existing metadata if available
onMounted(() => {
  const model = activeModel.value as FormModel
  if (model.metadata && typeof model.metadata === "string") {
    try {
      const parsedMetadata = JSON.parse(model.metadata)
      metadataForm.value = {
        id: parsedMetadata.id || "",
        version: parsedMetadata.version || "0.0.1",
        // airalogy_protocol_id: parsedMetadata.airalogy_protocol_id || "",
        name: parsedMetadata.name || "",
        authors: parsedMetadata.authors || [],
        maintainers: parsedMetadata.maintainers || [],
        disciplines: parsedMetadata.disciplines || [],
        keywords: parsedMetadata.keywords || [],
        license: parsedMetadata.license || "",
      }
    }
    catch (e) {
      console.error("Failed to parse metadata:", e)
    }
  }
})

// Reset metadata form to the original value
function resetMetadata() {
  const model = activeModel.value as FormModel
  if (model.metadata && typeof model.metadata === "string") {
    try {
      const parsedData = JSON.parse(model.metadata)
      metadataForm.value = {
        id: parsedData.id || "",
        version: parsedData.version || "0.0.1",
        // airalogy_protocol_id: parsedData.airalogy_protocol_id || "",
        name: parsedData.name || "",
        authors: parsedData.authors || [],
        maintainers: parsedData.maintainers || [],
        disciplines: parsedData.disciplines || [],
        keywords: parsedData.keywords || [],
        license: parsedData.license || "",
      }
    }
    catch (e) {
      console.error("Failed to parse metadata:", e)
    }
  }
  else {
    // Reset to defaults
    metadataForm.value = {
      id: "",
      version: "0.0.1",
      airalogy_protocol_id: "",
      name: "",
      authors: [],
      maintainers: [],
      disciplines: [],
      keywords: [],
      license: "",
    }
  }
}
function handleUpdateToml(toml: string) {
  // Update the TOML content in the model
  uploadModel.value.tomlContent = toml
}
</script>
