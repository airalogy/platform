<template>
  <n-form-item
    :ref="(el: any) => handleFormItemRef(`${scope}_${prop}`, el)"
    :path="`${scope}.${prop}.value`"
    label-placement="top"
    class="w-full pl-4 text-start"
    :class="{
      'form__item--check':
        model.scope === 'research_check' || model.type === 'checkbox' || model.type === 'boolean' || model?.raw?.check,
    }"
    :show-require-mark="false"
    :show-feedback="Boolean(assignerError)"
    :feedback="assignerError"
    :validation-status="assignerError ? 'error' : undefined"
  >
    <template #label>
      <n-collapse-item :name="`${scope}-${prop}`" class="triangle-right !mb-3 !ml-3" :class="`triangle-right--${scopeKeyRecord[scope]}`">
        <template #header>
          <n-ellipsis
            v-if="Boolean(model.title || model.label)"
            class="mr-auto text-4 font-500 capitalize"
          >
            <span> {{ model.title || model.label }} </span>
            <AimdRequiredMarker v-if="model.required" :label="$t('common.required')" />
          </n-ellipsis>
        </template>
        <field-info-display
          :model="model"
          :scope="scope"
          :ajv-info="ajvInfo"
          :enum-info="enumInfo"
          :type-map="typeMap"
          :var-scope-record="varScopeRecord"
          :is-var-table="isVarTable"
          :show-title="false"
        />
      </n-collapse-item>
    </template>

    <template #default>
      <div class="form-input-wrapper">
        <form-item-input
          v-if="model?.value?.rrec_airalogy_id"
          v-bind="{
            ...props,
            model: {
              ...props.model,
              value: props.model.value.rrec_airalogy_id,
              type: 'text',
              disabled: true,
            },
          }"
        />
        <div v-else-if="showAssigner" class="assigner-input-group">
          <n-button
            type="primary"
            size="small"
            tertiary
            class="assigner-btn"
            :loading="assignerLoadingRecord[prop]"
            @click="handleAssignerClick(props)"
          >
            <template #icon>
              <n-icon size="18">
                <icon-local-calculator />
              </n-icon>
            </template>
          </n-button>
          <form-item-input v-bind="props" />
        </div>
        <form-item-input v-else v-bind="props" />
      </div>
    </template>
  </n-form-item>
</template>

<script setup lang="ts">
import type { IRecordDataKey, ScopeFieldKey } from "@airalogy/aimd-core/types"
import type { ProtocolModels } from "@airalogy/shared/types"
import type { ValidateFunction } from "ajv"
import type { IFieldItem } from "../types/types"
import FieldInfoDisplay from "@/components/common/field-info-display.vue"
import { AimdRequiredMarker } from "@airalogy/aimd-recorder"
import { scopeKeyRecord } from "@airalogy/shared/utils/schema/constants"
import { useProtocolFormInject } from "../composables/useProtocolForm"
import FormItemInput from "./form-item-input.vue"

const props = defineProps<{
  model: IFieldItem
  scope: ScopeFieldKey
  prop: string
  ajvInfo?: any
  enumInfo?: any
  inputId: string
  assigner?: ProtocolModels.Assigner
  dependent?: { name: string, scope: IRecordDataKey }[]
  id: string
}>()

const ajvInfo = toRef(props, "ajvInfo") as any as Ref<
  Omit<ValidateFunction, "schema"> & { schema?: Record<string, any> }
>
const { handleFormItemRef, typeMap, varScopeRecord, handleAssignerClick, isVarTable, assignerLoadingRecord, assignerErrorRecord } = useProtocolFormInject()!

const assignerError = computed(() => {
  const error = assignerErrorRecord.value[props.prop]
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
</script>

<style lang="sass" scoped>
.wrapped-tag
  @apply whitespace-pre-wrap break-all min-h-fit

.form__item--check
  :deep(.n-form-item-blank)
    flex-direction: row

:deep(.property-label)
  @apply vertical-middle! max-w-full inline-block

  &::first-letter
    text-transform: uppercase

// Form input wrapper - ensure left alignment
.form-input-wrapper
  display: flex
  justify-content: flex-start
  width: 100%

// Assigner input group styling
.assigner-input-group
  display: flex
  align-items: stretch
  width: 100%

  .assigner-btn
    height: auto
    min-height: 40px
    border-radius: 3px 0 0 3px
    flex-shrink: 0

  :deep(.upload-btn)
    border-radius: 0 3px 3px 0
    border-left: 0
    height: auto
    min-height: 40px

  :deep(.file-card)
    flex: 1
    border-radius: 0 3px 3px 0
    margin-left: -1px
</style>
