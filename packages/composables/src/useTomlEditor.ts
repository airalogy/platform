import type { ProtocolModels } from "@airalogy/shared/types/models"
import type { Ref } from "vue"
import { type Change, diffLines } from "diff"
import { cloneDeep, isEqual } from "lodash-es"
import { parse, stringify, stringifyArray } from "smol-toml"
import { computed, nextTick, ref, unref, watch } from "vue"

// TOML parsing result interface
interface TomlParseResult {
  data: { airalogy_protocol?: Record<string, any>, [key: string]: any }
  lineRanges: Record<string, { start: number, end: number }>
}

// Extract H1 heading from markdown content for default name
export function extractH1FromAimd(content?: string): string | undefined {
  if (!content)
    return undefined

  // Look for markdown H1 heading (# Title) - using a safer regex pattern
  const h1Match = content.match(/^#[ \t]([^\n]+)$/m)
  if (h1Match && h1Match[1]) {
    return h1Match[1].trim()
  }

  return undefined
}

/**
 * Composable for TOML editing with line preservation
 * Handles tracking and applying modifications to TOML data
 * while preserving original line numbers
 */
export function useTomlEditor(
  formData: ProtocolModels.ProtocolMetaData,
  originalToml: Ref<string>,
  aimdContent?: Ref<string>,
) {
  const originalData = ref({}) as Ref<ProtocolModels.ProtocolMetaData>
  const parsedToml = ref<TomlParseResult>({ data: {}, lineRanges: {} })

  // Check if data has been modified
  const diffContent = ref<Change[]>([])
  const hasModifications = ref(false)

  // Generated TOML with preserved line numbers
  const generatedToml = computed(() => {
    try {
      return generateModifiedToml()
    }
    catch (error) {
      console.error("Error generating TOML:", error)
      return "Error generating TOML"
    }
  })
  // Default name from markdown if available
  const defaultName = computed(() => extractH1FromAimd(unref(aimdContent)))

  // Setup original data when originalToml changes
  watch(originalToml, (value) => {
    console.log("🔄 originalToml watcher triggered", { hasValue: !!value })

    try {
      if (value) {
        // Parse TOML with line ranges first
        parsedToml.value = parseTomlWithLineRanges(value)
        console.log("📊 Parsed TOML data:", parsedToml.value.data)

        // Set originalData from parsed TOML data (not from formData)
        const parsedData = parsedToml.value.data
        originalData.value = cloneDeep(parsedData) as ProtocolModels.ProtocolMetaData

        // Initialize special fields to ensure they exist in originalData
        if (!originalData.value.authors)
          originalData.value.authors = []
        if (!originalData.value.maintainers)
          originalData.value.maintainers = []
        if (!originalData.value.disciplines)
          originalData.value.disciplines = []
        if (!originalData.value.keywords)
          originalData.value.keywords = []

        console.log("✅ originalData set from parsed TOML:", originalData.value)
      }
      else {
        // Reset to empty state if no TOML
        originalData.value = {} as ProtocolModels.ProtocolMetaData
        parsedToml.value = { data: {}, lineRanges: {} }
        console.log("🔄 Reset originalData and parsedToml to empty state")
      }
    }
    catch (error) {
      console.error("❌ Error in originalToml watcher:", error)
    }
  }, { immediate: true })

  // Watch for form data changes and detect modifications
  watch(formData, (value) => {
    console.log("🔄 formData watcher triggered")

    // Use nextTick to ensure originalData has been updated first
    nextTick(() => {
      console.log("🔍 Comparing formData with originalData", {
        formData: value,
        originalData: originalData.value,
      })

      const isModified = !isEqual(value, originalData.value)
      hasModifications.value = isModified

      console.log("📊 Modification detection result:", { isModified })

      if (!isModified && originalToml.value) {
        diffContent.value = []
        console.log("✅ No modifications detected, clearing diff")
        return
      }

      // Generate diff content
      console.log("🔄 Generating diff content...")
      diffContent.value = diffLines(originalToml.value, generatedToml.value, {
        newlineIsToken: true,
        ignoreWhitespace: false,
      })
      console.log("📊 Generated diff content:", diffContent.value.length, "changes")
    })
  })

  watch(defaultName, (value) => {
    // Use default name from markdown if name is not set
    if (!originalData.value.name && value && "name" in formData && !formData.name) {
      console.log("🔄 Setting default name from markdown:", value)
      originalData.value.name = value
      formData.name = value
    }
  })
  /**
   * Format a string array (disciplines or keywords) as TOML
   * @param fieldName Field name
   * @param values String values
   * @returns Formatted TOML string
   */
  function formatArrayToml(fieldName: string, values: any[]): string {
    // Use stringify for consistent TOML formatting
    const content = stringifyArray(values || [], 1000).trim()

    return `${fieldName} = ${content}`
  }

  /**
   * Format person array (authors or maintainers) as TOML
   * @param fieldName Field name
   * @param persons Array of ProtocolPerson objects
   * @returns Formatted TOML string
   */
  function formatPersonArrayToml(fieldName: string, persons: ProtocolModels.ProtocolPerson[]): string {
    return formatArrayToml(fieldName, persons.map(person => ({
      name: person.name,
      ...(person.email ? { email: person.email } : {}),
      ...(person.airalogy_user_id ? { airalogy_user_id: person.airalogy_user_id } : {}),
    }))).trim()
  }

  const optionalKeys: Array<keyof ProtocolModels.ProtocolMetaData> = ["airalogy_protocol_id", "authors", "keywords", "disciplines", "maintainers", "license", "description"]

  const shouldInsertNewField = (mod: { key: keyof ProtocolModels.ProtocolMetaData, currentValue: any }) => {
    const { key, currentValue } = mod
    if (optionalKeys.includes(key)) {
      if (Array.isArray(currentValue)) {
        return currentValue.length > 0
      }
      return Boolean(currentValue)
    }

    return true
  }
  /**
   * Parse TOML content with line ranges information
   * @param tomlContent The TOML content to process
   * @returns Object containing parsed data and line ranges
   */
  function parseTomlWithLineRanges(tomlContent: string): TomlParseResult {
    try {
      const result = parse(tomlContent, { maxDepth: 100, withLineRanges: true }) as unknown as TomlParseResult
      return {
        data: result.data?.airalogy_protocol || {},
        lineRanges: result.lineRanges,
      }
    }
    catch (error) {
      console.error("Error parsing TOML with line ranges:", error)
      return { data: {}, lineRanges: {} }
    }
  }

  // Generate TOML with line preservation
  function generateModifiedToml(): string {
    const originalLines = originalToml.value ? originalToml.value.split("\n") : []
    const { data: originalTomlData, lineRanges } = parsedToml.value
    const currentFormData = formData // Alias for clarity within this function scope

    // Log inputs for debugging and validation
    console.log("generateModifiedToml: Original Data:", cloneDeep(originalTomlData))
    console.log("generateModifiedToml: Current Form Data:", cloneDeep(currentFormData))
    console.log("generateModifiedToml: Line Ranges:", cloneDeep(lineRanges))

    const allKeys = new Set([...Object.keys(originalTomlData), ...Object.keys(currentFormData)] as (keyof ProtocolModels.ProtocolMetaData)[])

    // airalogy_protocol_id is a deprecated key for the TOML file, so we remove it
    allKeys.delete("airalogy_protocol_id")

    const modifications: Array<{
      key: keyof ProtocolModels.ProtocolMetaData
      newContent: string // New TOML string for the key
      originalStartLine?: number // 1-indexed from lineRanges
      originalEndLine?: number // 1-indexed from lineRanges
      isNew: boolean
      isDelete: boolean
      currentValue: any
    }> = []

    for (const key of allKeys) {
      const rangeKey = `airalogy_protocol.${key}`
      const originalValue = originalTomlData[key]
      const currentValue = currentFormData[key as keyof ProtocolModels.ProtocolMetaData]
      const keyExistsInOriginal = key in originalTomlData
      const keyExistsInForm = key in currentFormData

      if (isEqual(originalValue, currentValue)) {
        continue
      }

      let newContentForKey = ""
      if (keyExistsInForm && currentValue !== undefined) {
        if (key === "authors" || key === "maintainers") {
          newContentForKey = formatPersonArrayToml(key, currentValue as ProtocolModels.ProtocolPerson[])
        }
        else if (key === "disciplines" || key === "keywords") {
          newContentForKey = formatArrayToml(key, currentValue as string[])
        }
        else {
          newContentForKey = stringify({ [key]: currentValue }).trim()
        }
      }

      if (keyExistsInOriginal && keyExistsInForm) { // Modified
        if (lineRanges[rangeKey]) {
          modifications.push({
            key,
            newContent: newContentForKey,
            originalStartLine: lineRanges[rangeKey].start,
            originalEndLine: lineRanges[rangeKey].end,
            isNew: false,
            isDelete: false,
            currentValue,
          })
        }
        else {
          console.warn(`Modified key "${key}" not found in lineRanges. Will attempt to append if it has content.`)
          if (newContentForKey) {
            modifications.push({ key, newContent: newContentForKey, isNew: true, isDelete: false, currentValue })
          }
        }
      }
      else if (keyExistsInForm) { // New
        if (newContentForKey) {
          modifications.push({ key, newContent: newContentForKey, isNew: true, isDelete: false, currentValue })
        }
      }
      else if (keyExistsInOriginal) { // Deleted
        if (lineRanges[rangeKey]) {
          modifications.push({
            key,
            newContent: "", // Empty content for deletion
            originalStartLine: lineRanges[rangeKey].start,
            originalEndLine: lineRanges[rangeKey].end,
            isNew: false,
            isDelete: true,
            currentValue,
          })
        }
        else {
          console.warn(`Deleted key "${key}" not found in lineRanges. Cannot remove its specific lines from original TOML.`)
        }
      }
    }

    console.log("generateModifiedToml: Calculated Modifications:", cloneDeep(modifications))

    const sortedExistingModifications = modifications
      .filter(mod => !mod.isNew && mod.originalStartLine !== undefined && mod.originalEndLine !== undefined)
      .sort((a, b) => a.originalStartLine! - b.originalStartLine!)

    const newFieldsToAdd = modifications
      .filter(mod => mod.isNew && shouldInsertNewField(mod))

    const resultLines: string[] = []
    let currentOriginalLineIndex = 0 // 0-indexed for originalLines array

    for (const mod of sortedExistingModifications) {
      const modStartLine0Indexed = mod.originalStartLine! - 1
      if (modStartLine0Indexed > currentOriginalLineIndex) {
        resultLines.push(...originalLines.slice(currentOriginalLineIndex, modStartLine0Indexed))
      }

      if (mod.newContent) {
        resultLines.push(...mod.newContent.split("\n"))
      }

      currentOriginalLineIndex = mod.originalEndLine! // originalEndLine is 1-indexed and inclusive for the section
    }

    // Add any remaining lines from the original TOML after the last modification
    if (currentOriginalLineIndex < originalLines.length) {
      resultLines.push(...originalLines.slice(currentOriginalLineIndex))
    }

    // Append new fields
    if (newFieldsToAdd.length > 0) {
      // Ensure there's a separation if resultLines is not empty and doesn't end with a blank line
      if (resultLines.length > 0 && resultLines[resultLines.length - 1].trim() !== "") {
        resultLines.push("") // Add a blank line separator
      }
      for (const newField of newFieldsToAdd) {
        resultLines.push(...newField.newContent.split("\n"))
        // Add a blank line after each new field block, unless it's the very last line of the file potential
        // if (newFieldsToAdd.indexOf(newField) < newFieldsToAdd.length - 1) {
        //   resultLines.push("")
        // }
      }
    }

    // Ensure the TOML ends with a single newline if it's not empty
    // Remove trailing blank lines first, then add one if needed.
    while (resultLines.length > 0 && resultLines[resultLines.length - 1].trim() === "") {
      resultLines.pop()
    }
    if (resultLines.length > 0) {
      resultLines.push("")
    }

    if (!lineRanges.airalogy_protocol) {
      resultLines.unshift("[airalogy_protocol]")
    }

    const finalToml = resultLines.join("\n")
    console.log("generateModifiedToml: Final generated TOML:", finalToml)
    return finalToml
  }

  return {
    hasModifications,
    generatedToml,
    diffContent,
  }
}
