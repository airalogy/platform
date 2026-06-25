<template>
  <markdown-editor
    :ref="handleEditorRef"
    v-model:text="model.value"
    raw-result
    class="!rounded-t-0"
    style="--editor-border-hover-color: var(--primary-color); --editor-border-focus-color: var(--primary-color);"
    :editor-style="{ borderRadius: '0 0 6px 6px' }"
    :readonly="props.disabled"
    :protocol-id="protocolId"
    :post-add-attachments="postAddAttachments"
    @update:text="handleUpdateText"
    @focus="handleFocus"
    @blur="handleBlur"
  >
    <template v-if="assigner || dependent" #action>
      <tooltip-button
        v-if="assigner"
        :tooltip="isLoading ? 'Assigner Assigning' : 'Assigner'"
        size="small"
        :icon-props="{ size: 14 }"
        quaternary
        circle
        :icon="isLoading ? CancelIcon : DoneIcon"
      />
      <tooltip-button
        v-else
        :tooltip="isLoading ? 'Assigner Dependent Assigning' : 'Assigner Dependent'"
        size="small"
        :icon-props="{ size: 14 }"
        quaternary
        circle
        :icon="UploadIcon"
      />
      <!-- <n-tooltip v-if="assigner">
        Assigner
        <template #trigger>
          <n-button size="small" theme>
            <n-icon size="16" >
              <icon-local-cloud-done v-if="isLoading === false " />
              <icon-mdi-cloud-cancel-outline v-else color="var(--n-text-color-disabled)" />
            </n-icon>
          </n-button>
        </template>
      </n-tooltip> -->
      <!-- <n-tooltip v-else>
        Assigner Dependent
        <template #trigger>
          <n-icon size="16" class="w-7 text-center">
            <icon-local-cloud-upload />
          </n-icon>
        </template>
      </n-tooltip> -->
    </template>
  </markdown-editor>
</template>

<script setup lang="ts">
import type { Editor } from "@tiptap/vue-3"
import type { TooltipInst } from "naive-ui"
import type { IAIMDInputProps } from "../../types/props"
import { postAddAttachments } from "@/service/api/attachments"
import { useProtocolInfoStore } from "@/views/project-protocols/hooks/useProtocolInfoStore"
import { MarkdownEditor } from "@airalogy/components"
import DoneIcon from "~icons/local/cloud-done"
import UploadIcon from "~icons/local/cloud-upload"
import CancelIcon from "~icons/mdi/cloud-cancel-outline"
import { type ShallowRef, toRefs } from "vue"
import { useAIMDInject } from "../../composables/useAIMDHelpers"

const props = defineProps<IAIMDInputProps>()
const { model, scope, prop, assigner, dependent, type, info } = toRefs(props)

const { handleFieldChange, handleScrollField, assignerLoadingRecord, handleRef, handleInputBlur } = useAIMDInject()!

// Check if this is a reference field (used for ref_var)
const isReferenceField = props.isReference === true
// Use a different ref key for reference fields to avoid conflicts
const refKey = isReferenceField ? `ref-var_${scope.value}_${prop.value}` : `${scope.value}_${prop.value}`

const isLoading = computed(() => assignerLoadingRecord.value[prop.value])
const wrapperRef = ref<HTMLElement | null>(null)
const editorRef = ref<{ editorRef: ShallowRef<Editor | null>, wrapperRef: Ref<HTMLElement | null> } | null>(null)

const tooltipRef = inject<Ref<TooltipInst | null>>("tooltipRef", ref(null))

const isEditorBubbleActive = injectLocal("isEditorBubbleActive", ref(false))
const { protocolId } = useProtocolInfoStore() || {}

function handleEditorRef(instance: any) {
  if (!instance) {
    return
  }

  editorRef.value = instance
  wrapperRef.value = instance.wrapperRef
  handleRef(refKey, instance.editorRef, type.value)
}

function handleFocus({ event }: { event: FocusEvent }) {
  // Reference fields don't need to trigger scroll events
  if (!isReferenceField) {
    handleScrollField(event, scope.value, prop.value)
  }
  nextTick(() => {
    isEditorBubbleActive.value = true
  })
  if (tooltipRef?.value) {
    tooltipRef.value.setShow(false)
  }
}

function handleBlur() {
  const el = unrefElement(wrapperRef)
  if (el && !isReferenceField) {
    // Reference fields don't need to trigger blur events
    handleInputBlur({ currentTarget: el } as any as FocusEvent, scope.value, prop.value)
  }
  nextTick(() => {
    isEditorBubbleActive.value = false
  })
}

function handleUpdateText(value: any) {
  // Reference fields don't allow updates (they're disabled anyway)
  if (isReferenceField) {
    return
  }
  return handleFieldChange({
    scope: scope.value,
    prop: prop.value,
    value,
    info: info?.value,
    assigner: assigner?.value,
    dependent: dependent?.value,
  })
}
</script>

<style scoped lang="sass">
.relative
  position: relative

.absolute
  position: absolute

.right-2
  right: 0.5rem

.top-2
  top: 0.5rem

.w-full
  width: 100%
</style>
