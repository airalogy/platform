<template>
  <slot v-bind="{ ...toReactive(context) }" />
</template>

<script setup lang="ts">
import type { IAIMDWrapperProps } from "@/components/custom/aimd/types/aimd-types"
import type { ExtractResult } from "@/views/project-protocols/modules/protocol/helpers/parseFieldStructure"
import type { ScopeFieldKey } from "@airalogy/aimd-core/types"
import type { ProtocolInfo } from "@airalogy/shared/types/models/protocol"
import { useAIMDProvide } from "@/components/custom/aimd/composables/useAIMDHelpers"
import { useFieldParser } from "@/views/project-protocols/modules/protocol/composables/useFieldParser"
import { toReactive } from "@vueuse/core"
import Big from "big.js"
import { cloneDeepWith as _cloneDeepWith } from "lodash-es"
import { computed, toRaw, watchEffect } from "vue"

interface Props {
  protocolId?: string
  protocol?: ProtocolInfo | null
  readonly?: boolean
  recordData?: ExtractResult | null
  minimal?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  protocolId: "timeline-display",
  readonly: true,
  minimal: true,
})

const emit = defineEmits<{
  "update:value": [val: string]
  "add-row:table": [payload: any]
  "remove-row:table": [payload: any]
  "click:field": [event: MouseEvent]
}>()

// Extract table information from research_variable fields
const tableRecord = ref<Record<string, Record<string, any>>>({})
const refRecord = ref({ ref_step: {}, rv_ref: {} })
const scopeList = computed(() => Object.keys(props.recordData?.field || {}) as ScopeFieldKey[])
const propList = computed(() =>
  scopeList.value.map(scope =>
    Object.keys(props.recordData?.field?.[scope] || {}).filter(prop => prop !== "__SCOPE__"),
  ),
)

// Provide aimd context with configurable props
const aimdProps = computed(() => {
  const record = props.recordData || {
    field: {},
    rules: {},
  } as ExtractResult

  return {
    assignerErrorRecord: {},
    assignerLoadingRecord: {},
    assignerRequestRecord: {},
    readonly: props.readonly,
    protocolId: props.protocolId,
    record,
    typed: {},
    scopeList: scopeList.value as ScopeFieldKey[],
    propList: propList.value,
    refRecord: refRecord.value,
    tableRecord: tableRecord.value,
    varScopeRecord: {},
  } as IAIMDWrapperProps
})

// Provide the context and destructure returned values
const context = useAIMDProvide(toReactive(aimdProps), emit, props.minimal)
const { fieldModel, restoreTableVariableRecord } = context

const { parseVarTable } = useFieldParser(fieldModel as any, toRef(props, "protocol"), scopeList, propList, refRecord, tableRecord, ref({} as any), false)

// Populate fieldModel with data from recordData
watchEffect(() => {
  const { recordData } = props
  if (!recordData || !recordData.field) {
    return
  }

  const { field } = recordData
  const recordScopes = Object.keys(field) as ScopeFieldKey[]

  recordScopes.forEach((scopeName) => {
    const scopeData = field[scopeName]
    if (!scopeData)
      return

    const propList = Object.keys(scopeData).filter(prop => prop !== "__SCOPE__")

    propList.forEach((prop) => {
      const item = scopeData[prop]
      if (!item) {
        return
      }

      let val: any = _cloneDeepWith(toRaw(item.value), (objVal) => {
        if (objVal instanceof Big) {
          return new Big(objVal)
        }
        return undefined
      })

      if (!val && (scopeName === "research_check" || scopeName === "research_step")) {
        val = {
          annotation: "",
          checked: null,
        }
      }

      if (fieldModel[scopeName]) {
        fieldModel[scopeName][prop] = { value: val }
      }
      else {
        fieldModel[scopeName] = { [prop]: { value: val } }
      }
    })
  })
})

// Initialize tableVariableRecord after fieldModel is populated
watchEffect(() => {
  const { recordData } = props
  if (!recordData || !recordData.field || !fieldModel.research_variable) {
    return
  }

  const researchVariableFields = Object.entries(recordData.field.research_variable || {}).map(([fieldName, fieldInfo]) => {
    if (fieldInfo.type === "table" && fieldInfo.raw?.type === "table" && fieldInfo.raw?.subvars) {
      return [fieldName, fieldInfo]
    }
    return null
  }).filter(Boolean) as [string, any][]

  parseVarTable(researchVariableFields, recordData.field.research_variable)
  restoreTableVariableRecord()
})

defineExpose({
  context,
})
</script>
