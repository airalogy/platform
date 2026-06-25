<template>
  <n-collapse v-model:expanded-names="expandedNamesRef" display-directive="show" arrow-placement="right">
    <div v-if="Array.isArray(itemInfoList)" class="border-l pl-4">
      <h3 class="text-4 font-bold" @click="handleScrollView">
        {{ item.group }}
      </h3>
      <base-protocol-form-item
        v-for="(groupItem, idx) in item.children"
        :id="groupItem.id"
        :key="idx"
        :prop="groupItem.group || ''"
        :model="groupItem"
        :scope="scope"
        :input-id="`form-${scope}-${groupItem.group}.${groupItem.label}`"
        :assigner="groupItem.assigner"
        :dependent="groupItem.dependent"
      />
    </div>
    <base-protocol-table-form-item
      v-else-if="item.type === 'table'"
      :id="item.id"
      :prop="propInfo"
      :model="item"
      :ajv-info="ajv"
      :scope="scope"
      :enum-info="enumInfo"
      :input-id="`form-${scope}-${propInfo}`"
      :assigner="item.assigner"
      :dependent="item.dependent"
      :dependent-record="item.dependentRecord"
      :assigner-record="item.assignerRecord"
    />
    <base-protocol-form-item
      v-else-if="item.id"
      :id="item.id"
      :prop="propInfo"
      :model="item"
      :ajv-info="ajv"
      :scope="scope"
      :enum-info="enumInfo"
      :input-id="`form-${scope}-${propInfo}`"
      :assigner="item.assigner"
      :dependent="item.dependent"
    />
  </n-collapse>
</template>

<script setup lang="ts">
import type { FieldKey, ScopeFieldKey } from "@airalogy/aimd-core/types"
import type { IFieldItem } from "./types/types"
import { themeSettings } from "@/theme/settings"
import { getRefValue, mergeEnumRefValue } from "@airalogy/shared/utils"
import BaseProtocolFormItem from "./components/base-protocol-form-item.vue"
import BaseProtocolTableFormItem from "./components/base-protocol-table-form-item.vue"
import { type IEmits, useProtocolFormProvide } from "./composables/useProtocolForm"

const props = withDefaults(defineProps<IProps>(), {
  item: () =>
    ({
      label: "",
      disabled: false,
      required: false,
      scope: "" as FieldKey,
      title: "",
      type: "textarea",
      id: "",
    }) as IFieldItem,
  name: "",
  propInfo: "",
  ajv: {},
  varScopeRecord: () => ({}),
  tableRecord: () => ({}),
  shouldScroll: false,
})

const emit = defineEmits<IEmits>()

export interface IProps {
  item: IFieldItem
  scope: ScopeFieldKey
  propInfo: string
  ajv?: any
  varScopeRecord: Record<string, string>
  tableRecord: Record<
    string,
    Record<
      string,
      Record<"title" | "type" | "description" | "format", string> & { sequence: number }
    >
  >
  readonly?: boolean
  protocolId: string
  assignerLoadingRecord: Record<string, boolean | undefined>
  assignerErrorRecord: Record<string, string | boolean | undefined>
  shouldScroll: boolean
}
const itemInfoList = computed(() => {
  const { children } = props.item
  return Array.isArray(children) ? [] : null
})

function handleScrollView(event: Event) {
  const target = event.target as HTMLElement
  target.scrollIntoView({ behavior: "smooth", block: "center" })
}

const { expandedNamesRef } = useProtocolFormProvide(props, emit)
const enumInfo = computed(() => {
  const { ajv } = props
  if (!ajv?.schema) {
    return null
  }

  // If schema is an array type with items referencing a definition
  if (ajv.schema.type === "array" && ajv.schema.items?.$ref) {
    return getRefValue(ajv.schema, ajv.schema.items.$ref)
  }

  // Handle direct enum cases
  if (Array.isArray(ajv.schema.enum)) {
    return ajv.schema
  }

  // Handle allOf cases
  if (ajv.schema.allOf) {
    return mergeEnumRefValue(ajv.schema, ajv.schema.allOf)
  }

  // Handle direct $ref cases
  if (ajv.schema.$ref) {
    return getRefValue(ajv.schema, ajv.schema.$ref)
  }

  return null
})

const checkColor = computed(() => themeSettings.tokens.light.colors["field-check-bg"])
const stepColor = computed(() => themeSettings.tokens.light.colors["field-step-bg"])
</script>

<style lang="sass">
.triangle-right
  position: relative
  &::before
    content: ''
    position: absolute
    top: 5px
    left: -10px
    width: 0
    height: 0
    border-left: 5px solid var(--scope-color, #1A79FF)
    border-top: 5px solid transparent
    border-bottom: 5px solid transparent
  &--check
    --scope-color: v-bind('checkColor')
  &--step
    --scope-color: v-bind('stepColor')
</style>

<style lang="sass" scoped>
:deep(.n-descriptions-table)
  table-layout: fixed

:deep(.n-descriptions-table-content)
  text-wrap: wrap

:deep(:not(.descriptions__table) .n-descriptions-table-content)
  width: 50%
  overflow: hidden!important
  padding-right: 6px!important

:deep(.n-tag__content)
  overflow: hidden
.form__item--check
  :deep(.n-form-item-blank)
    flex-direction: row

:deep(.n-input__placeholder)
  white-space: nowrap!important

:deep(:not(.descriptions__table) .n-descriptions-table-row:last-child .n-descriptions-table-content:only-child .n-descriptions-table-content__content)
  display: inline-block!important
</style>
