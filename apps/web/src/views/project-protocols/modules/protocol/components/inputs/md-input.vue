<template>
  <markdown-editor
    :ref="handleEditorRef"
    v-model:text="model.value"
    raw-result
    class="size-full"
    style="--editor-border-hover-color: var(--primary-color); --editor-border-focus-color: var(--primary-color);"
    :editor-style="{ borderRadius: '0 0 6px 6px' }"
    preset="simple"
    :readonly="readonly || commonProps.disabled"
    :post-add-attachments="postAddAttachments"
    :resolve-file="getCachedAttachment"
    @update:text="handleUpdateText"
    @focus="handleFocus"
    @blur="handleBlur"
  >
    <template v-if="assigner || dependent" #action>
      <template v-if="assigner">
        <icon-local-cloud-done v-if="isLoading === false" />
        <icon-mdi-cloud-cancel-outline v-else color="var(--n-text-color-disabled)" />
      </template>
      <template v-else>
        <icon-local-cloud-upload />
      </template>
    </template>
  </markdown-editor>
</template>

<script setup lang="ts">
import type { InputPropsOptions } from "../../types/input-props"
import { getCachedAttachment, postAddAttachments } from "@/service/api/attachments"
import { MarkdownEditor } from "@airalogy/components"
import { useInputProps } from "../../composables/useInputProps"
import { useProtocolFormInject } from "../../composables/useProtocolForm"

const props = defineProps<InputPropsOptions>()
const { model, scope, prop, assigner, dependent, info, readonly } = toRefs(props)
const { handleFieldChange, assignerLoadingRecord, handleRef, handleScrollField, handleInputBlur } = useProtocolFormInject()!

const wrapperRef = ref<HTMLElement | null>(null)

function handleEditorRef(el: any) {
  wrapperRef.value = el
  handleRef(`${scope.value}_${prop.value}`, el)
}

function handleFocus({ event }: { event: FocusEvent }) {
  handleScrollField(event, scope.value, prop.value)
}

function handleBlur() {
  const el = unrefElement(wrapperRef)
  if (el) {
    handleInputBlur({ currentTarget: el } as any as FocusEvent, scope.value, prop.value)
  }
}

function handleUpdateText(value: any) {
  return handleFieldChange({
    scope: scope.value,
    prop: prop.value,
    value,
    info: info?.value,
    assigner: assigner?.value,
    dependent: dependent?.value,
  })
}

const { commonProps } = useInputProps(props)
const isLoading = computed(() => assignerLoadingRecord.value[prop.value])
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
