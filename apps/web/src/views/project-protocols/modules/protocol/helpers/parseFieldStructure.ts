import type { JsonSchema } from "@/components/custom/aimd/types/aimd-types"
import type { FieldKey, IFileDataItem, IRecordData, IRecordDataItem, IRecordDataKey, ScopeFieldKey } from "@airalogy/aimd-core/types"
import type { FieldItem, ProtocolInfo } from "@airalogy/shared/types/models/protocol"
import type { JSONSchemaType } from "ajv"
import type { Ref } from "vue"
import type { IFieldItem as IExtendedFieldItem } from "../types/types"
import { getInputType } from "@/components/custom/aimd/composables/useAIMDHelpers"
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
  /** Schema metadata consumed by the platform field renderers. Validation lives in aimd-recorder. */
  rules: Partial<Record<FieldKey, Partial<Record<string, { ajv: { schema: Record<string, any> } }>>>>
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

        // Keep the JSON Schema attached to each field for renderer metadata
        // (input kind, enums, file extension, etc.). All validation is delegated
        // to @airalogy/aimd-recorder by protocol-add-record-form.
        if (fieldProps && k !== "rv_ref" && k !== "ref_step") {
          acc.rules[k as FieldKey] ??= {}
          acc.rules[k as FieldKey]![fieldKey] = {
            ajv: { schema: fieldProps as Record<string, any> },
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

  return result
}

export const EMPTY_ARRAY_MESSAGE = "Array is empty"

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
