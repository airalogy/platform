import type { JsonSchema } from "@/components/custom/aimd/types/aimd-types"
import type { FieldKey, IFileDataItem, IRecordData, IRecordDataItem, IRecordDataKey, ScopeFieldKey } from "@airalogy/aimd-core/types"
import type { FieldItem, ProtocolInfo } from "@airalogy/shared/types/models/protocol"
import type { JSONSchemaType } from "ajv"
import type { FormItemRule } from "naive-ui"
import type { Ref } from "vue"
import type { IFieldItem as IExtendedFieldItem } from "../types/types"
import { getInputType } from "@/components/custom/aimd/composables/useAIMDHelpers"
import { ajv } from "@/utils/ajv"
import { DYNAMIC_TABLE_LINK, DYNAMIC_TABLE_SUB_VAR, ESCAPED_PROTOCOL_FIELDS } from "@airalogy/shared/constants"
import { BuiltInType } from "@airalogy/shared/enum/airalogy.js"
import { fileTypes, getFileType, getRefValue, type IAiralogyIdFileItem, parseAiralogyId } from "@airalogy/shared/utils"
import { scopeKeyRecord, scopeNameRecord } from "@airalogy/shared/utils/schema"
import Big from "big.js"
import dayjs from "dayjs"

// Local type definitions using extended field item
type ExtendedFieldRecord = {
  [k in string]: IExtendedFieldItem
}

export interface ExtendedExtractResult {
  field: Partial<Record<ScopeFieldKey, ExtendedFieldRecord>>
  rules: Partial<Record<FieldKey, Partial<Record<string, { ajv: import("ajv").ValidateFunction | null, value: FormItemRule }>>>>
}

export type ExtractResult = ExtendedExtractResult
export type FieldRecord = ExtendedFieldRecord

/**
 * Parse a single subvar definition like "var(partner_email: str, pattern=r\"...\")"
 * Returns an object with name and optional pattern, type, etc.
 */
function parseSubvarDefinition(subvarStr: string): { name: string, type?: string, pattern?: string, kwargs?: Record<string, any> } {
  let trimmed = subvarStr.trim()

  // Handle var(...) wrapper
  if (trimmed.startsWith("var(") && trimmed.endsWith(")")) {
    trimmed = trimmed.slice(4, -1).trim()
  }

  // Parse key=value parameters (including pattern=r"...")
  const kwargs: Record<string, any> = {}
  // Match pattern=r"...", pattern="...", key="value", etc.
  const kvPattern = /(\w+)\s*=\s*(?:r?"([^"]*)"|r?'([^']*)'|(\S+?)(?=,|$|\s))/g
  let match = kvPattern.exec(trimmed)
  while (match) {
    const key = match[1]
    let value = match[2] ?? match[3] ?? match[4]
    // Handle r"..." raw strings
    if (match[4] && match[4].startsWith("r\"")) {
      value = match[4].slice(2, -1)
    }
    else if (match[4] && match[4].startsWith("r'")) {
      value = match[4].slice(2, -1)
    }
    if (key !== "name" && key !== "type") { // Avoid overwriting main fields
      kwargs[key] = value
    }
    match = kvPattern.exec(trimmed)
  }

  // Parse main part (name: type or just name)
  const mainPart = trimmed.split(/,\s*(?=\w+\s*=)/)[0].trim()
  let name: string
  let type: string | undefined

  if (mainPart.includes(":")) {
    const colonIdx = mainPart.indexOf(":")
    name = mainPart.slice(0, colonIdx).trim()
    type = mainPart.slice(colonIdx + 1).trim().split(/\s/)[0]
  }
  else {
    name = mainPart.split(/\s/)[0].trim()
  }

  const result: { name: string, type?: string, pattern?: string, kwargs?: Record<string, any> } = { name }
  if (type)
    result.type = type
  if (kwargs.pattern) {
    result.pattern = fixPatternEscapes(kwargs.pattern)
  }
  if (Object.keys(kwargs).length > 0)
    result.kwargs = kwargs

  return result
}

/**
 * Fix pattern escape sequences that may have been corrupted during string processing.
 *
 * Problem: In markdown templates, users write \\s to mean \s (regex whitespace).
 * But during processing (markdown parsing, JSON parsing, etc.), \\s might become \s,
 * and in JavaScript strings, \s is interpreted as just 's' (invalid escape = char).
 *
 * This corrupts regex patterns:
 * - [^@\s] (exclude @ and whitespace) becomes [^@s] (exclude @ and letter 's')
 * - \. (literal dot) becomes . (any character)
 *
 * Solution: Detect and fix specific patterns that are clearly corrupted.
 * We only fix patterns that look like common email/string regex patterns.
 */
function fixPatternEscapes(pattern: string): string {
  // The pattern comes from Python raw string r"..." where \ is literal
  // In Python: r"\s" is two characters: backslash + s
  // In JavaScript RegExp: we need \s to be one escape sequence
  // So we need to convert double-backslash to single-backslash for regex escapes
  return pattern
    .replace(/\\\\s/g, "\\s")
    .replace(/\\\\d/g, "\\d")
    .replace(/\\\\w/g, "\\w")
    .replace(/\\\\S/g, "\\S")
    .replace(/\\\\D/g, "\\D")
    .replace(/\\\\W/g, "\\W")
    .replace(/\\\\\./g, "\\.")
    .replace(/\\\\t/g, "\\t")
    .replace(/\\\\n/g, "\\n")
    .replace(/\\\\r/g, "\\r")
}

function getTargetScope(
  varName: string,
  entries: [string, any][],
): ScopeFieldKey | undefined {
  const scope = entries.find(([_, v]) => {
    if (Array.isArray(v)) {
      return v.findIndex(it => it.name === varName) !== -1
    }
    return Object.keys(v).includes(varName)
  })

  return scope?.[0] as ScopeFieldKey
}
/**
 * Extract variables from markdown template
 */
