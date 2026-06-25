import type { IAIMDWrapperProps } from "@/components/custom/aimd/types/aimd-types"
import type { FieldKey, IRecordData, ScopeFieldKey } from "@airalogy/aimd-core/types"
import type { ProtocolInfo } from "@airalogy/shared/types/models/protocol.js"
import type { MaybeRefOrGetter, Ref } from "vue"
import type { ExtractResult, FieldRecord } from "../helpers/parseFieldStructure"
import type { IFieldItem } from "../types/types"
import { useBoolean } from "@/composables"
import { useAuthStore } from "@/store/modules/auth"
import { useProtocolWorkflowStore } from "@/store/modules/workflow"
import { useRouteQuery } from "@vueuse/router"
import Big from "big.js"
import { cloneDeepWith, merge } from "lodash-es"
import { nanoid } from "nanoid"
import { computed, reactive, ref, watch } from "vue"
import { getFieldStructure } from "../helpers/parseFieldStructure"

type FieldPropKey = keyof IFieldItem | [keyof IFieldItem, string[]]

export function useFieldState(
  props: MaybeRefOrGetter<{
    protocol: ProtocolInfo | null | undefined
    protocolId: string | number
    recordData?: Partial<IRecordData>
    readonly?: boolean
  }>,
  templateRef: Ref<string>,
) {
  const workflowId = useRouteQuery("workflow", nanoid())
  const workflowField = ref<{ id: string, title: string, field: FieldRecord } | null>(null)
  const workflowStore = useProtocolWorkflowStore()
  const workflowInfo = computed(() =>
    workflowId.value ? workflowStore.getWorkflow(workflowId.value) : null,
  )
  const route = useRoute()
  const authStore = useAuthStore()
  const fieldModel = reactive<FieldRecord>({})

  const workflowInitialValues = computed(() => {
    if (!workflowInfo.value?.model)
      return null

    return workflowInfo.value.model.record[route.query.target as string]?.initialValue
  })

  // Field Model
  const fieldRecordDefault = shallowRef<ExtractResult | null>(null)

  const restoreFieldRecord = (currRecordData?: Partial<IRecordData>) => {
    const { protocol, recordData, readonly } = toValue(props)
    fieldRecordDefault.value = getFieldStructure({
      markdown: templateRef.value,
      protocol,
      workflowField,
      userInfo: authStore.userInfo,
      recordData: currRecordData || recordData,
      isReadonly: readonly,
    })
  }

  onMounted(() => restoreFieldRecord())

  watch(fieldRecordDefault, (val) => {
    if (!val?.field)
      return

    merge(fieldModel, cloneDeepWith(val.field, (val) => {
      if (val instanceof Big) {
        return new Big(val)
      }

      return undefined
    }))
  })

  // Mounted State
  const { bool: domMounted, setTrue: setDomMounted, setFalse: setDomUnMounted } = useBoolean()

  // Field Lists
  const fieldPropList = ref<FieldPropKey[][]>([])
  const scopeList = computed(() => {
    if (!fieldRecordDefault.value) {
      return []
    }

    const { field } = fieldRecordDefault.value
    return Object.entries(field).reduce((acc, [key, value]) => {
      if (Object.keys(value).length > 1) {
        acc.push(key as FieldKey)
      }
      return acc
    }, [] as ScopeFieldKey[])
  })

  // Scope Record
  const varScopeRecord = computed(() => {
    const { fields } = toValue(props).protocol || {}
    if (!fields)
      return {}

    return (Object.entries(fields) as unknown as [FieldKey, IFieldItem[]][]).reduce(
      (acc, [k, v]) => {
        if (Array.isArray(v)) {
          v.forEach((it) => {
            if (it.name)
              acc[it.name] = k
          })
        }
        return acc
      },
      {} as Record<string, ScopeFieldKey>,
    )
  })

  // Records
  const refRecord = ref<Record<"ref_step" | "rv_ref", Record<string, any>>>({
    ref_step: {},
    rv_ref: {},
  })

  const tableRecord = ref< IAIMDWrapperProps["tableRecord"] >({})

  const tableEmitterRecord = ref<
    Record<"master" | "slave", Record<string, ((...args: any[]) => void)[]>>
  >({
        master: {},
        slave: {},
      })

  // Expanded Names
  const expandedNamesRef = ref<string[]>([...scopeList.value])

  // Focus Management
  const prevFocusedField = ref<HTMLElement | null>(null)
  const focusedField = ref<HTMLElement | null>(null)

  watch(
    () => focusedField.value,
    (val) => {
      if (prevFocusedField.value)
        prevFocusedField.value.classList.remove("aimd-field--focus")
      if (val)
        val.classList.add("aimd-field--focus")
    },
  )

  watch(scopeList, (list) => {
    if (!fieldRecordDefault.value) {
      return
    }

    const { field } = fieldRecordDefault.value

    if (list.length !== fieldPropList.value.length) {
      fieldPropList.value = list.map((scope) => {
        const entries = field[scope]
          ? Object.entries(field[scope] || {}).filter(([key, value]) => {
            if (key === "__SCOPE__") {
              return false
            }

            const { originalName } = value
            if (originalName) {
              return false
            }

            return true
          })
          : []

        return entries.map(([key]) => key as FieldPropKey)
      },
      )
    }

    expandedNamesRef.value = [...list]
  })

  watch(workflowId, (currId, prevId) => {
    workflowStore.moveWorkflow(prevId, currId)
  })
  return {
    // Models
    fieldModel,
    fieldRecordDefault,

    // Lists
    fieldPropList,
    scopeList,

    // Records
    refRecord,
    tableRecord,
    tableEmitterRecord,
    varScopeRecord,

    // Expanded Names
    expandedNamesRef,

    // Focus Management
    prevFocusedField,
    focusedField,

    // Mounted State
    domMounted,
    setDomMounted,
    setDomUnMounted,

    // Workflow Field
    workflowField,
    workflowId,

    // Restore Field Record
    restoreFieldRecord,
  }
}
