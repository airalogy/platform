<template>
  <n-card size="small" class="record-info-card">
    <!-- Basic Information Section -->
    <h3 class="mb-3 text-base font-medium">
      {{ title }}
    </h3>
    <n-grid :cols="4" :x-gap="8" :y-gap="8">
      <template v-if="recordInfo.recordId">
        <n-grid-item :span="1">
          <div class="text-gray-600">
            Record ID
          </div>
        </n-grid-item>
        <n-grid-item :span="3">
          <div class="flex items-center justify-end text-right">
            <span class="mr-2 font-mono">#{{ recordInfo.recordId }}</span>
            <n-button v-if="recordInfo.recordId" text size="tiny" @click.stop="copyRecordId">
              <template #icon>
                <n-icon>
                  <icon-tabler-check v-if="copied" />
                  <icon-ion-copy-outline v-else />
                </n-icon>
              </template>
            </n-button>
          </div>
        </n-grid-item>
      </template>

      <template v-if="recordInfo.recordVersion">
        <n-grid-item :span="1">
          <div class="text-gray-600">
            Version
          </div>
        </n-grid-item>
        <n-grid-item :span="3">
          <div class="text-right">
            v{{ recordInfo.recordVersion }}
          </div>
        </n-grid-item>
      </template>

      <template v-if="recordInfo.createdAt">
        <n-grid-item :span="1">
          <div class="text-gray-600">
            {{ $t("common.created") }}
          </div>
        </n-grid-item>
        <n-grid-item :span="3">
          <div class="text-right">
            {{ formatDate(recordInfo.createdAt) }}
          </div>
        </n-grid-item>
      </template>

      <template v-if="recordInfo.updatedAt">
        <n-grid-item :span="1">
          <div class="text-gray-600">
            {{ $t("common.updated") }}
          </div>
        </n-grid-item>
        <n-grid-item :span="3">
          <div class="text-right">
            {{ formatDate(recordInfo.updatedAt) }}
          </div>
        </n-grid-item>
      </template>

      <template v-if="recordInfo.operator">
        <n-grid-item :span="1">
          <div class="text-gray-600">
            Operator
          </div>
        </n-grid-item>
        <n-grid-item :span="3">
          <div class="text-right">
            {{ recordInfo.operator }}
          </div>
        </n-grid-item>
      </template>
    </n-grid>
  </n-card>
</template>

<script setup lang="ts">
import { useBoolean, useClosableMessage } from "@airalogy/composables"
import { copyToClip } from "@airalogy/shared"
import { $t } from "@airalogy/shared/locales"
import { formatDate as formatDateBase } from "@airalogy/shared/utils"
import IconIonCopyOutline from "~icons/ion/copy-outline"
import IconTablerCheck from "~icons/tabler/check"
import { NButton, NCard, NGrid, NGridItem, NIcon } from "naive-ui"

interface RecordInfo {
  recordId?: string
  recordVersion?: number
  createdAt?: string
  updatedAt?: string
  operator?: string
}

interface Props {
  recordInfo: RecordInfo
  title?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: "Record Information",
})

const message = useClosableMessage()

const { bool: copied, setTrue: setCopied, setFalse: setNotCopied } = useBoolean(false)

function copyRecordId(e: MouseEvent) {
  e.stopPropagation()
  if (!props.recordInfo.recordId)
    return
  copyToClip(props.recordInfo.recordId)
  message.success("Record ID copied to clipboard")
  setCopied()
  setTimeout(() => {
    setNotCopied()
  }, 2000)
}

function formatDate(date: string) {
  return formatDateBase(date, "date")
}
</script>
