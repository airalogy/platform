<template>
  <div>
    <define-modal-footer v-slot="{ wrapperClass }">
      <!-- <template v-if="props.node?.isEnd && props.node?.readonly">
        <span v-if="showFinalConclusion" class="ml-auto">End Workflow</span>
        <span v-else class="ml-auto">Continue Workflow</span>
        <n-switch v-model:value="showFinalConclusion" />
      </template> -->

      <div class="w-full flex items-center gap-3" :class="wrapperClass">
        <n-button
          class="ml-auto !min-w-20"
          @click="emit('update:show', false)"
        >
          {{ $t("common.cancel") }}
        </n-button>

        <n-button
          v-if="type === 'final' && !props.node?.readonly" type="warning" class="!min-w-20"
          @click="handleConfirm"
        >
          {{ $t("page.protocol.workflow.end") }}
        </n-button>

        <n-button v-else type="primary" class="!min-w-20" @click="handleConfirm">
          {{ $t("common.confirm") }}
        </n-button>
      </div>
    </define-modal-footer>
    <div v-if="props.editorOnly && props.node?.status !== 'done'">
      <n-form-item
        :label="conclusionLabel" required path="conclusion"
        label-style="font-size: 16px; font-weight: 600"
      >
        <markdown-editor v-model:text="intermediateModel.intermediate" raw-result class="h-fit" :post-add-attachments="postAddAttachments">
          <template v-if="!props.node?.hideAIButton" #action>
            <ai-button
              :button-props="{ onClick: () => handleGenerateConclusion(type) }"
              button-class="absolute right-2 bottom-2" :tooltip="$t('page.protocol.workflow.aiGenerateConclusion')"
            >
              AI
            </ai-button>
          </template>
        </markdown-editor>
      </n-form-item>

      <modal-footer />
    </div>
    <div
      v-else class="conclusion-modal"
      :class="{ 'conclusion-modal--collapsed': collapsed, 'ai-generated': nodeRecord?.isConclusionGenerated }"
    >
      <div class="conclusion-modal__header" @click="collapsed = !collapsed">
        <div class="w-full flex items-center justify-between">
          <h3>{{ props.title || props.node?.name }}</h3>
          <div class="flex items-center">
            <!-- <n-tag v-if="nodeRecord?.isConclusionGenerated" type="info" size="small" round class="box__badge mr-3">
              AI Generated
            </n-tag> -->
            <n-tag v-if="props.node?.status" :type="getStatusType(props.node.status)" class="mr-2">
              {{ statusLabel }}
            </n-tag>

            <n-icon :class="{ 'rotate-180': !collapsed }" class="transition-transform">
              <icon-ion-chevron-down />
            </n-icon>
          </div>
        </div>
      </div>

      <div v-show="!collapsed" class="conclusion-modal__content">
        <n-form class="max-h-80vh overflow-y-auto b-t-1 p-4 pt-0" :model="intermediateModel" :rules="rules">
          <n-form-item required path="conclusion" label-style="font-size: 16px; font-weight: 600">
            <markdown-editor v-model:text="intermediateModel.intermediate" raw-result class="h-fit" :post-add-attachments="postAddAttachments">
              <template v-if="!props.node?.hideAIButton" #action>
                <ai-button
                  :button-props="{ onClick: () => handleGenerateConclusion(type) }"
                  button-class="absolute right-2 bottom-2" :tooltip="$t('page.protocol.workflow.aiGenerateConclusion')"
                >
                  AI
                </ai-button>
              </template>
            </markdown-editor>
          </n-form-item>
        </n-form>

        <modal-footer wrapper-class="p-4" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { SelectedNode, WorkflowModel } from "@/store/modules/workflow"
import type { NButton } from "naive-ui/es/button"
import { useFormRules } from "@/composables"
import { postAddAttachments } from "@/service/api/attachments"
import MarkdownEditor from "@airalogy/components/markdown-editor/index.vue"
import { useI18n } from "vue-i18n"

const props = withDefaults(defineProps<IProps>(), {
  editorOnly: false,
})

const emit = defineEmits<IEmits>()
const { t, locale } = useI18n()

// Create reusable modal footer template
const [DefineModalFooter, ModalFooter] = createReusableTemplate<{ wrapperClass?: string }>()

interface IProps {
  node?: SelectedNode | null
  workflowModel: WorkflowModel
  title?: string
  editorOnly?: boolean
  collapse?: boolean
}

interface SetConclusionIconPayload {
  final: string
  intermediate: string
  id?: string
  type: "intermediate" | "final" | "both"
  node?: SelectedNode | null
}

