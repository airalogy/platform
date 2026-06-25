import type { IAnnotationDataItem, IRecordData, IRecordDataKey } from "@airalogy/aimd-core/types"
import type { Ref } from "vue"
import type { IRecordDataItem } from "./types"
import Big from "big.js"
import { cloneDeepWith, get, has, isBoolean, isObject, set } from "lodash-es"

type ProtocolRecordScopeData = Pick<IRecordData, "research_variable" | "research_step" | "research_check">

export function normalizeRecordScopeData(
  value: unknown,
): ProtocolRecordScopeData[keyof ProtocolRecordScopeData] {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as ProtocolRecordScopeData[keyof ProtocolRecordScopeData]
  }

  return {}
}

export function createProtocolRecordData(
  data?: Partial<Record<"var" | "step" | "check", unknown>> | null,
): ProtocolRecordScopeData {
  return {
    research_variable: normalizeRecordScopeData(data?.var),
    research_step: normalizeRecordScopeData(data?.step),
    research_check: normalizeRecordScopeData(data?.check),
  }
}

/**
 * Converts different value types to their appropriate format
 */
export function processFieldValue(value: any): any {
  // Handle undefined value
  if (typeof value === "undefined") {
    return null
  }

  // Handle Big.js numbers and other number types
  if (isObject(value)) {
    const { type, value: rawValue } = value as { type: string, value: any }

    if (type === "number" || type === "integer" || type === "float") {
      if (rawValue instanceof Big) {
        return rawValue.toNumber()
      }
      return rawValue
    }

    // Handle file/image objects
    if (type === "image" || type === "file" || (value as any)?.airalogy_file_id) {
      const { airalogy_file_id } = value as any
      const filename = (value as any).filename || (value as any).name
      return { airalogy_file_id, filename }
    }

    // Handle objects with value property
    if ("value" in value) {
      return value.value
    }
  }

  // Return the original value if no transformation needed
  return value
}

/**
 * Determines target path for different field types
 */
export function getFieldTargetPath(
  scope: IRecordDataKey,
  prop: string,
  info?: any,
): string[] {
  if (scope === "var_table" && info?.group) {
    const { row } = info
    const [groupName, varName] = prop.split(".")
    return [scope, groupName, row, varName].filter(Boolean)
  }

  return [scope, prop]
}

/**
 * Creates the appropriate value structure based on scope and value type
 */
export function createFieldValueStructure(
  scope: IRecordDataKey,
  value: any,
): any {
  if (scope === "research_step") {
    if (isBoolean(value)) {
      return { annotation: "", checked: value }
    }
    else if (isObject(value)) {
      return value
    }
    else {
      return { annotation: String(value), checked: null }
    }
  }
  else if (scope === "research_check") {
    if (isBoolean(value)) {
      return { annotation: "", checked: value }
    }
    else if (isObject(value)) {
      return value
    }
    else {
      return { annotation: String(value), checked: null }
    }
  }

  return value
}

/**
 * Handles updating a field in the record data
 */
export function assignFieldValue(
  recordData: Ref<Partial<IRecordData>>,
  scope: IRecordDataKey,
  prop: string,
  value: any,
  info?: any,
): void {
  const targetScope = scope === "var_table"
    ? "research_variable"
    : scope

  // Initialize scope if it doesn't exist
  if (!recordData.value[targetScope]) {
    recordData.value[targetScope] = {}
  }

  const scopeData = recordData.value[targetScope]

  if (!scopeData) {
    // Initialize with structured value
    const structuredValue = createFieldValueStructure(scope, value)
    recordData.value[targetScope] = { [prop]: structuredValue }
    return
  }

  // Handle var_table scope (complex tables with rows)
  if (scope === "var_table") {
    const { group, row } = info || {}

    // Handle group.row.property path
    if (group) {
      const processedValue = processFieldValue(value)
      if (!scopeData[group]) {
        scopeData[group] = []
      }

      const targetRow = get(scopeData, [group, row])
      if (!targetRow) {
        set(scopeData, [group, row], {})
      }

      const [, varName] = prop.split(".")
      set(scopeData, [group, row, varName], processedValue)
      return
    }

    // Handle array values
    if (Array.isArray(value)) {
      scopeData[prop] = value.map((item) => {
        const entries = Object.entries(item)
        return Object.fromEntries(
          entries.map(([key, val]) => {
            const processedVal = processFieldValue(val)
            return [key, processedVal]
          }),
        ) as IRecordDataItem
      })
      return
    }
  }

  // Handle research_step scope
  if (scope === "research_step") {
    if (scopeData[prop]) {
      const target = scopeData[prop] as IAnnotationDataItem
      if (isBoolean(value)) {
        target.checked = value
      }
      else if (isObject(value)) {
        scopeData[prop] = value as IAnnotationDataItem
      }
      else {
        target.annotation = value
      }
    }
    else {
      scopeData[prop] = createFieldValueStructure(scope, value)
    }
    return
  }

  // Handle research_check scope
  if (scope === "research_check") {
    if (scopeData[prop]) {
      const target = scopeData[prop] as IAnnotationDataItem
      if (isBoolean(value)) {
        target.checked = value
      }
      else if (isObject(value)) {
        scopeData[prop] = value as IAnnotationDataItem
      }
      else {
        target.annotation = value
      }
    }
    else {
      scopeData[prop] = createFieldValueStructure(scope, value)
    }
    return
  }

  // Handle standard fields
  const processedValue = processFieldValue(value)
  scopeData[prop] = processedValue
}
/**
 * Extracts asset IDs from record data for API submission
 */
export function extractAssetId<T = any>(payload: T): T | undefined {
  if (!payload)
    return undefined

  const customizer = (value: any) => {
    if (isObject(value)) {
      if (has(value, "airalogy_file_id")) {
        return (value as any).airalogy_file_id as string
      }
    }
    return undefined
  }

  return cloneDeepWith(payload, customizer) as T | undefined
}
