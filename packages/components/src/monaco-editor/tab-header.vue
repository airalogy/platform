<template>
  <header class="relative w-full flex items-center justify-between">
    <!-- protocol-title-section -->
    <slot name="title" />
    <!-- Logo -->
    <router-link to="/" class="mx-1.25 h-10 w-10 flex-center text-primary">
      <n-icon size="28">
        <icon-local-logo-icon />
      </n-icon>
    </router-link>

    <!-- Action Buttons -->
    <div class="mr-auto flex items-center gap-4">
      <tooltip-button tooltip="Click to create empty protocol" :button-props="{ themeOverrides: buttonThemeOverrides, text: true }" @click="handleNewProtocol('empty')">
        <template #icon>
          <n-icon>
            <icon-tabler-file-plus />
          </n-icon>
        </template>
        New
      </tooltip-button>
      <tooltip-button
        :tooltip="isEditorReadOnly ? 'Create a copy to edit this protocol' : 'Click to save protocol'"
        type="primary"
        size="small"
        :theme-overrides="buttonThemeOverrides"
        :loading="loading"
        @click="handleSave"
      >
        <template #icon>
          <n-icon>
            <icon-ion-edit v-if="isEditorReadOnly" />
            <icon-save v-else />
          </n-icon>
        </template>
        {{ isEditorReadOnly ? 'Edit' : "Save" }}
      </tooltip-button>
    </div>
  </header>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types/models"
import { useUploadFileDataStore } from "@airalogy/components/monaco-editor/store/uploadFileDataStore"
import { useClosableMessage, useLoading } from "@airalogy/composables"
import IconSave from "~icons/lucide/save"
import { NIcon } from "naive-ui"

interface Props {
  protocolInfo: ProtocolModels.ProjectProtocolInfo | null
}
const props = defineProps<Props>()
const emit = defineEmits<IEmits>()
interface IEmits {
  (e: "newFile", mode: "empty" | "copy"): void
  (e: "save"): boolean
}

// Uniformly use light theme
const buttonThemeOverrides = {
  textColor: "#333333",
  textColorHover: "#1A79FF",
  colorHover: "rgba(26, 121, 255, 0.1)",
  colorPressed: "rgba(26, 121, 255, 0.2)",
}
const uploadFileDataStore = useUploadFileDataStore()
const isEditorReadOnly = injectLocal<Ref<boolean>>("isEditorReadOnly")

function handleNewProtocol(mode: "empty" | "copy") {
  emit("newFile", mode)
}

const { loading, startLoading, endLoading } = useLoading()

const message = useClosableMessage()
async function handleSave() {
  startLoading()

  const result = await emit("save")
  if (result) {
    message.success("Protocol saved successfully")
  }
  endLoading()
}
</script>

<style lang="sass" scoped>
.n-button
  @apply font-light

  &:not(:disabled):hover
    @apply border border-white/20

    :deep(.n-button__border)
      @apply border-white/20
</style>
