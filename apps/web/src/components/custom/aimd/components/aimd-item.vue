<template>
  <n-form-item
    ref="formItemRef"
    :path="formPath"
    :rule="cellRules"
    :show-label="props.scope === 'research_variable'"
    :show-feedback="props.scope === 'var_table' || Boolean(assignerError)"
    :feedback="assignerError"
    :validation-status="assignerError ? 'error' : undefined"
    class="w-full text-start align-top"
    :class="{ 'aimd-cell-form-item': props.scope === 'var_table' }"
    :theme-overrides="
      props.scope === 'research_variable' ? themeOverridesRecord.formItem : undefined
    "
    :required="props.required"
    require-mark-placement="left"
    style="--n-label-height: 12px"
  >
    <template #label>
      <div ref="fieldContainerRef" class="aimd-field aimd-field--no-style aimd-field__label cursor-pointer">
        <span class="aimd-field__scope" :class="`aimd-field__scope--${props.type}`">
          {{ props.fieldType }}
        </span>
        <insert-wbr :text="props.prop" class="aimd-field__name flex-1" />
      </div>
    </template>
    <n-input-group v-if="showAssigner && isMdInput" class="assigner-input-group">
      <n-button
        type="primary"
        size="small"
        tertiary
        :theme-overrides="{ borderRadiusSmall: '0 0 0 6px', paddingSmall: '0 12px' }"
        @click="handleClick"
      >
        <template #icon>
          <icon-ion-stop-circle-outline v-if="assignerLoadingRecord[props.prop]" />
          <icon-local-calculator v-else />
        </template>
      </n-button>
      <aimd-input v-bind="props" :show-assigner="showAssigner" :class="[props.scope === 'var_table' && 'max-h-120px', showAssigner && 'flex-1 overflow-x-auto']" />
    </n-input-group>
    <aimd-input
      v-else
      v-bind="props"
      :class="props.scope === 'var_table' && 'max-h-120px'"
    />
  </n-form-item>
</template>

<script setup lang="ts">
import type { FormItemInst, FormItemRule } from "naive-ui"
import type { IAIMDItemProps } from "../types/aimd-types"
import InsertWbr from "@/components/common/insert-wbr.vue"
import { usePlatformAimdValidation } from "@/views/project-protocols/modules/protocol/composables/useAimdRecordValidation"
import { getAimdVarTableCellFieldKey } from "@airalogy/aimd-recorder"
import { BuiltInType } from "@airalogy/shared/enum/airalogy"
import { isUploadFileType } from "@airalogy/shared/utils"
import { themeOverridesRecord } from "../composables/themeOverrides"
import { useAIMDInject } from "../composables/useAIMDHelpers"

const props = defineProps<IAIMDItemProps>()
// Check if this is a reference field (used for ref_var)
const isReferenceField = props.isReference === true

/**
 * Compute the correct form path for validation
 * For table cells (var_table), use nested path: research_variable.${group}.value[${row}].${prop}
 * For regular fields, use: ${scope}.${prop}.value
 */
const formPath = computed(() => {
  if (isReferenceField) {
    return `ref-var.${props.scope}.${props.prop}.value`
  }

  // For table cells, use nested path for cell-level validation
  if (props.scope === "var_table" && props.info?.group !== undefined && props.info?.row !== undefined) {
    const { group, row } = props.info
    return `research_variable.${group}.value[${row}].${props.prop}`
  }

  return `${props.scope}.${props.prop}.value`
})

const validation = usePlatformAimdValidation()

const cellRules = computed<FormItemRule[]>(() => {
  if (
    !validation
    || props.scope !== "var_table"
    || props.info?.group === undefined
    || props.info?.row === undefined
  ) {
    return []
  }

  return [{
    trigger: ["change", "blur"],
    validator: () => validation.validateField(
      getAimdVarTableCellFieldKey(String(props.info.group), Number(props.info.row), props.prop),
      true,
    ),
  }]
})

// Keep backward compatible path ref
const path = formPath
const formItemRef = ref<FormItemInst & { validationErrored: boolean } | null>(null)

const { handleFormItemRef, handleAssignerClick, assignerLoadingRecord, assignerErrorRecord, handleAssignerCancel } = useAIMDInject()!
const parentRef = useParentElement()

const fieldContainerRef = ref<HTMLElement | null>(null)
const assignerStateKey = computed(() => {
  const { group, row } = props.info || {}
  return group !== undefined && row !== undefined
    ? `${group}.${props.prop}[${row}]`
    : props.prop
})

