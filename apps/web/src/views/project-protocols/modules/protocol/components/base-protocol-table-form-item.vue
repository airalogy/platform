<template>
  <n-form-item
    :ref="(el: any) => handleFormItemRef(`${scope}_${prop}`, el)"
    :path="`${scope}.${prop}.value`"
    label-placement="top"
    class="w-full pl-4 text-start"
    :show-require-mark="false"
    :show-feedback="Boolean(tableAssignerError)"
    :feedback="tableAssignerError"
    :validation-status="tableAssignerError ? 'error' : undefined"
  >
    <template #label>
      <n-collapse-item :name="`${scope}-${prop}`" class="triangle-right triangle-right--table !mb-3 !ml-3">
        <template #header>
          <n-ellipsis v-if="Boolean(model.title || model.label)" class="mr-auto text-4 font-500 capitalize">
            <span> {{ model.title || model.label }} </span>
            <span v-if="model.required" class="n-form-item-label__asterisk mr-auto flex-1">
              &nbsp;*
            </span>
          </n-ellipsis>
        </template>

        <div v-if="Boolean(model.label)" class="mb-4 w-full flex items-center px-1">
          <div class="w-1/2">
            <span class="mr-2">{{ $t("common.field") }}:</span>
            <n-tag>
              <n-ellipsis class="text-3 font-normal">
                {{ model.label }}
              </n-ellipsis>
            </n-tag>
          </div>
          <div class="w-1/2">
            <span class="mr-2">{{ $t("common.type") }}:</span>
            <n-tag>
              <n-ellipsis class="text-3 font-normal">
                {{ model.type }}
              </n-ellipsis>
            </n-tag>
          </div>
        </div>
        <n-descriptions v-if="subvarNames.length > 0" bordered :column="1" class="descriptions__table">
          <template v-for="(rvName, idx) in subvarNames" :key="rvName">
            <n-descriptions-item v-if="tableRecord[prop]?.[rvName]" :span="1">
              <template #label>
                <span> {{ idx + 1 }}: </span>
                <span>
                  {{ tableRecord[prop][rvName].title || rvName }}
                </span>
              </template>
              <n-descriptions
                label-placement="left" :column="2" :bordered="false" class="!b-0"
                label-class="capitalize !align-middle" content-class="!b-0 !align-middle"
              >
                <n-descriptions-item :label="$t('common.field')" :span="1">
                  <n-tag class="h-fit w-full whitespace-pre-wrap break-all py-2 text-3">
                    {{ rvName }}
                  </n-tag>
                </n-descriptions-item>
                <template v-for="(property, propertyName) in tableRecord[prop][rvName]" :key="propertyName">
                  <n-descriptions-item
                    v-if="!['sequence', 'title', 'assigner'].includes(propertyName)"
                    :label="propertyName" :span="Array.isArray(property) ? 2 : 1" :bordered="false"
                    content-class="!b-0"
                    :label-style="Array.isArray(property) ? 'vertical-align: top!important' : ''"
                    :content-style="Array.isArray(property) ? 'vertical-align: top!important' : ''"
                  >
                    <template v-if="Array.isArray(property)">
                      <ul class="ml-5 list-decimal">
                        <li v-for="(propertyItem, propertyIndex) in property" :key="propertyIndex" class="mb-4">
                          <n-tag v-if="typeof propertyItem === 'string'">
                            {{ propertyItem }}
                          </n-tag>
                          <div v-else>
                            <span class="mr-4 inline-block">{{ $t("common.type") }}:</span>
                            <n-tag :type="typeMap[propertyItem.type]">
                              {{ propertyItem.type }}
                            </n-tag>
                          </div>
                          <div v-if="propertyItem.format" class="mt-2 max-w-20">
                            <span class="mr-4 inline-block">{{ $t("common.format") }}:</span>
                            <n-tag>
                              <n-ellipsis>
                                {{ propertyItem.format }}
                              </n-ellipsis>
                            </n-tag>
                          </div>
                        </li>
                      </ul>
                    </template>
                    <n-tag
                      v-else-if="typeof property === 'string' || typeof property === 'number'"
                      :type="typeMap[property]"
                      class="h-fit w-full whitespace-pre-wrap break-all py-2 text-3"
                    >
                      {{ property }}
                    </n-tag>
                  </n-descriptions-item>
                </template>
                <n-descriptions-item
                  v-if="tableRecord?.[prop]?.[rvName]?.assigner" :label="$t('common.assigner')" :span="2" :bordered="false"
                  content-class="!b-0"
                >
                  <div>
                    <span>{{ $t("common.assignerMode") }}: </span>
                    <n-tag size="small">
                      {{ tableRecord[prop][rvName].assigner!.mode }}
                    </n-tag>
                  </div>
                  <assigner-dependencies
                    :fields="tableRecord[prop][rvName].assigner!.dependent_fields"
                    :is-table-form="true"
                    source="form"
                  />
                </n-descriptions-item>
              </n-descriptions>
            </n-descriptions-item>
          </template>
        </n-descriptions>
      </n-collapse-item>
    </template>
    <template v-if="Array.isArray(model.value)" #default>
      <n-collapse display-directive="show">
        <n-collapse-item v-for="(row, rowIdx) in model.value" :key="rowIdx" :title="$t('common.rowIndex', { index: rowIdx + 1 })" class="!ml-0">
          <n-descriptions v-if="subvarNames.length > 0" bordered label-class="break-all" class="table-row-descriptions">
            <n-descriptions-item v-for="(key, colIdx) in subvarNames" :key="key" :label="key">
              <!-- Wrap each cell in n-form-item for cell-level validation -->
              <n-form-item
                :ref="(el: any) => handleCellFormItemRef(`${scope}_${prop}_${rowIdx}_${key}`, el)"
                :path="`${scope}.${prop}.value[${rowIdx}].${key}`"
                :show-label="false"
                :show-feedback="true"
                :feedback="getCellAssignerError(key, rowIdx)"
                :validation-status="getCellAssignerError(key, rowIdx) ? 'error' : undefined"
                :rule="getCellRules(key, rowIdx)"
                class="cell-form-item"
              >
                <form-item-input v-bind="getInputProps({ prop, key, rowIdx, colIdx, model, row })" />
              </n-form-item>
            </n-descriptions-item>
          </n-descriptions>
        </n-collapse-item>
      </n-collapse>
      <n-button
        v-if="!isReadonly && (!model?.link || model?.link?.isSource)" type="primary" class="mr-auto mt-4" @click="
          handleAddVarTableRow({
            name: model.raw!.name,
            subvars: model.raw!.subvars || [],
            link: model.link,
            assigner: model.raw?.assigner,
          })
        "
      >
        <template #icon>
          <icon-local-add-circle />
        </template>
        {{ $t("common.addRow") }}
      </n-button>
    </template>
  </n-form-item>
