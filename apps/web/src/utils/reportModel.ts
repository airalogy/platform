import type { IRecordDataKey } from "@airalogy/aimd-core/types"
import Big from "big.js"

export function isFileType(val: any): val is { airalogy_file_id: string, type?: string } {
  return val && typeof val === "object" && (
    val.airalogy_file_id
    || val.type === "image"
    || val.type === "file"
  )
}

export function isNumericType(val: any): val is { type: "number" | "float" | "integer", value: any } {
  return val && typeof val === "object" && (
    val.type === "number"
    || val.type === "float"
    || val.type === "integer"
  )
}

export function processNumericValue(val: any): number | undefined {
  if (typeof val === "undefined" || val === null) {
    return undefined
  }
  return val instanceof Big ? val.toNumber() : val
}

export function processValue(val: any): any {
  if (val instanceof Big) {
    return val.toNumber()
  }

  if (isFileType(val)) {
    return val.airalogy_file_id
  }

  if (isNumericType(val)) {
    return processNumericValue(val.value)
  }

  if (val && typeof val === "object" && "value" in val) {
    return val.value
  }

  return val
}

export function handleDependencyVal(payload: {
  fieldName: string
  targetScope: IRecordDataKey
  targetVal: any
  dependencies: [string, any][]
  invalidMessages: { scope: IRecordDataKey, field: string, message: string[] }[]
  onInvalid: () => void
  isRow?: boolean
}) {
  const { fieldName, targetScope, targetVal, dependencies, invalidMessages, onInvalid, isRow } = payload

  if (targetScope === "research_check" || targetScope === "research_step") {
    dependencies.push([fieldName, Boolean(targetVal)])
    return
  }

  const invalidMessage = { scope: targetScope, field: fieldName, message: ["Value is required"] }
  if (typeof targetVal === "undefined" || targetVal === null) {
    invalidMessages.push(invalidMessage)
    onInvalid()
    return
  }

  if (Array.isArray(targetVal)) {
    if (isRow) {
      const processedRow = targetVal.map((row) => {
        return Object.fromEntries(Object.entries(row).map(([key, val]) => [key, processValue(val)]))
      })
      dependencies.push([fieldName, processedRow])
    }
    else {
      dependencies.push([fieldName, targetVal])
    }
  }
  else {
    const processedValue = processValue(targetVal)
    if (processedValue === undefined) {
      invalidMessages.push(invalidMessage)
      onInvalid()
    }
    else {
      dependencies.push([fieldName, processedValue])
    }
  }
}
