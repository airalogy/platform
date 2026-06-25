<template>
  <div class="h-full w-full flex flex-col overflow-auto bg-gray-100/50 p-2">
    <h2 class="mb-4 text-lg font-semibold">
      Protocol Settings
    </h2>

    <!-- Protocol Information Section -->
    <protocol-info-card :protocol-info="protocolForm" class="mb-4" />

    <!-- Protocol Metadata Form -->
    <n-card title="Protocol Metadata" class="mb-4" size="small">
      <n-form
        ref="formRef"
        :model="protocolForm"
        label-placement="left"
        label-width="auto"
        require-mark-placement="right-hanging"
      >
        <protocol-metadata-form
          v-if="isMounted"
          v-model="protocolForm"
          :parse-error="parseError"
          :original-toml="originalToml"
          :item-props="{ labelWidth: 120 }"
          :skip-global-id="true"
          @save="saveChanges"
          @reset="resetChanges"
          @update:toml="tomlContent = $event"
          @open-in-editor="openInEditor"
        />

        <div class="mt-4 flex justify-end gap-2">
          <n-button type="primary" @click="saveChanges">
            Save Changes
          </n-button>
          <n-button @click="resetChanges">
            Reset Changes
          </n-button>
        </div>
      </n-form>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import ProtocolInfoCard from "@airalogy/components/protocol/protocol-info-card.vue"
import { useThemeStore } from "@airalogy/composables"
import { useProtocolSettings } from "./composables/useProtocolSettings"
import ProtocolMetadataForm from "./protocol-metadata-form.vue"

// Define emits
const emit = defineEmits<{
  (e: "openInEditor", filename: string): void
}>()

// Store initialization
const themeStore = useThemeStore()

const {
  protocolForm,
  originalToml,
  parseError,
  tomlContent,
  formRef,
  saveChanges,
  resetChanges,
  loadTomlContent,
} = useProtocolSettings()

// Function to open in editor
function openInEditor(filename: string) {
  emit("openInEditor", filename)
}
const isMounted = ref(false)

onMounted(() => {
  loadTomlContent()
  isMounted.value = true
})
</script>

<style scoped>
/* Add any component-specific styles here */
</style>