</template>

<script setup lang="ts">
import type { IRecordDataKey } from "@airalogy/aimd-core/types"
import type { ProtocolModels } from "@airalogy/shared/types"
import type { FormItemInst, FormItemRule } from "naive-ui"
import type { IFieldItem } from "../types/types"
import AssignerDependencies from "@/components/custom/aimd/components/assigner-dependencies.vue"
import { fieldEventKey } from "@/utils/template/eventKey"
import { getSubvarNames } from "@airalogy/aimd-core"
import { get } from "lodash-es"
import { useProtocolFormInject } from "../composables/useProtocolForm"
import FormItemInput from "./form-item-input.vue"

interface Props {
  model: IFieldItem
  scope: IRecordDataKey
  prop: string
  ajvInfo?: any
  enumInfo?: any
  inputId: string
  assigner?: ProtocolModels.Assigner
  dependent?: { name: string, scope: IRecordDataKey }[]
  dependentRecord?: Record<string, { name: string, scope: IRecordDataKey }[]>
  assignerRecord?: Record<string, ProtocolModels.Assigner>
  id: string
  // Cell validation rules from parseFieldStructure
  cellRules?: Record<string, {
    pattern?: string
    type?: string
    required?: boolean
    validator?: (value: any, rowIndex: number) => { valid: boolean, message: string }
  }>
}