const assignerError = computed(() => {
  const error = assignerErrorRecord.value[assignerStateKey.value]
  return typeof error === "string" ? error : undefined
})

const showAssigner = computed(() => {
  const { assigner, model } = props
  if (!assigner) {
    return false
  }

  const { mode } = assigner
  return mode === "manual"
    || (mode === "auto_first" && typeof model.value === "undefined")
})
const isMdInput = computed(() => {
  // Include markdown, boolean, and all file types that support assigner button
  return ["md", BuiltInType.Md, BuiltInType.AiralogyMarkdown, "boolean"].includes(props.type)
    || isUploadFileType(props.type)
})

function handleClick() {
  if (assignerLoadingRecord.value[assignerStateKey.value]) {
    handleAssignerCancel(props)
  }
  else {
    handleAssignerClick(props)
  }
}

watch([formPath, formItemRef], ([newPath, newFormItemRef]) => {
  if (newFormItemRef) {
    handleFormItemRef(newPath, newFormItemRef)
  }
}, {
  immediate: true,
})

// Note: Validation is triggered on blur, not on value change
// This provides a better UX by not showing errors while the user is still typing

watch(() => formItemRef.value?.validationErrored, (isErrored) => {
  const parentEl = parentRef.value
  nextTick(() => {
    if (parentEl) {
      if (isErrored) {
        parentEl.classList.add("aimd-field-wrapper--error")
      }
      else {
        parentEl.classList.remove("aimd-field-wrapper--error")
      }
    }
  })
})
</script>

<style scoped lang="sass">
:deep(.n-form-item-feedback-wrapper)
  white-space: nowrap
  width: 100%
  border-radius: 0 0 4px 4px
  transition: all 0.3s ease-in-out
  position: absolute
  top: -5px
  z-index: 1000
  pointer-events: none
  white-space: pre-wrap
  &:not(:empty)
    pointer-events: auto
    background: rgba(255, 255, 255, 0.95)
    padding: 4px 8px
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15)

.n-form-item--no-label
  grid-template-columns: auto

// Assigner input group styling
.assigner-input-group
  display: flex
  align-items: stretch

  :deep(> .n-button)
    height: auto !important
    align-self: stretch

// Input border styling - connects with label above
// Use CSS variables to keep consistent with aimd.css
:deep(.n-input)
  --n-border: 1px solid var(--aimd-border-color, #90caf9)
  --n-border-hover: 1px solid var(--aimd-border-color, #90caf9)
  margin-top: -1px
  position: relative
  z-index: 1

:deep(.n-date-picker .n-input),
:deep(.n-select .n-base-selection)
  --n-border: 1px solid var(--aimd-border-color, #90caf9)
  --n-border-hover: 1px solid var(--aimd-border-color, #90caf9)

:deep(.n-dynamic-input)
  --n-border: 1px solid var(--aimd-border-color, #90caf9)
  margin-top: -1px

// Checkbox wrapper styling
:deep(.checkbox__wrapper)
  border-color: var(--aimd-border-color, #90caf9)
  margin-top: -1px

// Validation error styling - make error fields more visible
:global(.aimd-field-wrapper--error)
  :deep(.n-input),
  :deep(.n-date-picker .n-input),
  :deep(.n-select .n-base-selection),
  :deep(.n-input-number),
  :deep(.checkbox__wrapper)
    --n-border: 2px solid #d03050 !important
    --n-border-hover: 2px solid #d03050 !important
    --n-border-focus: 2px solid #d03050 !important
    box-shadow: 0 0 0 2px rgba(208, 48, 80, 0.2)

// Cell validation error styling (for var_table cells using n-form-item native error state)
.aimd-cell-form-item
  // Override absolute positioning from global styles for table cells
  :deep(.n-form-item-feedback-wrapper)
    position: static !important
    top: auto !important
    min-height: 0 !important

  &.n-form-item--error
    :deep(.n-input),
    :deep(.n-input-number),
    :deep(.n-select .n-base-selection)
      --n-border: 1px solid #d03050 !important
      --n-border-hover: 1px solid #d03050 !important
      --n-border-focus: 1px solid #d03050 !important
      border-color: #d03050 !important
      box-shadow: 0 0 0 2px rgba(208, 48, 80, 0.2)

    :deep(.n-form-item-feedback-wrapper)
      min-height: auto !important
      padding-top: 4px !important

    :deep(.n-form-item-feedback--error)
      color: #d03050
</style>
