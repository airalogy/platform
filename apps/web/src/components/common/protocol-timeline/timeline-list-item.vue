<template>
  <minimal-aimd-provider
    ref="providerContext"
    :protocol="protocolInfo"
    :protocol-id="protocolId || ''"
    :record-data="parsedFieldStructure "
    :readonly="true"
    :minimal="props.mode === 'timeline'"
  >
    <template #default="{ variableList, stepRefList, fieldModel }">
      <div v-if="providerContext?.context" class="min-h-20 w-full text-4" v-bind="$attrs">
        <define-field-header v-slot="{ scope, fieldKey, fieldValue, fieldData }">
          <div class="relative h-full w-60 border-r border-[#e5e5e5] bg-[#F3F5F9] p-3">
            <n-collapse-item v-if="fieldData.model" :name="`${scope}-${fieldKey}`" size="small" class="timeline-field-info">
              <template #header>
                <span class="break-all text-sm font-400"> {{ fieldData.title }} </span>
                <span v-if="fieldData.model?.required" class="text-red-500 font-bold"> &nbsp;* </span>
              </template>
              <template #header-extra>
                <tooltip-button
                  :tooltip="isShowingRawContent(scope, fieldKey) ? 'Hide raw content' : 'Show raw content'"
                  size="tiny"
                  quaternary
                  class="opacity-30 hover:opacity-100"
                  @click.stop="toggleRawContent(scope, fieldKey)"
                >
                  <template #icon>
                    <n-icon>
                      <icon-tabler-eye v-if="isShowingRawContent(scope, fieldKey)" />
                      <icon-tabler-code v-else />
                    </n-icon>
                  </template>
                </tooltip-button>
                <n-popover class="flex-shrink-0 !p-1" trigger="hover">
                  <template #trigger>
                    <div>
                      <tooltip-button
                        tooltip="Copy field data in JSON format"
                        size="tiny"
                        quaternary
                        class="opacity-30 hover:opacity-100"
                        placement="bottom"
                        @click.stop="handleCopy(JSON.stringify({ [fieldKey]: fieldValue }, null, 2))"
                      >
                        <template #icon>
                          <n-icon>
                            <icon-tabler-copy />
                          </n-icon>
                        </template>
                      </tooltip-button>
                    </div>
                  </template>

                  <n-button size="small" quaternary @click="handleCopy(fieldKey)">
                    Copy Key
                  </n-button>
                  <n-button size="small" quaternary @click="handleCopy(JSON.stringify(fieldValue, null, 0))">
                    Copy Value
                  </n-button>
                </n-popover>
              </template>
              <field-info-display
                :model="fieldData.model"
                :scope="(scope as ScopeFieldKey)"
                :show-title="false"
                :show-assigner-dependencies="false"
                :show-assigner-targets="false"
                class="mt-2 text-xs"
              />
            </n-collapse-item>
            <div v-else class="font-400">
              {{ fieldData.title }}
            </div>
          </div>
        </define-field-header>

        <define-timeline-field-row v-slot="{ item: listItem, isShowingRaw, fieldData }">
          <div class="field-row">
            <field-header
              :scope="listItem.scope"
              :field-key="listItem.prop"
              :field-value="listItem.model?.value"
              :field-data="fieldData"
            />
            <div v-if="isShowingRaw" class="size-full break-words rounded bg-gray-50 p-3 text-sm font-mono">
              {{ JSON.stringify(listItem.model?.value, null, 2) }}
            </div>
            <timeline-field-item
              v-else-if="hasValue(listItem)"
              v-bind="listItem"
              class="size-full p-3"
              :content-class="listItem.model.value?.airalogy_file_id ? '!size-full' : ''"
              :protocol-id="protocolId || ''"
            />
          </div>
        </define-timeline-field-row>

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
            <n-tag v-if="recordInfoData.recordVersion && recordInfoData.recordVersion > 1" type="success" size="small" class="mx-3">
              v {{ recordInfoData.recordVersion }}
            </n-tag>
            <!-- Protocol info popup button -->
            <n-popover
              v-if="protocolInfo && ((protocolId || item.protocolId) || item.recordId || item.recordVersion)"
              trigger="hover"
              placement="bottom-start"
              :show-arrow="false"
              raw
              class="max-w-lg rounded-lg bg-white p-2 shadow-lg"
            >
              <template #trigger>
                <n-button
                  size="tiny"
                  quaternary
                  class="ml-2 opacity-70 hover:opacity-100"
                >
                  <template #icon>
                    <n-icon size="16">
                      <icon-tabler-info-circle />
                    </n-icon>
                  </template>
                  {{ $t("common.info") }}
                </n-button>
              </template>
              <div class="w-96">
                <!-- Record Information -->
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

        <n-spin v-if="props.mode === 'preview'" :show="!(protocolInfo && parsedFieldStructure && mounted)" class="b-1 rounded-xl" content-class="p-5">
          <!-- <edit-protocol v-if="isEdit" :protocol="protocol" :protocol-id="props.item?.id" /> -->
          <n-form
            v-if="parsedFieldStructure"
            class="platform-aimd-form-preview"
            :rules="parsedFieldStructure.rules"
            :model="fieldModel"
          >
            <aimd-markdown-preview
              :content="protocolInfo?.aimd"
              :value="fieldModel"
              :render-options="aimdRenderOptions"
              :mermaid-component="MermaidBlock"
              :resolve-url="resolveProtocolFile"
              body-class="markdown-body"
              class="p-0"
              mode="edit"
              readonly
              @render:result="setMounted"
            />
          </n-form>
          <template v-if="!mounted">
            <n-skeleton v-for="item in 3" :key="item" class="mb-1" :style="{ width: `${Math.min(Math.random(), 0.3) * 100 + 30}%` }" />
          </template>
        </n-spin>
        <n-collapse v-else-if="parsedFieldStructure" size="small" :trigger-areas="['main', 'arrow']" arrow-placement="left" class="overflow-hidden border border-[#e5e5e5] rounded-xl">
          <template v-for="(list, idx) in [variableList, stepRefList]" :key="idx">
            <!-- Variable List -->
            <timeline-field-row
              v-for="fieldItem in list"
              :key="fieldItem.id"
              :item="fieldItem"
              :protocol-id="protocolId || ''"
              :is-showing-raw="isShowingRawContent(fieldItem.scope, fieldItem.prop)"
              :field-data="getFieldData(fieldItem.scope, fieldItem.prop)"
            />
          </template>
        </n-collapse>
      </div>
    </template>
  </minimal-aimd-provider>
