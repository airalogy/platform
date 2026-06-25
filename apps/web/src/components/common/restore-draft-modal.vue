<template>
  <n-button
    v-if="Boolean(draft)"
    size="medium"
    type="primary"
    :disabled="loading"
    :loading="loading"
    class="mr-4 px-4"
    quaternary
    @click="showModal"
  >
    {{ $t("page.protocol.draft.restoreButton") }}
  </n-button>
  <n-button
    size="medium"
    type="primary"
    :disabled="loading"
    :loading="loading"
    class="mr-4 px-4"
    ghost
    @click="handleSaveDraft"
  >
    {{ $t("page.protocol.draft.saveButton") }}
  </n-button>
  <n-modal
    v-model:show="isShown"
    :title="$t('page.protocol.draft.title')"
    :show-icon="false"
    display-directive="if"
    :mask-closable="false"
    preset="dialog"
    class="draft__modal !w-80vw"
    action-class="flex-wrap justify-start items-center"
  >
    <template #action>
      <n-checkbox v-model:checked="deleteDraft">
        {{ $t("page.protocol.draft.delete") }}
      </n-checkbox>
      <n-checkbox v-model:checked="mergeDraft">
        {{ $t("page.protocol.draft.merge") }}
      </n-checkbox>

      <n-button @click="hideModal">
        {{ $t("common.cancel") }}
      </n-button>
      <n-button type="primary" @click="handleRestoreDraft">
        {{ $t("page.protocol.draft.restoreAction") }}
      </n-button>
    </template>
    <template v-if="Boolean(draft)">
      <div>{{ $t("page.protocol.draft.prompt") }}</div>

      <n-tabs v-model:value="draftViewTab" type="line" class="mt-4">
        <n-tab-pane name="preview" :tab="$t('page.protocol.draft.previewTab')">
          <n-collapse v-if="draft?.data" :default-expanded-names="['preview']">
            <n-collapse-item name="preview">
              <template #header>
                <span>{{ $t("page.protocol.draft.previewTitle") }}</span>
                <n-text class="ml-1" :depth="3">
                  ({{ $t("page.protocol.draft.lastModified") }}: {{ lastModified }})
                </n-text>
              </template>
              <timeline-list-item
                class="max-h-40vh overflow-y-auto"
                :protocol-id="props.protocolId"
                :item="draftPreviewItem"
                :is-draft="true"
                :show-header="false"
                mode="draft"
              />
            </n-collapse-item>
          </n-collapse>
          <div v-else class="text-gray-500 italic">
            {{ $t("page.protocol.draft.noPreview") }}
          </div>
        </n-tab-pane>
        <n-tab-pane name="json" :tab="$t('page.protocol.draft.jsonTab')">
          <div v-if="draft?.data" class="draft-json max-h-40vh overflow-y-auto">
            <pre>{{ draftJson }}</pre>
          </div>
          <div v-else class="text-gray-500 italic">
            {{ $t("page.protocol.draft.noJson") }}
          </div>
        </n-tab-pane>
      </n-tabs>
    </template>
    <div v-else>
      {{ $t("page.protocol.draft.noDraft") }}
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import type { IDraftData } from "@/views/project-protocols/modules/protocol/composables/useDraftManagement"
import type { ITimelineItem } from "@/views/project-protocols/types"
import type { IRecordData } from "@airalogy/shared"
import type { ProtocolModels } from "@airalogy/shared/types/models"
import type { FieldRecord } from "../../views/project-protocols/modules/protocol/helpers/parseFieldStructure"
import TimelineListItem from "@/components/common/protocol-timeline/timeline-list-item.vue"
import { useClosableMessage, useLoading, useShowModal } from "@/composables"
import { useDraftManagement } from "@/views/project-protocols/modules/protocol/composables/useDraftManagement"

interface IProps {
  data: Partial<IRecordData>
  protocolId: string
  fieldModel: FieldRecord
  protocol: ProtocolModels.ProtocolInfo | null
}

const props = defineProps<IProps>()

const emit = defineEmits<IEmits>()

interface IEmits {
  (e: "update:data", data: IRecordData): void
  (e: "update:field-model", fieldModel: FieldRecord): void
  (e: "restore:draft", data: Partial<IRecordData>): boolean
}

const { showModal, hideModal, isShown } = useShowModal()
const { loading } = useLoading()
const message = useClosableMessage()

const data = useVModel(props, "data", emit)

const { getDraft, saveDraft, deleteDraft: handleDeleteDraft, prepareRestoreDraft, formatLastModified, transformDraftForPreview } = useDraftManagement(props.protocol, data)

const draft = ref<IDraftData | null>(getDraft(props.protocolId))

const lastModified = computed(() => formatLastModified(draft.value))
const draftViewTab = ref<"preview" | "json">("preview")

const draftPreviewItem = computed(() => {
  const transformedData = draft.value?.data ? transformDraftForPreview(draft.value.data) : {} as any as IRecordData

  console.debug("Draft preview data (transformed):", transformedData)

  return {
    id: "draft-preview",
    time: lastModified.value,
    field: transformedData,
  } as ITimelineItem
})

const draftJson = computed(() => {
  if (!draft.value?.data) {
    return ""
  }
  try {
    return JSON.stringify(draft.value.data, null, 2)
  }
  catch (error) {
    console.error("Failed to stringify draft data:", error)
    return ""
  }
})

const deleteDraft = ref(false)
const mergeDraft = ref(false)

function handleSaveDraft() {
  saveDraft(props.protocolId, props.data)
  draft.value = getDraft(props.protocolId)
  draftViewTab.value = "preview"
}

function handleRestoreDraft() {
  if (!draft.value)
    return

  const draftData = prepareRestoreDraft(props.protocolId, mergeDraft.value, deleteDraft.value)

  if (!draftData) {
    message.error("No draft data found.")
    return
  }

  const result = emit("restore:draft", draftData)
  if (result) {
    if (deleteDraft.value) {
      handleDeleteDraft(props.protocolId)
      draft.value = null
    }
  }

  hideModal()
}
</script>

<style lang="sass">
.draft__modal
  .n-collapse .n-collapse-item .n-collapse-item
    margin-left: 0!important

.draft-json
  background: var(--n-color)
  border: 1px solid var(--n-border-color)
  border-radius: 6px
  padding: 12px
  font-size: 12px
  line-height: 1.4
  white-space: pre-wrap
  word-break: break-word
</style>