interface GenerateConclusionPayload {
  id?: string
  type: "intermediate" | "final"
  node?: SelectedNode | null
}

interface IEmits {
  (e: "update:show", value: boolean): void
  (e: "update:model", value: any): void
  (e: "action:generate-conclusion", payload: GenerateConclusionPayload): void
  (e: "action:end-workflow", payload: SetConclusionIconPayload): void
  (e: "action:set-conclusion", payload: SetConclusionIconPayload): void
}

const intermediateModel = ref<{ final: string, intermediate: string }>({
  final: props.workflowModel.finalResearchConclusion || "",
  intermediate: props.node?.conclusion || "",
})

interface FormModel {
  final?: string
  intermediate?: string
}

const { defaultRequiredRule } = useFormRules()
const rules: Partial<Record<keyof FormModel, App.Global.FormRule[]>> = {
  final: [defaultRequiredRule],
  intermediate: [defaultRequiredRule],
}

const type = computed(() => {
  if (props.node) {
    if (props.node.conclusionType) {
      return props.node.conclusionType
    }

    return props.node.isEnd ? "both" : "intermediate"
  }

  return "final"
})

const conclusionLabel = computed(() => {
  if (type.value === "final")
    return t("page.protocol.workflow.finalConclusionLabel")
  if (type.value === "both")
    return t("page.protocol.workflow.finalConclusionLabel")
  return t("page.protocol.workflow.intermediateConclusionLabel")
})

const statusLabel = computed(() => {
  if (!props.node?.status)
    return ""
  const statusKey = `page.protocol.workflow.status.${props.node.status}` as I18n.I18nKey
  return t(statusKey)
})

function handleGenerateConclusion(generateType: "intermediate" | "final") {
  emit("action:generate-conclusion", {
    node: props.node,
    type: generateType,
    id: props.node?.id,
  } satisfies GenerateConclusionPayload)
}

function handleConfirm() {
  const payload: SetConclusionIconPayload = {
    ...intermediateModel.value,
    type: type.value,
    id: props.node?.id,
    node: props.node,
  }

  if (type.value === "final" || type.value === "both") {
    emit("action:end-workflow", payload)
  }
  else {
    emit("action:set-conclusion", payload)
  }
}

// onMounted(() => {
//   if (props.node) {
//     const { id } = props.node

//     const intermediate = id ? props.workflowModel?.record[id]?.conclusion || "" : ""
//     const final = props.workflowModel?.finalResearchConclusion || ""

//     if (props.node.conclusionType === "final") {
//       showFinalConclusion.value = true
//     }

//     intermediateModel.value = { intermediate, final }
//   }
// })

const nodeRecord = computed(() => (props.node ? props.workflowModel?.record[props.node.id] : null))

watch(
  nodeRecord,
  (record) => {
    if (record) {
      intermediateModel.value.intermediate = record.conclusion || ""
    }
  },
  { immediate: true, deep: true },
)

watch(
  () => props.workflowModel.finalResearchConclusion,
  (val) => {
    if (props.node?.isEnd) {
      intermediateModel.value.final = val || ""
    }
  },
  { immediate: true },
)

// Add collapsed state
const collapsed = ref(true)

function getStatusType(status: string): "default" | "success" | "warning" | "error" {
  switch (status) {
    case "done":
      return "success"
    case "init":
      return "default"
    case "generated":
      return "warning"
    default:
      return "default"
  }
}
</script>

<style scoped lang="sass">
.conclusion-modal
  background: white
  border-radius: 8px
  transition: all 0.3s ease

  &:hover
    box-shadow: 0 2px 12px rgba(0,0,0,0.1)
  &--collapsed
    .conclusion-modal__content
      height: 0
      overflow: hidden

  &__header
    padding: 12px 4px
    cursor: pointer
    display: flex
    justify-content: space-between
    align-items: center

    h3
      margin: 0
      font-size: 18px
      font-weight: 600
      overflow: hidden
      text-overflow: ellipsis
      white-space: nowrap
      max-width: calc(100% - 100px)

  &__content
    transition: height 0.3s ease

  &__footer
    padding: 16px 24px
    border-top: 1px solid #eee

  .flex
    display: flex

  .items-center
    align-items: center

  .justify-between
    justify-content: space-between

  .w-full
    width: 100%

  .mr-2
    margin-right: 0.5rem

.ai-generated
  --ai-linear: linear-gradient(130deg, rgba(26, 121, 255, 0.8) 0%, rgba(122, 75, 255, 0.8) 100%)
  position: relative

  .box__badge
    background: var(--ai-linear)
    text-align: center
    padding: 0 8px
    color: white
    font-size: 12px
</style>