</template>

<script setup lang="ts">
import type { IAIMDItemProps } from "@/components/custom/aimd/types/aimd-types"
import type { ITimelineItem } from "@/views/project-protocols/types"
import type { ScopeFieldKey } from "@airalogy/aimd-core/types"
import type { HTMLAttributes } from "vue"
import type { useAIMDInject } from "../../custom/aimd/composables/useAIMDHelpers"
import FieldInfoDisplay from "@/components/common/field-info-display.vue"
import TimelineFieldItem from "@/components/common/protocol-timeline/timeline-field-item.vue"
import { createPlatformAimdFormRenderers, getPropsFromNode } from "@/components/custom/aimd/composables/createPlatformAimdFormRenderers"
import ProtocolInfoCard from "@/components/protocol/protocol-info-card.vue"
import RecordInfoCard from "@/components/protocol/record-info-card.vue"
import { useAuthStore } from "@/store/modules/auth"
import { resolveProtocolFile as resolveProtocolFileUtil } from "@/utils/resolveProtocolFile"
import { useOrProvideProtocolInfoStore } from "@/views/project-protocols/hooks/useProtocolInfoStore"
import { getFieldStructure } from "@/views/project-protocols/modules/protocol/helpers/parseFieldStructure"
import { AimdMarkdownPreview } from "@airalogy/aimd-renderer/vue"
import MermaidBlock from "@airalogy/components/markdown-editor/modules/mermaid/mermaid-block.vue"
import TooltipButton from "@airalogy/components/tooltip-button.vue"
import { useBoolean, useClosableMessage } from "@airalogy/composables"
import { copyToClip } from "@airalogy/shared"
import { $t } from "@airalogy/shared/locales"
import { get as _get } from "lodash-es"

interface Props {
  item: ITimelineItem
  protocolId?: string
  showHeader?: boolean
  readonly?: boolean
  headerClass?: HTMLAttributes["class"]
  mode?: "timeline" | "draft" | "preview"
}

defineOptions({ name: "TimelineListItem", inheritAttrs: false })

const props = withDefaults(defineProps<Props>(), {
  showHeader: true,
  mode: "timeline",
})

// const _emit = defineEmits<{
//   "field-change": [payload: any]
//   "update:value": [val: string]
//   "add-row:table": [payload: any]
//   "remove-row:table": [payload: any]
//   "click:field": [event: MouseEvent]
// }>()

const authStore = useAuthStore()
const { protocolInfo, fetchProtocolInfo, isLoading } = useOrProvideProtocolInfoStore(null)
const { bool: mounted, setTrue: setMounted } = useBoolean()

