<template>
  <n-card size="small" class="protocol-info-card">
    <!-- Basic Information Section -->
    <h3 class="mb-3 text-base font-medium">
      {{ title }}
    </h3>
    <n-grid :cols="4" :x-gap="8" :y-gap="8">
      <n-grid-item :span="1">
        <div class="text-gray-600">
          {{ $t("page.protocol.protocolName") }}
        </div>
      </n-grid-item>
      <n-grid-item :span="3">
        <div class="text-right">
          {{ protocolInfo.name }}
        </div>
      </n-grid-item>

      <n-grid-item :span="1">
        <div class="text-gray-600">
          {{ $t("page.protocol.protocolId") }}
        </div>
      </n-grid-item>
      <n-grid-item :span="3">
        <div class="flex items-center justify-end text-right">
          <span class="mr-2 font-mono">{{ airalogyId }}</span>
          <n-button v-if="airalogyId" text size="tiny" @click.stop="copyProtocolId">
            <template #icon>
              <n-icon>
                <icon-tabler-check v-if="copied" />
                <icon-ion-copy-outline v-else />
              </n-icon>
            </template>
          </n-button>
        </div>
      </n-grid-item>

      <n-grid-item v-if="protocolInfo.metadata.version" :span="1">
        <div class="text-gray-600">
          {{ $t("common.version") }}
        </div>
      </n-grid-item>
      <n-grid-item v-if="protocolInfo.metadata.version" :span="3">
        <div class="text-right">
          v{{ protocolInfo.latest_version }}
        </div>
      </n-grid-item>

      <n-grid-item v-if="protocolInfo.metadata.license" :span="1">
        <div class="text-gray-600">
          {{ $t("common.license") }}
        </div>
      </n-grid-item>
      <n-grid-item v-if="protocolInfo.metadata.license" :span="3">
        <div class="text-right">
          {{ protocolInfo.metadata.license }}
        </div>
      </n-grid-item>

      <n-grid-item v-if="protocolInfo.created_at" :span="1">
        <div class="text-gray-600">
          {{ $t("common.created") }}
        </div>
      </n-grid-item>
      <n-grid-item v-if="protocolInfo.created_at" :span="3">
        <div class="text-right">
          {{ formatDate(protocolInfo.created_at) }}
        </div>
      </n-grid-item>

      <n-grid-item v-if="protocolInfo.updated_at" :span="1">
        <div class="text-gray-600">
          {{ $t("common.updated") }}
        </div>
      </n-grid-item>
      <n-grid-item v-if="protocolInfo.updated_at" :span="3">
        <div class="text-right">
          {{ formatDate(protocolInfo.updated_at) }}
        </div>
      </n-grid-item>
    </n-grid>

    <!-- Protocol Metadata -->
    <protocol-metadata-display v-if="protocolInfo.metadata" :metadata="protocolInfo.metadata" :exclude-fields="['keywords', 'disciplines']" class="mt-4" />
  </n-card>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types"
import { useBoolean, useClosableMessage } from "@airalogy/composables"
import { copyToClip, getRealAiralogyId } from "@airalogy/shared"
import { $t } from "@airalogy/shared/locales"
import { formatDate as formatDateBase } from "@airalogy/shared/utils"
import IconIonCopyOutline from "~icons/ion/copy-outline"
import IconTablerCheck from "~icons/tabler/check"
import { NButton, NCard, NGrid, NGridItem, NIcon } from "naive-ui"
import ProtocolMetadataDisplay from "./protocol-metadata-display.vue"

interface Props {
  protocolInfo: ProtocolModels.ProjectProtocolInfo
  title?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: $t("page.protocol.protocolDetails"),
})

const message = useClosableMessage()

const { bool: copied, setTrue: setCopied, setFalse: setNotCopied } = useBoolean(false)
function copyProtocolId(e: MouseEvent) {
  e.stopPropagation()
  if (!props.protocolInfo.airalogy_id)
    return
  copyToClip(props.protocolInfo.airalogy_id)
  message.success($t("page.protocol.protocolIdCopied"))
  setCopied()
  setTimeout(() => {
    setNotCopied()
  }, 2000)
}

function formatDate(date: string) {
  return formatDateBase(date, "date")
}

const airalogyId = computed(() => {
  if (!props.protocolInfo) {
    return
  }

  return getRealAiralogyId(props.protocolInfo)
})
</script>
