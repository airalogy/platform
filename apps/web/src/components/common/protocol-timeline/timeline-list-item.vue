<template>
  <div class="min-h-20 w-full text-4" v-bind="$attrs">
    <div v-if="props.showHeader" class="mb-4 flex items-center" :class="props.headerClass">
      <slot name="header-prefix" />
      <slot name="header-content">
        <span class="inline-block whitespace-nowrap align-top">{{ item.time }}</span>

        <router-link
          v-if="item.operatorUsername"
          :to="{ name: 'user-profile', params: { username: item.operatorUsername } }"
          class="ml-4 inline-block align-top color-text-secondary hover:color-[#1A79FF]"
        >
          @{{ item.operator }}
        </router-link>
        <span v-else-if="item.operator" class="ml-4 inline-block align-top color-text-secondary">
          {{ item.operator }}
        </span>
        <n-tag
          v-if="recordInfoData.recordVersion && recordInfoData.recordVersion > 1"
          type="success"
          size="small"
          class="mx-3"
        >
          v {{ recordInfoData.recordVersion }}
        </n-tag>
        <n-popover
          v-if="
            protocolInfo && (protocolId || item.protocolId || item.recordId || item.recordVersion)
          "
          trigger="hover"
          placement="bottom-start"
          :show-arrow="false"
          raw
          class="max-w-lg rounded-lg bg-white p-2 shadow-lg"
        >
          <template #trigger>
            <n-button size="tiny" quaternary class="ml-2 opacity-70 hover:opacity-100">
              <template #icon>
                <n-icon size="16">
                  <icon-tabler-info-circle />
                </n-icon>
              </template>
              {{ $t("common.info") }}
            </n-button>
          </template>
          <div class="w-96">
            <record-info-card
              v-if="item.recordId || item.recordVersion"
              :record-info="recordInfoData"
              class="mt-2 border-0"
            />
            <protocol-info-card
              v-if="protocolInfo"
              :protocol-info="protocolInfo"
              :title="$t('page.protocol.protocolDetails')"
              class="border-0"
            />
          </div>
        </n-popover>
      </slot>
      <slot name="header-suffix" />
    </div>

    <n-spin
      :show="!protocolInfo || isLoading"
      class="border border-[#e5e5e5] rounded-xl"
      content-class="p-5"
    >
      <readonly-record-preview
        v-if="protocolInfo?.aimd && previewRecord"
        :aimd="protocolInfo.aimd"
        :protocol-id="protocolId"
        :record="previewRecord"
      />
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import type { ITimelineItem } from "@/views/project-protocols/types"
import type { HTMLAttributes } from "vue"
import ProtocolInfoCard from "@/components/protocol/protocol-info-card.vue"
import RecordInfoCard from "@/components/protocol/record-info-card.vue"
import { useOrProvideProtocolInfoStore } from "@/views/project-protocols/hooks/useProtocolInfoStore"
import ReadonlyRecordPreview from "@/views/project-protocols/modules/readonly-record-preview.vue"

interface Props {
  item: ITimelineItem
  protocolId?: string
  showHeader?: boolean
  headerClass?: HTMLAttributes["class"]
  recordData?: object
}

defineOptions({ name: "TimelineListItem", inheritAttrs: false })

const props = withDefaults(defineProps<Props>(), {
  showHeader: true,
})

const { protocolInfo, fetchProtocolInfo, isLoading } = useOrProvideProtocolInfoStore(null)
const previewRecord = computed(() => props.recordData || props.item.record || props.item.field)

const recordInfoData = computed(() => ({
  recordId: props.item.recordId,
  recordVersion: props.item.recordVersion,
  createdAt: props.item.record?.metadata?.record_current_version_submission_time,
  operator: props.item.operator,
}))

watch(
  [() => props.protocolId, () => props.item.protocolVersion],
  ([newVal, protocolVersion]) => {
    if (newVal && !isLoading.value) {
      fetchProtocolInfo(newVal, protocolVersion, undefined, true)
    }
  },
  { immediate: true },
)
</script>

<style scoped lang="sass">
:deep(.n-descriptions-table-header)
  width: 30%
</style>