const props = defineProps<Props>()

function mergeDependents(
  ...lists: Array<Array<{ name: string, scope: IRecordDataKey }> | undefined>
): Array<{ name: string, scope: IRecordDataKey }> | undefined {
  const merged = lists
    .flatMap(list => list || [])
    .filter((item): item is { name: string, scope: IRecordDataKey } => Boolean(item?.name && item?.scope))

  if (merged.length === 0) {
    return undefined
  }

  const seen = new Set<string>()
  return merged.filter((item) => {
    const key = `${item.scope}.${item.name}`
    if (seen.has(key)) {
      return false
    }
    seen.add(key)
    return true
  })
}

const {
  createTableCellModel,
  handleAddVarTableRow,
  typeMap,
  handleFormItemRef,
  tableRecord,
  readonly: isReadonly,
  assignerErrorRecord,
} = useProtocolFormInject()!

// Store cell form item refs for validation
const cellFormItemRefs = reactive<Record<string, { value: FormItemInst | null }>>({})

/**
 * Handle cell form item ref registration
 */
function handleCellFormItemRef(path: string, el: FormItemInst | null) {
  if (cellFormItemRefs[path]) {
    cellFormItemRefs[path].value = el
  }
  else {
    cellFormItemRefs[path] = { value: el }
  }
}

/**
 * Get cell-level validation rules for a specific subvar (returns array for n-form-item)
 */
function getCellRules(subvarKey: string, rowIdx: number): FormItemRule[] {
  // Try to get cell rule from props.cellRules
  const cellRuleKey = `${props.scope}.${props.prop}.${subvarKey}`
  const cellRule = props.cellRules?.[cellRuleKey]

  // Also try to get pattern from tableRecord
  const tableSchema = tableRecord.value?.[props.prop]?.[subvarKey] as Record<string, any> | undefined
  const pattern = cellRule?.pattern || tableSchema?.pattern
  const isRequired = cellRule?.required || tableSchema?.required || false

  if (!pattern && !isRequired) {
    return []
  }

  return [{
    required: isRequired,
    trigger: ["blur"],
    validator: (_rule, value) => {
      // Required validation
      if (isRequired && (value === null || value === undefined || value === "")) {
        return new Error(`${subvarKey} is required`)
      }

      // Pattern validation - skip if pattern is empty string or only whitespace
      if (pattern && pattern.trim() && typeof value === "string" && value.trim()) {
        try {
          const regex = new RegExp(pattern)
          const trimmedValue = value.trim()
          if (!regex.test(trimmedValue)) {
            return new Error(`${subvarKey} does not match required pattern`)
          }
        }
        catch (e) {
          console.warn(`Invalid regex pattern for ${subvarKey}:`, pattern, e)
        }
      }

      return true
    },
  }]
}

const fieldEventBus = useEventBus<string>(fieldEventKey)

const tableAssignerError = computed(() => {
  const error = assignerErrorRecord.value[props.prop]
  return typeof error === "string" ? error : undefined
})

// Normalize subvars to string array (handles both string[] and {name: string}[] formats)
const subvarNames = computed(() => getSubvarNames(props.model.raw?.subvars))

// Note: Validation is triggered on blur, not on value change
// This provides a better UX by not showing errors while the user is still typing

