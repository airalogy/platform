import type { ScopeFieldKey } from "@airalogy/aimd-core/types"
import { isUploadFileType, scopeKeyRecord } from "@airalogy/shared/utils"
import { isObject } from "lodash-es"

/**
 * Unified field type detection for both display and input purposes
 * Used across timeline-data-cell, aimd-item, and timeline-aimd-input
 */
export function getUnifiedFieldType(value: any, schemaInfo?: { type?: string, scope?: string }): {
  displayType: string // For human-readable display (e.g., "Boolean", "Text", "File")
  aimdType: string // For aimd input component type selection (e.g., "boolean", "text", "file")
  cssClass: string // For field tag CSS class (e.g., "check", "var", "file")
} {
  // If we have schema information from protocol matching, use it first
  if (schemaInfo?.type) {
    const schemaType = schemaInfo.type

    // Handle boolean types
    if (schemaType === "boolean" || schemaType === "rs-check" || schemaType === "rc-check") {
      return {
        displayType: "Boolean",
        aimdType: "boolean",
        cssClass: "check",
      }
    }

    // Handle annotation types
    if (schemaType === "rs-annotation" || schemaType === "rc-annotation") {
      return {
        displayType: "Check",
        aimdType: "rs-annotation",
        cssClass: "check",
      }
    }

    // Handle step types
    if (schemaType === "step" || schemaType === "research_step") {
      return {
        displayType: "Step",
        aimdType: "step",
        cssClass: "step",
      }
    }

    // Handle variable types
    if (schemaType === "var" || schemaType === "research_variable") {
      return {
        displayType: "Variable",
        aimdType: "text",
        cssClass: "var",
      }
    }

    // Handle file types - use shared utility
    if (isUploadFileType(schemaType)) {
      return {
        displayType: "File",
        aimdType: schemaType,
        cssClass: "file",
      }
    }

    // Handle table types
    if (schemaType === "var_table" || schemaType === "rv_table") {
      return {
        displayType: "Table",
        aimdType: "array",
        cssClass: "var_table",
      }
    }
  }

  // If we have scope information, use it
  if (schemaInfo?.scope) {
    const scope = schemaInfo.scope as ScopeFieldKey
    const scopeType = scopeKeyRecord[scope]

    if (scopeType) {
      return {
        displayType: getScopeDisplayName(scopeType),
        aimdType: getScopeAIMDType(scopeType),
        cssClass: scopeType,
      }
    }
  }

  // Fall back to value-based type detection
  return getValueBasedFieldType(value)
}

/**
 * Get field type based on the actual value structure
 */
function getValueBasedFieldType(value: any): {
  displayType: string
  aimdType: string
  cssClass: string
} {
  // Handle arrays
  if (Array.isArray(value)) {
    return {
      displayType: "Array",
      aimdType: "array",
      cssClass: "var_table",
    }
  }

  // Handle primitives
  if (typeof value === "boolean") {
    return {
      displayType: "Boolean",
      aimdType: "boolean",
      cssClass: "check",
    }
  }

  if (typeof value === "number") {
    return {
      displayType: "Number",
      aimdType: "number",
      cssClass: "var",
    }
  }

  if (typeof value === "string") {
    return {
      displayType: "Text",
      aimdType: "text",
      cssClass: "var",
    }
  }

  // Handle objects with specific structures
  if (isObject(value)) {
    // File objects
    if ("filename" in value && "id" in value) {
      return {
        displayType: "File",
        aimdType: "file",
        cssClass: "file",
      }
    }

    if ("airalogy_file_id" in value) {
      return {
        displayType: "File",
        aimdType: "file",
        cssClass: "file",
      }
    }

    // Check/annotation objects
    if ("annotation" in value || "checked" in value) {
      return {
        displayType: "Check",
        aimdType: "rs-check",
        cssClass: "check",
      }
    }

    // Assigner objects
    if ("mode" in value && "dependent_fields" in value) {
      return {
        displayType: "Assigner",
        aimdType: "assigner",
        cssClass: "step",
      }
    }

    // Variable objects with scope
    if ("scope" in value && "value" in value) {
      return {
        displayType: "Variable",
        aimdType: "variable",
        cssClass: "var",
      }
    }
  }

  // Default fallback
  return {
    displayType: "Object",
    aimdType: "text",
    cssClass: "var",
  }
}

/**
 * Convert scope key to display name
 */
function getScopeDisplayName(scopeType: string): string {
  const displayMap: Record<string, string> = {
    step: "Step",
    check: "Check",
    var: "Variable",
    file: "File",
    var_table: "Table",
    rp: "Protocol",
    rr: "Result",
    rrec: "Record",
    rq: "Question",
    rnw: "Workflow",
    rn: "Node",
    ref_step: "Label",
    rv_ref: "Reference",
    step_ref: "Step Reference",
  }

  return displayMap[scopeType] || "Field"
}

/**
 * Convert scope key to aimd input type
 */
function getScopeAIMDType(scopeType: string): string {
  const typeMap: Record<string, string> = {
    step: "rs-check",
    check: "rs-check",
    var: "text",
    file: "file",
    var_table: "array",
    rp: "text",
    rr: "text",
    rrec: "text",
    rq: "text",
    rnw: "text",
    rn: "text",
    ref_step: "text",
    rv_ref: "text",
    step_ref: "text",
  }

  return typeMap[scopeType] || "text"
}

/**
 * Check if a value should be rendered as an asset
 */
export function shouldRenderAsAsset(value: any): boolean {
  return !!(
    (value?.file_extension && value?.value)
    || (value?.file_extension && value?.id)
    || value?.airalogy_file_id
  )
}

/**
 * Check if a value is array data
 */
export function isArrayData(value: any): boolean {
  return Array.isArray(value?.value || value)
}