// const {
//   // Models
//   fieldModel,
//   fieldRecordDefault,
//   setDomMounted,
// } = useFieldState(computed(() => ({
//   protocol: protocolInfo.value,
//   protocolId: props.item.protocolId || "",
//   recordData: props.item.field,
//   readonly: true,
// })), computed(() => protocolInfo.value?.aimd || ""))

// Raw content state per field
const showRawContentMap = ref<Record<string, boolean>>({})

// Helper functions for raw content management
function getFieldKey(scope: string, fieldKey: string): string {
  return `${scope}-${fieldKey}`
}

function toggleRawContent(scope: string, fieldKey: string): void {
  const key = getFieldKey(scope, fieldKey)
  showRawContentMap.value[key] = !showRawContentMap.value[key]
}

function isShowingRawContent(scope: string, fieldKey: string): boolean {
  const key = getFieldKey(scope, fieldKey)
  return showRawContentMap.value[key] || false
}

// Parse protocol info and get structured field data like protocol-add-record-form does
const parsedFieldStructure = computed(() => {
  // Extract protocol info from the item field data

  const protocol = toValue(protocolInfo)
  if (!protocol) {
    return null
  }
  const { aimd } = protocol

  // Use getFieldStructure to parse the protocol info properly
  return getFieldStructure({
    markdown: aimd || "",
    protocol,
    workflowField: ref(null),
    userInfo: authStore.userInfo,
    recordData: props.item.field,
    isReadonly: true,
  }, props.mode === "draft")
})

// Resolve file paths for protocol assets
async function resolveProtocolFile(src: string): Promise<{ url: string } | null> {
  const protocol = toValue(protocolInfo)
  if (!protocol?.id)
    return null
  return resolveProtocolFileUtil(src, protocol.id)
}

const message = useClosableMessage()

function handleCopy(content: any) {
  if (!content) {
    return
  }
  copyToClip(content)
  message.success("Copied to clipboard")
}

// Computed data for record info card
const recordInfoData = computed(() => ({
  recordId: props.item.recordId,
  recordVersion: props.item.recordVersion,
  createdAt: props.item.record?.metadata?.record_current_version_submission_time,
  operator: props.item.operator,
}))

function getFieldData(scope: string, fieldKey: string) {
  const { field } = toValue(parsedFieldStructure) || {}
  if (!field) {
    return { model: null, title: fieldKey }
  }

  const model = _get(field, [scope, fieldKey]) || null
  const title = _get(field, [scope, fieldKey, "title"]) || fieldKey

  return { model, title }
}
// Create reusable template for field header
const [DefineFieldHeader, FieldHeader] = createReusableTemplate<{
  scope: string
  fieldKey: string
  fieldValue: any
  fieldData: { model: any, title: string }
}>({ inheritAttrs: false })

// Create reusable template for field row
const [DefineTimelineFieldRow, TimelineFieldRow] = createReusableTemplate<{
  item: IAIMDItemProps
  protocolId: string
  isShowingRaw: boolean
  fieldData: { model: any, title: string }
}>({ inheritAttrs: false })

function hasValue(item: IAIMDItemProps) {
  return item.model?.value !== undefined && item.model?.value !== null
}
watch([() => props.protocolId, () => props.item.protocolVersion], ([newVal, protocolVersion]) => {
  if (newVal && !isLoading.value) {
    fetchProtocolInfo(newVal, protocolVersion, undefined, true)
  }
}, { immediate: true })

const providerContext = ref<{ context: ReturnType<typeof useAIMDInject> }>()

// Create AIMD renderers for unified system
const aimdRenderers = computed(() => {
  const context = providerContext.value?.context
  if (!context) {
    return {}
  }

  return createPlatformAimdFormRenderers({
    getTokenProps: (node) => {
      const variableList = toValue(context.variableList)
      if (!variableList) {
        return null
      }
      return getPropsFromNode(node, variableList)
    },
  })
})
const aimdRenderOptions = computed(() => ({ aimdRenderers: aimdRenderers.value }))
</script>

<style scoped lang="sass">
:deep(.n-descriptions-table-header)
  width: 30%

.timeline-field-info
  :deep(.n-collapse-item-arrow)
    @apply color-text-secondary opacity-30 hover:opacity-100 !w-4 !h-4 -mt-0.5
  :deep(.n-collapse-item__header)
    @apply flex-wrap
  :deep(.n-collapse-item__header-main)
    padding: 0

  :deep(.n-collapse-item__content-wrapper)
    padding-top: 0

  :deep(.n-collapse-item__content-inner)
    padding-top: 0!important

.field-row
  @apply grid grid-cols-[minmax(auto,max-content)_minmax(0,1fr)] items-start border-b border-[#e5e5e5] last:border-b-0

:deep(.n-form-item-label__text)
  flex: 1
</style>