export function extractVariables(
  markdown: string,
  workflowField: Ref<{ id: string, title: string, field: ExtendedFieldRecord } | null> = ref(null),
  protocol?: ProtocolInfo | null,
) {
  const variables: Map<ScopeFieldKey, Set<string>> = new Map()
  const info: Map<ScopeFieldKey, Record<string, any>> = new Map()

  const matches = markdown.matchAll(ESCAPED_PROTOCOL_FIELDS)

  Array.from(matches).forEach(([_match, _scope, content]) => {
    // Extract field name from content (before first `:`, `,`, or whitespace)
    // e.g., "name: str" -> "name", "name, subvars=[...]" -> "name"
    const fieldNameMatch = content.match(/^([^:,\s]+)/)
    const field = fieldNameMatch ? fieldNameMatch[1].trim() : content.trim()

    // Check if this is a var with subvars (should be treated as var_table)
    const hasSubvars = /subvars\s*=\s*\[/.test(content)
    const scope: ScopeFieldKey = _scope === "var" && hasSubvars ? "var_table" : _scope as ScopeFieldKey

    const scopeName = scope === "var_table"
      ? "research_variable"
      : scope === "ref_step" || scope === "rv_ref"
        ? scope
        : scopeNameRecord[scope as Markdown.FiledName]

    const target = variables.get(scopeName)
    if (target) {
      target.add(field)
    }
    else {
      variables.set(scopeName, new Set([field]))
    }

    if (scope === "var_table") {
      // Custom parser to extract subvars content, handling quotes properly
      // Find "subvars=[" and then match brackets considering quotes
      let rawSubvarsStr = ""
      const subvarsMatch = content.match(/subvars\s*=\s*\[/)
      if (subvarsMatch && subvarsMatch.index !== undefined) {
        const startIdx = subvarsMatch.index + subvarsMatch[0].length
        let depth = 1
        let inQuote = false
        let quoteChar = ""
        for (let i = startIdx; i < content.length && depth > 0; i++) {
          const char = content[i]
          const prevChar = i > 0 ? content[i - 1] : ""

          // Handle quotes (but not escaped ones)
          if ((char === "\"" || char === "'") && prevChar !== "\\") {
            if (!inQuote) {
              inQuote = true
              quoteChar = char
            }
            else if (char === quoteChar) {
              inQuote = false
              quoteChar = ""
            }
          }

          // Only count brackets outside of quotes
          if (!inQuote) {
            if (char === "[")
              depth++
            else if (char === "]")
              depth--
          }

          if (depth > 0) {
            rawSubvarsStr += char
          }
        }
      }

      // Split by comma, but respect parentheses and quotes for var() syntax
      const subvarStrings: string[] = []
      let depth = 0
      let inQuote = false
      let quoteChar = ""
      let current = ""
      for (let i = 0; i < rawSubvarsStr.length; i++) {
        const char = rawSubvarsStr[i]
        const prevChar = i > 0 ? rawSubvarsStr[i - 1] : ""

        // Handle quotes
        if ((char === "\"" || char === "'") && prevChar !== "\\") {
          if (!inQuote) {
            inQuote = true
            quoteChar = char
          }
          else if (char === quoteChar) {
            inQuote = false
            quoteChar = ""
          }
        }

        if (!inQuote) {
          if (char === "(") {
            depth++
          }
          else if (char === ")") {
            depth--
          }
          else if (char === "," && depth === 0) {
            if (current.trim())
              subvarStrings.push(current.trim())
            current = ""
            continue
          }
        }
        current += char
      }
      if (current.trim())
        subvarStrings.push(current.trim())

      // Parse each subvar definition to extract name, type, pattern, etc.
      const parsedSubvars = subvarStrings.map(parseSubvarDefinition)
      const subvars = parsedSubvars.map(s => s.name)
      const subvarDefs: Record<string, { name: string, type?: string, pattern?: string, kwargs?: Record<string, any> }> = {}
      for (const sv of parsedSubvars) {
        subvarDefs[sv.name] = sv
      }

      const linkMatch = DYNAMIC_TABLE_LINK.exec(content)?.groups || null

      DYNAMIC_TABLE_SUB_VAR.lastIndex = 0
      DYNAMIC_TABLE_LINK.lastIndex = 0

      const targetScope = info.get(scopeName)
      let link = null
      if (linkMatch) {
        const { source, target: matchTarget } = linkMatch
        const [sourceName, sourceProp] = source.split(".")
        const [targetName, targetProp] = matchTarget.split(".")
        link = {
          source: { name: sourceName, prop: sourceProp },
          target: { name: targetName, prop: targetProp },
          isSource: sourceName === field,
        }
      }

      const fieldInfo = { type: "table", subvars, subvarDefs, link }

      if (targetScope) {
        if (targetScope[field]) {
          targetScope[field].type = "table"
          targetScope[field].subvars = subvars
          targetScope[field].subvarDefs = subvarDefs
        }
        else {
          targetScope[field] = fieldInfo
        }

        if (link) {
          const { isSource, source, target } = link
          if (!isSource) {
            const sourceInfo = info.get(scopeName)?.[source.name]
            if (sourceInfo) {
              sourceInfo.link = { ...link, isSource: true }
            }
          }
          else {
            const targetInfo = info.get(scopeName)?.[target.name]
            if (targetInfo) {
              targetInfo.link = { ...link, isSource: false }
            }
          }
        }
      }
      else {
        info.set(scopeName, { [field]: fieldInfo })
      }
    }
  })

  if (workflowField.value?.id) {
    variables.set("research_workflow", new Set([workflowField.value.id]))
  }

  // Validate table links if protocol is provided
  if (protocol?.fields) {
    validateTableLinks(info, protocol.fields)
  }

  return { variables, info }
}

// Add this function to validate table links
function validateTableLinks(
  info: Map<ScopeFieldKey, Record<string, Record<string, any>>>,
  fields: ProtocolInfo["fields"],
): void {
  info.forEach((scopeInfo, scopeName) => {
    Object.entries(scopeInfo).forEach(([fieldName, fieldInfo]) => {
      if (fieldInfo.link) {
        const { source, target } = fieldInfo.link
        const sourceExists = fields?.[scopeName as FieldKey]?.some(f => f.name === source.name)
        const targetExists = fields?.[scopeName as FieldKey]?.some(f => f.name === target.name)

        if (!sourceExists || !targetExists) {
          console.warn(`Invalid table link: ${fieldName} - source or target field not found`)
          delete fieldInfo.link
        }
      }
    })
  })
}

/**
 * Get field structure from markdown template
 */
export function getFieldStructure(
  payload: {
    markdown: string
    protocol: ProtocolInfo | null | undefined
    workflowField: Ref<{ id: string, title: string, field: ExtendedFieldRecord } | null>
    userInfo: Api.Auth.UserInfo | null
    recordData?: Partial<IRecordData>
    isReadonly?: boolean
  },
  keepCurrentValue = false,
): ExtendedExtractResult {
  const { markdown, workflowField = ref(null), protocol, userInfo = null, recordData, isReadonly } = payload

  const { variables, info } = extractVariables(markdown, workflowField)

  const { fields, json_schema, assigners } = protocol || {}
  if (!fields || !json_schema) {
    return { field: {}, rules: {} }
  }

  const entries = Object.entries(fields) as [
    ScopeFieldKey,
    FieldItem[],
  ][]

  /** Rv_ref and ref_step ref fields */
  const refEntries: ["rv_ref" | "ref_step", Set<string>][] = []

  // Create dependentMap to track field dependencies
  const dependentMap = new Map<string, Array<{ scope: IRecordDataKey, name: string }>>()

  // Track field name occurrences to handle duplicates
  const fieldNameOccurrences: Record<string, Record<string, Set<number>>> = {}

  variables.forEach((fieldList, scopeName) => {
    if (scopeName === "rv_ref" || scopeName === "ref_step") {
      entries.push([
        scopeName,
        Array.from(fieldList).map(name => ({
          name,
          line_number: -1,
          ...info.get(scopeName)?.[name],
        })),
      ])
      refEntries.push([scopeName, fieldList])
      return
    }

    if (!fields[scopeName as FieldKey]) {
      entries.push([
        scopeName as FieldKey,
        Array.from(fieldList).map(name => ({
          name,
          line_number: -1,
          ...info.get(scopeName)?.[name],
        })),
      ])
      return
    }

    const targetScope = fields[scopeName as FieldKey]
    fieldList.forEach((field) => {
      const existingIndex = targetScope.findIndex(({ name }) => name === field)
      const extraInfo = info.get(scopeName)?.[field]

      if (existingIndex === -1) {
        // Field not in backend - add with info from template
        targetScope.push({ name: field, line_number: -1, ...extraInfo })
      }
      else if (extraInfo) {
        // Field exists in backend - merge info from template (type, subvars, etc.)
        const existing = targetScope[existingIndex] as any
        if (extraInfo.type && !existing.type) {
          existing.type = extraInfo.type
        }
        // Merge subvars if extraInfo has them and existing doesn't or is empty
        if (extraInfo.subvars?.length > 0 && (!existing.subvars || existing.subvars.length === 0)) {
          existing.subvars = extraInfo.subvars
        }
        // Merge subvarDefs (contains pattern and other metadata)
        if (extraInfo.subvarDefs && !existing.subvarDefs) {
          existing.subvarDefs = extraInfo.subvarDefs
        }
        if (extraInfo.link && !existing.link) {
          existing.link = extraInfo.link
        }
      }
    })
  })

  // Process entries to build field structure
  const result = entries.reduce(
    (acc, [k, v]) => {
      const scope = scopeKeyRecord[k]
      const schema = json_schema[k as keyof typeof json_schema]

      const {
        properties,
        required,
        title: scopeTitle = "",
        type: scopeType = "text",
        description,
        $defs,
      } = schema || {}

      const hasRequired = Boolean(required)
      const isBoolean = scopeType === "boolean" || k === "research_check" || k === "research_step"

      // const recordKey = getRecordDataKey(k)
      // Initialize scope record with metadata
      const initRecord: ExtendedFieldRecord = {
        __SCOPE__: {
          label: scope,
          value: "top",
          disabled: false,
          required: true,
          scope: k,
          title: scopeTitle,
          description,
          type: scopeType,
          id: `scope-${scope}`,
        },
      }

      if (scopeTitle === "VarModel") {
        initRecord.__SCOPE__.title = "Variables"
      }
      else if (scope === "step") {
        initRecord.__SCOPE__.title = "Steps"
      }
      else if (scope === "check") {
        initRecord.__SCOPE__.title = "Checkpoints"
      }

      // Handle workflow fields
      if (k === "research_workflow") {
        if (workflowField.value?.field) {
          acc.field[k] = {
            ...initRecord,
            ...workflowField.value.field,
          }
        }
        return acc
      }

      // Process each field in the scope
      acc.field[k] = v.reduce((propAcc, it) => {
        const { name, type: rawType, subvars, subvarDefs } = it as any

        // Skip fields without a valid name
        if (!name) {
          return propAcc
        }

        const isRequired = Boolean(hasRequired && required?.includes(name))
        const fieldProps = properties?.[name] ?? {}
        const {
          title,
          type,
          default: defaultValue,
          items,
          recommended_protocol_id,
          enum: enumValue,
        } = fieldProps

        // Determine input type
        const inputType = getInputType(fieldProps as JsonSchema & { anyOf?: JsonSchema[] })

        // Initialize field value based on type
        const assigner = assigners?.[name]
        const disabled = isReadonly || Boolean(assigner && assigner.mode === "auto_force")
        const refValue = items?.$ref ? getRefValue(schema, items.$ref) : undefined
        const recordItem = recordData?.[k]?.[name]
        const recordValue = (recordItem && !Array.isArray(recordItem) && typeof recordItem === "object") ? (recordItem as IRecordDataItem).value ?? recordItem : recordItem
        let value = keepCurrentValue || enumValue ? recordValue : getInitialValue(recordData?.[k]?.[name], inputType, rawType, isBoolean, refValue || items)

        if (value === null) {
          value = getDefaultValue(isBoolean, inputType, userInfo, defaultValue, recommended_protocol_id)
        }

        // Handle duplicate field names by using line_number to create a unique key
        let fieldKey = name
        const lineNumber = it.line_number || -1

        // Initialize tracking for this scope if it doesn't exist
        if (!fieldNameOccurrences[k]) {
          fieldNameOccurrences[k] = {}
        }

        // Initialize tracking for this field name if it doesn't exist
        if (!fieldNameOccurrences[k][name]) {
          fieldNameOccurrences[k][name] = new Set<number>()
        }

        // Check if this field name + line number combination already exists
        if (fieldNameOccurrences[k][name].has(lineNumber)) {
          // If duplicate exists with same line number, use the name as is (will overwrite)
          console.warn(`Duplicate field found with same line number: ${k}.${name} at line ${lineNumber}`)
        }
        else if (fieldNameOccurrences[k][name].size > 0) {
          // If the field name already exists but with different line number, create a unique key
          fieldKey = `${name}_${lineNumber}`
          console.info(`Created unique field key for duplicate: ${fieldKey} (original: ${name})`)
        }

        // Track this field occurrence
        fieldNameOccurrences[k][name].add(lineNumber)

        // Create field item with assigner
        propAcc[fieldKey] = {
          label: name,
          disabled,
          value,
          scope: k,
          title: title || name,
          type: enumValue ? "enum" : rawType || inputType,
          required: isRequired,
          raw: it,
          id: `field-${k}-${fieldKey}`,
          assigner,
          originalName: fieldKey !== name ? name : undefined, // Store original name for reference
        }

        if (assigner && assigner.mode === "auto_first") {
          propAcc[fieldKey].assignedSet = new Set<string>()
        }

        // Handle table relationships
        if (rawType === "table" && inputType !== "array") {
          // Only handle var_table, not list[Partner] which has inputType='array'
          const tableInfo = info?.get(k)?.[name]
          if (tableInfo?.link) {
            propAcc[fieldKey] = {
              ...propAcc[fieldKey],
              links: {
                ...tableInfo.link,
                type: tableInfo.type || "one-to-one",
              },
              onUpdate: (value: any) => {
                handleTableUpdate(value, tableInfo.link, acc.field)
              },
            }
          }
        }

        // Add validation rules
        if (fieldProps) {
          let ajvValidate = null
          try {
            ajvValidate = ajv.compile({ $defs: $defs || { [name]: {} }, ...fieldProps })
          }
          catch (err) {
            console.error(`Failed to compile rule for ${name}:`, err)
          }

          if (!acc.rules[k as FieldKey]) {
            acc.rules[k as FieldKey] = {}
          }

          // Special handling for reference fields
          if (k === "rv_ref" || k === "ref_step") {
            acc.rules[k as FieldKey]![fieldKey] = {
              ajv: null,
              value: {
                required: isRequired,
                trigger: ["change", "blur"],
                validator: (rule, value) => {
                  if (!value)
                    return isRequired ? new Error("Reference is required") : true

                  // Validate reference exists
                  const refExists = validateReference(k, value, refEntries)
                  if (!refExists) {
                    return new Error(`Invalid reference: ${value}`)
                  }
                  return true
                },
                key: `${k}.${name}.value`,
              },
            }
          }
          else {
            acc.rules[k as FieldKey]![fieldKey] = {
              ajv: ajvValidate,
              value: {
                required: isRequired,
                trigger: ["change", "blur", "submit"],
                validator: (rule, value) => {
                  if (typeof fieldProps.default === "object" && fieldProps.default?.rrec_airalogy_id) {
                    return true
                  }

                  // Skip "should not be empty" validation for assigner fields
                  // Assigner fields are computed by backend, user should click compute button
                  // The validation will happen when user submits the form (before submission we should ensure all assigners are computed)
                  if (!assigner && isRequired && (value === null || typeof value === "undefined" || value === "")) {
                    return new Error("Should not be empty")
                  }

                  // Add array/list validation (including list[Partner] which has rawType='table')
                  // Check inputType first as it's more reliable for array types
                  // Note: Cell-level validation is now handled by dynamic cell rules (see below)
                  // This array-level validation is kept for backward compatibility and overall array validation
                  if (inputType === "array" || type === "array") {
                    // Validate even if array is empty or undefined (for required fields)
                    const arrayValue = Array.isArray(value) ? value : []
                    // Only validate array-level constraints (like minimum items), skip item validation
                    // Item validation is now done at cell level
                    if (isRequired && arrayValue.length === 0 && !assigner) {
                      return new Error("At least one item is required")
                    }
                  }
                  // Add table validation (for var_table fields)
                  else if (rawType === "table" && Array.isArray(value)) {
                    const tableValidation = validateTableStructure(value, items)
                    if (!tableValidation.valid) {
                      return new Error(tableValidation.message)
                    }
                  }

                  if (inputType === "date") {
                    if (typeof value === "string") {
                      const date = dayjs(value)
                      if (!date.isValid()) {
                        return new Error("Invalid date")
                      }
                    }
                    else if (typeof value === "object" && Object.hasOwn(value, "value")) {
                      const date = dayjs(value.value)
                      if (!date.isValid()) {
                        return new Error("Invalid date")
                      }
                    }
                  }

                  if (ajvValidate) {
                    let validateValue = value
                    const builtInType = (ajvValidate.schema as any)?.airalogy_built_in_type || (ajvValidate.schema as any)?.airalogy_type
                    if (builtInType) {
                      if (builtInType === "ATCG") {
                        if (!/^[ATCG]*$/.test(value)) {
                          return new Error("ATCG sequence can only contain the letters A, T, C, G.")
                        }
                      }
                      if (Array.isArray(value)) {
                        // For file uploads, check if files are still uploading (no airalogyId yet)
                        // If so, skip ajv validation - we just need to verify files exist
                        const hasUploadingFile = value.some((f: any) => f && !f.airalogyId && f.status !== "finished")
                        if (hasUploadingFile && value.length > 0) {
                          // Files are selected but still uploading, consider valid for now
                          return true
                        }
                        validateValue = value[0]?.airalogyId || value[0]?.id
                      }
                      else if (value?.airalogy_file_id) {
                        validateValue = value?.airalogy_file_id
                      }
                      else if (value?.formattedValue) {
                        validateValue = value.formattedValue
                      }
                      else if (value?.value) {
                        validateValue = value.value
                      }
                      else {
                        validateValue = value
                      }
                    }
                    else if (value !== null && typeof value === "object") {
                      if (Array.isArray(value)) {
                        validateValue = normalizeAjvValue(value)
                      }
                      else {
                        validateValue = normalizeAjvValue(value)
                      }
                    }
                    else if (!isRequired && (typeof value === "undefined" || value === null)) {
                      if (type === "string") {
                        validateValue = ""
                      }
                    }

                    const isValid = ajvValidate(validateValue)
                    if (ajvValidate.errors) {
                      return ajvValidate.errors.map(err => new Error(err.message))
                    }
                    return isValid
                  }

                  return true
                },
                key: `${k}.${name}.value`,
              },
            }
          }
        }

        if (assigner) {
          const { dependent_fields } = assigner
          if (Array.isArray(dependent_fields) && dependent_fields.length > 0) {
            dependent_fields.forEach((varName) => {
              // Find target scope for the dependent field
              const targetScope = getTargetScope(varName, entries) || k
              const targetDependent = dependentMap.get(`${targetScope}.${varName}`)

              if (targetDependent) {
                // Add to existing dependent list
                targetDependent.push({ scope: k, name: fieldKey })
              }
              else {
                // Create new dependent list
                dependentMap.set(`${targetScope}.${varName}`, [{ scope: k, name: fieldKey }])
              }
            })
          }
        }
        else if (rawType === "table" && Array.isArray(subvars) && subvars.length > 0) {
          const prefix = `${name}.`

          subvars.forEach((varName) => {
            const fullVarName = `${prefix}${varName}`
            const assigner = assigners?.[fullVarName]
            if (assigner) {
              const targetField = propAcc[fieldKey]
              if (!targetField) {
                return
              }

              const { dependent_fields } = assigner
              if (!targetField.assignerRecord) {
                targetField.assignerRecord = {}
              }

              targetField.assignerRecord![fullVarName] = assigner

              if (targetField.raw) {
                targetField.raw.assigner = assigner
              }

              if (assigner.mode === "auto_first") {
                targetField.assignedSet = new Set<string>()
              }

              if (Array.isArray(dependent_fields) && dependent_fields.length > 0) {
                dependent_fields.forEach((dependentVarName) => {
                  const targetDependent = dependentMap.get(`var_table.${dependentVarName}`)

                  if (targetDependent) {
                    // Add to existing dependent list
                    targetDependent.push({ scope: k, name: fullVarName })
                  }
                  else {
                    // Create new dependent list
                    dependentMap.set(`var_table.${dependentVarName}`, [{ scope: k, name: fullVarName }])
                  }
                })
              }
            }
          })
        }

        return propAcc
      }, initRecord)

      return acc
    },
    { field: {}, rules: {} } as ExtendedExtractResult,
  )

  if (isReadonly) {
    return result
  }

  // After the reduce operation, process the dependentMap
  dependentMap.forEach((value, key) => {
    const [scope, prop, subVar] = key.split(".")
    if (scope === "var_table") {
      // Find field by original name in case it was renamed for uniqueness
      const fields = Object.entries(result.field?.research_variable || {})
      const targetEntry = fields.find(([_, field]) => field.originalName === prop || field.label === prop)
      const target = targetEntry?.[1]

      if (target) {
        // Deduplicate dependents using a Set
        const nameSet = new Set<string>()
        const dependent: Array<{ name: string, scope: IRecordDataKey }> = []

        value.forEach((dep) => {
          const key = `${dep.scope}.${dep.name}`
          if (!nameSet.has(key)) {
            nameSet.add(key)
            dependent.push(dep)
          }
        })

        if (subVar) {
          const path = `${prop}.${subVar}`
          if (target.dependentRecord) {
            target.dependentRecord[path] = dependent
          }
          else {
            // Set the deduplicated dependents
            target.dependentRecord = {
              [path]: dependent,
            }
          }

          if (target.raw) {
            target.raw.dependent = dependent
          }
        }
        else {
          target.dependent = dependent

          if (target.raw) {
            target.raw.dependent = dependent
          }
        }
      }

      return
    }

    // Find field by original name in case it was renamed for uniqueness
    const fields = Object.entries(result.field?.[scope as ScopeFieldKey] || {})
    const targetEntry = fields.find(([_, field]) => field.originalName === prop || field.label === prop)
    const target = targetEntry?.[1]

    if (target) {
      // Deduplicate dependents using a Set
      const nameSet = new Set<string>()
      const dependent: Array<{ name: string, scope: IRecordDataKey }> = []

      value.forEach((dep: { scope: IRecordDataKey, name: string }) => {
        const key = `${dep.scope}.${dep.name}`
        if (!nameSet.has(key)) {
          nameSet.add(key)
          dependent.push(dep)
        }
      })

      // Set the deduplicated dependents
      target.dependent = dependent
    }
  })

  // Generate cell-level validation rules for array fields (list[Partner] style)
  // This enables validation to show errors on individual cells instead of the entire array
  generateCellValidationRules(result, json_schema)

  return result
}

/**
 * Generate cell-level validation rules for array fields
 * This creates dynamic validation paths like: research_variable.partners.value[*].partner_email
 * which can be used to validate individual cells in the array
 */
function generateCellValidationRules(
  result: ExtractResult,
  json_schema: Record<string, any> | undefined,
): void {
  if (!json_schema || !result.rules)
    return

  Object.entries(result.field).forEach(([scopeKey, scopeFields]) => {
    if (!scopeFields || scopeKey === "__SCOPE__")
      return

    Object.entries(scopeFields).forEach(([fieldKey, fieldItem]) => {
      if (!fieldItem || fieldKey === "__SCOPE__")
        return

      const { type, raw } = fieldItem as any
      const schema = json_schema[scopeKey as keyof typeof json_schema]

      // Check if this is an array/list type field (e.g., list[Partner])
      if (type === "table" || type === "array") {
        const fieldProps = schema?.properties?.[fieldKey]
        const items = fieldProps?.items

        // Get subvars from raw or from JSON schema items.properties
        const subvars = raw?.subvars || (items?.properties ? Object.keys(items.properties) : [])
        const subvarDefs = raw?.subvarDefs || {}

        if (subvars.length > 0 && items?.properties) {
          // Initialize cellRules in the rules object if not exists
          if (!(result.rules as any).cellRules) {
            (result.rules as any).cellRules = {}
          }

          // Create cell-level rules for each subvar
          subvars.forEach((subvarName: string) => {
            const subvarPropSchema = items.properties[subvarName] || {}
            const subvarDef = subvarDefs[subvarName] || {}

            // Get pattern from subvarDef (parsed from markdown) or from schema
            const pattern = subvarDef.pattern || subvarDef.kwargs?.pattern || subvarPropSchema.pattern
            const subvarType = subvarPropSchema.type || subvarDef.type || "string"
            const isRequired = items.required?.includes(subvarName) || false

            // Create the cell rule key: scope.field.subvar
            const cellRuleKey = `${scopeKey}.${fieldKey}.${subvarName}`

            ;(result.rules as any).cellRules[cellRuleKey] = {
              pattern,
              type: subvarType,
              required: isRequired,
              // Validator function that can be called for individual cells
              validator: (value: any, rowIndex: number): { valid: boolean, message: string } => {
                // Skip validation for empty values if not required
                if (!isRequired && (value === null || value === undefined || value === "")) {
                  return { valid: true, message: "" }
                }

                // Required field validation
                if (isRequired && (value === null || value === undefined || value === "")) {
                  return { valid: false, message: `${subvarName} is required` }
                }

                // Pattern validation - skip if pattern is empty string or only whitespace
                if (pattern && pattern.trim() && typeof value === "string" && value.trim()) {
                  try {
                    const regex = new RegExp(pattern)
                    const trimmedValue = value.trim()
                    if (!regex.test(trimmedValue)) {
                      return { valid: false, message: `${subvarName} does not match required pattern` }
                    }
                  }
                  catch (e) {
                    console.warn(`Invalid regex pattern for ${subvarName}:`, pattern, e)
                  }
                }

                // Type validation
                const typeMap: Record<string, string> = { str: "string", int: "number", float: "number", bool: "boolean" }
                const expectedType = typeMap[subvarType] || subvarType
                const actualType = typeof value

                if (expectedType === "number" && actualType !== "number" && value !== null && value !== undefined) {
                  if (Number.isNaN(Number(value))) {
                    return { valid: false, message: `${subvarName} must be a valid number` }
                  }
                }

                return { valid: true, message: "" }
              },
            }
          })
        }
      }
    })
  })
}

// Helper functions for validation
function validateTableStructure(value: any[], items: any): { valid: boolean, message: string } {
  if (!items || !items.properties) {
    return { valid: true, message: "" }
  }

  const requiredProps = items.required || []
  const properties = items.properties

  for (const row of value) {
    // Check required properties
    for (const prop of requiredProps) {
      if (row[prop] === undefined || row[prop] === null || row[prop] === "") {
        return { valid: false, message: `Missing required property: ${prop}` }
      }
    }

    // Validate property types and formats
    for (const [key, val] of Object.entries(row)) {
      const propSchema = properties[key]
      if (!propSchema)
        continue

      const expectedType = propSchema.type

      // Skip validation for null/empty values (unless required)
      if (val === null || val === undefined || val === "") {
        if (requiredProps.includes(key)) {
          return { valid: false, message: `Missing required property: ${key}` }
        }
        continue
      }

      // Type validation
      const actualType = typeof val
      if (actualType !== expectedType
        && !(expectedType === "number" && actualType === "object" && val instanceof Big)) {
        return {
          valid: false,
          message: `Invalid type for ${key}: expected ${expectedType}, got ${actualType}`,
        }
      }

      // Pattern (regex) validation - skip if pattern is empty string or only whitespace
      const expectedPattern = propSchema.pattern
      if (expectedPattern && expectedPattern.trim() && actualType === "string") {
        const stringVal = String(val).trim()
        if (stringVal) { // Only validate non-empty strings
          try {
            const regex = new RegExp(expectedPattern)
            if (!regex.test(stringVal)) {
              return {
                valid: false,
                message: `Invalid format for ${key}: ${stringVal} does not match required pattern`,
              }
            }
          }
          catch (e) {
            console.warn(`Invalid regex pattern for ${key}:`, expectedPattern, e)
          }
        }
      }
    }
  }

  return { valid: true, message: "" }
}

// const UUID_REGEX = /^[0-9A-F]{8}-[0-9A-F]{4}-[1-5][0-9A-F]{3}-[89AB][0-9A-F]{3}-[0-9A-F]{12}$/i
const UUID_REGEX = /^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$/i

const EXAMPLE_ID_REGEX = /^x{8}-x{4}-x{4}-x{4}-x{12}$/
type ExampleType = "record" | "file" | "image"
function validateByExample(value: string, example: `airalogy.id.${ExampleType}.${string}` | `airalogy.id.${ExampleType}.${string}.${string}`) {
  if (!example || !value) {
    return true
  }

  const target = example.split(".")
  const [_prefixAiralogy, _prefixId, type, id] = target
  const result = value.split(".")
  const [resultPrefixAiralogy, resultPrefixId, resultType, resultId, resultExt, resultVersion] = result

  const targetLength = (type === "record" && resultVersion ? 2 : 0) + target.length

  if (result.length !== targetLength) {
    return false
  }

  if (resultPrefixAiralogy !== _prefixAiralogy) {
    return false
  }

  if (resultPrefixId !== _prefixId) {
    return false
  }

  if (resultType !== type) {
    return false
  }

  if (type === "file" && !resultExt) {
    return false
  }

  if (EXAMPLE_ID_REGEX.test(id)) {
    return UUID_REGEX.test(resultId)
  }

  return true
}
export const EMPTY_ARRAY_MESSAGE = "Array is empty"

function validateArrayItems(
  value: any[],
  items: any,
  rule: FormItemRule,
  subvarDefs?: Record<string, { name: string, type?: string, pattern?: string, kwargs?: Record<string, any> }>,
): { valid: boolean, message: string } {
  if (!items) {
    return { valid: true, message: "" }
  }

  const { type, format, airalogy_type, airalogy_built_in_type, examples, properties, required: requiredProps } = items

  const size = value?.length
  // Check if array is empty
  if (!size || size === 0) {
    // For list[SubModel] types (object arrays with properties), empty array is valid
    // since list[SubModel] in Python allows empty list [] as a valid value
    // Check both direct object type and $ref references (which indicate SubModel types)
    if ((type === "object" && properties) || items.$ref) {
      return { valid: true, message: "" }
    }
    // For other required fields, empty array is invalid
    if (rule.required) {
      return { valid: false, message: "At least one item is required" }
    }
    // For optional fields, empty array is valid
    return { valid: true, message: "" }
  }

  for (let i = 0; i < value.length; i++) {
    const item = value[i]

    // Validate special types (FileId, RecordId)
    if ((airalogy_type === "FileId" || airalogy_built_in_type === "FileId") && !validateByExample(item, examples[0])) {
      return { valid: false, message: `Array items must be ${examples[0]}` }
    }

    if ((airalogy_type === "RecordId" || airalogy_built_in_type === "RecordId") && !validateByExample(item, examples[0])) {
      return { valid: false, message: `Array items must be ${examples[0]}` }
    }

    // Validate simple types
    if (type === "string" && typeof item !== "string") {
      return { valid: false, message: "Array items must be strings" }
    }

    if (type === "number" && typeof item !== "number") {
      return { valid: false, message: "Array items must be numbers" }
    }

    if (format === "date-time" && !dayjs(item).isValid()) {
      return { valid: false, message: "Invalid date-time format" }
    }

    // Validate object arrays (e.g., list[Partner])
    // Check if item is an object and we have either schema properties or subvarDefs from markdown
    const isObjectItem = typeof item === "object" && item !== null && !Array.isArray(item)
    const hasValidationDefs = properties || (subvarDefs && Object.keys(subvarDefs).length > 0)

    if (isObjectItem && hasValidationDefs) {
      // Check required properties
      if (requiredProps && Array.isArray(requiredProps)) {
        for (const prop of requiredProps) {
          if (item[prop] === undefined || item[prop] === null || item[prop] === "") {
            return { valid: false, message: `Item ${i + 1}: Missing required property '${prop}'` }
          }
        }
      }

      // Validate all properties defined in subvarDefs, not just those in item
      const allKeys = new Set([...Object.keys(item), ...(subvarDefs ? Object.keys(subvarDefs) : [])])

      for (const key of allKeys) {
        const val = item[key]
        const propSchema = properties?.[key] || {}
        // Get subvar definition from parsed markdown (contains pattern from template)
        const subvarDef = subvarDefs?.[key]

        // Map Python types to JavaScript types
        const typeMap: Record<string, string> = { str: "string", int: "number", float: "number", bool: "boolean" }
        const rawExpectedType = propSchema.type || subvarDef?.type
        const expectedType = rawExpectedType ? (typeMap[rawExpectedType] || rawExpectedType) : undefined
        // Pattern from subvarDefs (markdown) takes precedence over JSON schema
        const expectedPattern = subvarDef?.pattern || subvarDef?.kwargs?.pattern || propSchema.pattern

        // Skip validation for null/empty values (unless required)
        if (val === null || val === undefined || val === "") {
          if (requiredProps && requiredProps.includes(key)) {
            return { valid: false, message: `Item ${i + 1}: Missing required property '${key}'` }
          }
          continue
        }

        // Type validation
        const actualType = typeof val
        if (expectedType && actualType !== expectedType && !(expectedType === "number" && actualType === "object" && val instanceof Big)) {
          return { valid: false, message: `Item ${i + 1}: Property '${key}' must be of type ${expectedType}` }
        }

        // Pattern (regex) validation - skip if pattern is empty string or only whitespace
        if (expectedPattern && expectedPattern.trim() && (actualType === "string" || typeof val === "string")) {
          const stringVal = String(val).trim()
          if (stringVal) {
            try {
              const regex = new RegExp(expectedPattern)
              if (!regex.test(stringVal)) {
                return { valid: false, message: `Item ${i + 1}: Property '${key}' does not match required pattern` }
              }
            }
            catch (e) {
              console.warn(`Invalid regex pattern for ${key}:`, expectedPattern, e)
            }
          }
        }
      }
    }
  }

  return { valid: rule.required ? !!value : true, message: "" }
}

function validateReference(type: string, value: string, refEntries: ["rv_ref" | "ref_step", Set<string>][]): boolean {
  const refEntry = refEntries.find(([t]) => t === type)
  if (!refEntry)
    return false

  const [_, refs] = refEntry
  return refs.has(value)
}

function normalizeAjvValue(value: any): any {
  if (Array.isArray(value)) {
    return value.map(item => normalizeAjvValue(item))
  }

  if (!value || typeof value !== "object") {
    return value
  }

  if (value.type === "image" || value.type === "file" || value.airalogy_file_id) {
    return value.airalogy_file_id
  }

  if (value.value instanceof Big) {
    return value.value.toNumber()
  }

  if ("value" in value && ("displayedValue" in value || "formattedValue" in value || "type" in value)) {
    return normalizeAjvValue(value.value)
  }

  if ("formattedValue" in value && !("value" in value)) {
    return value.formattedValue
  }

  return Object.fromEntries(
    Object.entries(value).map(([key, nestedValue]) => [key, normalizeAjvValue(nestedValue)]),
  )
}

function handleTableUpdate(
  value: any,
  links: {
    source: { name: string, prop: string }
    target: { name: string, prop: string }
    type?: "one-to-one" | "one-to-many"
  },
  fieldModel: Record<string, ExtendedFieldRecord>,
) {
  const { source, target, type = "one-to-one" } = links
  if (!source || !target)
    return

  const sourceScope = getTargetScope(source.name, Object.entries(fieldModel))
  const targetScope = getTargetScope(target.name, Object.entries(fieldModel))

  if (!sourceScope || !targetScope)
    return

  const sourceField = fieldModel[sourceScope]?.[source.name]
  const targetField = fieldModel[targetScope]?.[target.name]

  if (!sourceField || !targetField)
    return

  // Update linked fields based on the relationship type
  if (type === "one-to-one") {
    targetField.value = value
  }
  else if (type === "one-to-many") {
    if (!Array.isArray(targetField.value)) {
      targetField.value = []
    }
    targetField.value.push(value)
  }
}

function handleNumberValue(recordValue: number, inputType: string) {
  return {
    value: new Big(recordValue),
    displayedValue: String(recordValue),
    type: inputType,
  }
}

function handleDateTimeValue(recordValue: string, type?: string | undefined) {
  const dayInst = dayjs(recordValue)

  if (type === "date") {
    return {
      value: dayInst.valueOf(),
      formattedValue: dayInst.format("YYYY-MM-DD"),
    }
  }

  if (type === BuiltInType.CurrentTime) {
    return {
      value: dayInst.format(),
      formattedValue: dayInst.format("YYYY-MM-DD HH:mm:ss"),
    }
  }

  return {
    value: dayInst.valueOf(),
    formattedValue: dayInst.format("YYYY-MM-DD HH:mm:ss"),
  }
}

function handleArrayValue(recordValue: any[], items?: { airalogy_type?: string, airalogy_built_in_type?: string }) {
  const { airalogy_built_in_type, airalogy_type } = items || {}
  const itemType = airalogy_type || airalogy_built_in_type
  return itemType === "RecordId" ? recordValue : [...recordValue]
}

function handleString(value: string) {
  return value
}

function handleTableValue(recordValue: any[], schema?: JSONSchemaType<any>) {
  if (!schema?.properties || !Array.isArray(recordValue)) {
    return recordValue
  }

  const properties = schema.properties
  return recordValue.map((row) => {
    return Object.fromEntries(Object.entries(row).map(([key, value]) => {
      const info = properties?.[key]
      let convertedValue = value
      if (info) {
        const { type } = info
        convertedValue = getInitialValue(value, type, undefined, false)
      }

      return [key, convertedValue]
    }))
  })
}

function handleBooleanValue(recordValue: { annotation?: string, checked?: boolean | null }) {
  return {
    annotation: recordValue.annotation || "",
    checked: recordValue.checked ?? null,
  }
}

function handleFileValue(recordValue: Record<string, any>, inputType: string) {
  return {
    ...recordValue,
    type: inputType,
  }
}

function isNumberType(inputType: string) {
  return (inputType === "number" || inputType === "float" || inputType === "integer")
}
function getInitialValue(
  recordValue: any,
  inputType: string,
  rawType: string | undefined,
  isBoolean: boolean,
  items?: any,
) {
  if (typeof recordValue === "undefined" || recordValue === null)
    return null

  if (isNumberType(inputType) && typeof recordValue === "number") {
    return handleNumberValue(recordValue, inputType)
  }

  if (inputType === BuiltInType.CurrentTime || inputType === "datetime" || inputType === "date") {
    if (typeof recordValue === "object" && Object.hasOwn(recordValue, "value")) {
      return handleDateTimeValue(recordValue.value, inputType)
    }
    return handleDateTimeValue(recordValue, inputType)
  }

  if (rawType === "table" && Array.isArray(recordValue)) {
    return handleTableValue(recordValue, items)
  }

  if (inputType === "file" || fileTypes.some(([type]) => type === inputType as any)) {
    if (typeof recordValue === "object") {
      return handleFileValue(recordValue, inputType)
    }
    else if (typeof recordValue === "string") {
      const result = parseAiralogyId(recordValue)
      if (result) {
        const { extension, uuid } = result as IAiralogyIdFileItem
        const fileType = getFileType(extension, true)
        return {
          id: uuid,
          type: fileType === "image" ? "image" : "file",
          airalogy_file_id: recordValue,
        } satisfies Partial<IFileDataItem>
      }
    }
  }

  if (inputType === "array" && Array.isArray(recordValue)) {
    return handleArrayValue(recordValue, items)
  }

  if (isBoolean && typeof recordValue === "object") {
    return handleBooleanValue(recordValue)
  }

  return recordValue
}

function getDefaultValue(
  isBoolean: boolean,
  inputType: string,
  userInfo: Api.Auth.UserInfo | null,
  defaultValue: any,
  recommended_protocol_id?: string,
) {
  if (isBoolean) {
    return { annotation: "", checked: null }
  }

  if (inputType === BuiltInType.CurrentTime) {
    const dayInst = dayjs()
    return { value: dayInst.format(), formattedValue: dayInst.format("YYYY-MM-DD HH:mm:ss") }
  }

  if (inputType === BuiltInType.UserName) {
    return userInfo?.name
  }

  if (inputType === "array") {
    return recommended_protocol_id ? [recommended_protocol_id] : []
  }

  if (typeof defaultValue === "number") {
    return handleNumberValue(defaultValue, inputType)
  }

  return defaultValue
}