function getInputProps(payload: {
  prop: string
  key: string
  rowIdx: number
  colIdx: number
  model: IFieldItem
  row: Record<string, any>
}) {
  const { prop, key, rowIdx, colIdx, model, row } = payload
  const { ajvInfo, enumInfo, inputId, assignerRecord, dependentRecord } = props

  const assigner = assignerRecord?.[`${prop}.${key}`]
  const dependent = mergeDependents(
    dependentRecord?.[`${prop}.${key}`],
    props.dependent,
  )
  const cellEnumInfo = get(enumInfo, ["properties", key, "enum"])

  // Get schema safely - tableRecord may not have all columns defined
  const schema = tableRecord.value?.[prop]?.[key] || { type: "string", title: key }

  return {
    model: createTableCellModel({
      schema,
      value: row[key],
      label: key,
      scope: "var_table",
      title: key,
      info: model,
    }),
    prop: key,
    scope: "var_table",
    ajvInfo,
    inputId,
    enumInfo: cellEnumInfo,
    info: {
      ...model.raw,
      row: rowIdx,
      col: colIdx,
      name: key,
      group: model.raw?.name,
      link: model.link,
    },
    assigner,
    dependent,
    readonly: isReadonly.value,
    disabled: isReadonly.value || assigner?.mode === "auto_force",
    id: `${inputId}-${key}-${rowIdx}-${colIdx}`,
  }
}

function getCellAssignerError(key: string, rowIdx: number) {
  const error = assignerErrorRecord.value[`${props.prop}.${key}[${rowIdx}]`]
  return typeof error === "string" ? error : undefined
}
</script>

<style lang="sass" scoped>
.descriptions__table
  :deep(.n-descriptions-table-wrapper .n-descriptions-table-wrapper),
  :deep(.n-descriptions .n-descriptions-table-content)
    border: 0!important

// Cell-level form item styling
.cell-form-item
  margin-bottom: 0 !important
  :deep(.n-form-item-blank)
    min-height: auto
  :deep(.n-form-item-feedback-wrapper)
    min-height: auto
    padding-top: 2px

  // Error state styling using n-form-item's native error class
  &:deep(.n-form-item-feedback--error)
    color: #d03050

  // Apply red border when n-form-item has error state
  &.n-form-item--error
    :deep(.n-input),
    :deep(.n-input-number),
    :deep(.n-select .n-base-selection)
      --n-border: 1px solid #d03050 !important
      --n-border-hover: 1px solid #d03050 !important
      --n-border-focus: 1px solid #d03050 !important
      border-color: #d03050 !important
      box-shadow: 0 0 0 2px rgba(208, 48, 80, 0.2)

.table-row-descriptions
  :deep(.n-descriptions-table-content)
    table-layout: auto
    width: 100%

  :deep(.n-descriptions-table-content td)
    overflow-wrap: break-word
    word-wrap: break-word
    vertical-align: top
    padding: 8px !important

  // Set minimum width for text cells
  :deep(.n-descriptions-table-content td)
    min-width: 120px

  // Limit width for TD containing file upload
  :deep(.n-descriptions-table-content td:has(.file-input-wrapper))
    max-width: 100px !important
    width: 100px !important
    overflow: hidden

  // Limit width for cells containing file upload
  :deep(.file-input-wrapper)
    max-width: 100px !important
    width: 100px !important
    display: block
    overflow: hidden

  :deep(.table-file-upload)
    max-width: 100px !important
    width: 100px !important
    display: block

  :deep(.n-upload)
    max-width: 100px !important
    width: 100px !important

  :deep(.n-upload-file-list)
    max-width: 100px !important
    width: 100px !important

  :deep(.n-upload-file-list--grid)
    max-width: 100px !important
    width: 100px !important

  :deep(.n-upload-file)
    max-width: 100px !important
    width: 100px !important

  :deep(.n-upload-trigger)
    max-width: 100px !important

  :deep(.n-upload-file--image-card-type)
    max-width: 100px !important
    width: 100px !important
    min-width: 90px !important

  :deep(.n-upload-file-info)
    max-width: 100px !important

  :deep(.n-upload-file-info__thumbnail)
    max-width: 90px !important

  // Ensure upload buttons fit in small container
  :deep(.file-input-wrapper .n-button)
    max-width: 100px !important
    font-size: 12px
    padding: 0 6px
    height: 30px
    white-space: nowrap
    overflow: hidden
    text-overflow: ellipsis
</style>
