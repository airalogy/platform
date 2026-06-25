import type { AimdSubvar } from "@airalogy/aimd-core"
import type { SomeJSONSchema } from "ajv/dist/types/json-schema"
import { getSubvarNames } from "@airalogy/aimd-core"
import { getInputType } from "../../composables/useAIMDHelpers"

export interface TableInfo {
  name: string
  /** Subvars can be string[] or AimdSubvar[] - use getSubvarNames() to normalize */
  subvars: Array<string | AimdSubvar>
  link: any
  schema: SomeJSONSchema
  value?: any
  title?: string
  description?: string
  group?: string
}

export interface BatchProcessOptions {
  mode: "append" | "replace"
  skipEmptyRows?: boolean
  validateRequired?: boolean
  onProgress?: (processed: number, total: number) => void
  onError?: (rowIndex: number, error: string) => void
}

export interface ProcessedTableData {
  success: boolean
  processedRows: number
  errors: Array<{ rowIndex: number, error: string }>
  data: Record<string, any>[]
}

/**
 * Enhanced batch processor for table data with comprehensive validation and type conversion
 */
export class BatchTableProcessor {
  private info: TableInfo
  private tableRecord: Record<string, Record<string, any>>

  constructor(info: TableInfo, tableRecord: Record<string, Record<string, any>>) {
    this.info = info
    this.tableRecord = tableRecord
  }

  /**
   * Process raw data into format compatible with handleSetTableVariableRecord
   */
  async processData(
    rawData: Record<string, any>[],
    options: BatchProcessOptions = { mode: "append" },
  ): Promise<ProcessedTableData> {
    const { mode, skipEmptyRows = true, validateRequired = true, onProgress, onError } = options
    const result: ProcessedTableData = {
      success: true,
      processedRows: 0,
      errors: [],
      data: [],
    }

    if (!this.info.subvars || !Array.isArray(rawData)) {
      result.success = false
      result.errors.push({ rowIndex: -1, error: "Invalid table configuration or data" })
      return result
    }

    const columnInfo = this.getColumnInfo()

    for (let i = 0; i < rawData.length; i++) {
      const rawRow = rawData[i]

      try {
        // Skip empty rows if requested
        if (skipEmptyRows && this.isEmptyRow(rawRow)) {
          continue
        }

        // Validate and convert row data
        const processedRow = await this.processRow(rawRow, columnInfo, validateRequired)
        result.data.push(processedRow)
        result.processedRows++

        // Report progress
        onProgress?.(i + 1, rawData.length)
      }
      catch (error) {
        const errorMessage = error instanceof Error ? error.message : "Unknown processing error"
        result.errors.push({ rowIndex: i, error: errorMessage })
        onError?.(i, errorMessage)

        // Continue processing other rows unless it's a fatal error
        if (errorMessage.includes("Fatal:")) {
          result.success = false
          break
        }
      }
    }

    result.success = result.errors.length === 0
    return result
  }

  /**
   * Get detailed column information from table record
   */
  private getColumnInfo() {
    const { name: tableName, subvars } = this.info
    const tableInfo = this.tableRecord[tableName] || {}
    const subvarNames = getSubvarNames(subvars)

    return subvarNames.map((subvar) => {
      const fieldInfo = tableInfo[subvar] || {}
      return {
        key: subvar,
        title: fieldInfo.title || subvar,
        description: fieldInfo.description,
        type: getInputType(fieldInfo),
        required: fieldInfo.required || false,
        enum: fieldInfo.enum,
        format: fieldInfo.format,
        minimum: fieldInfo.minimum,
        maximum: fieldInfo.maximum,
        pattern: fieldInfo.pattern,
        assigner: fieldInfo.assigner,
        dependent: fieldInfo.dependent,
      }
    })
  }

  /**
   * Process a single row with validation and type conversion
   */
  private async processRow(
    rawRow: Record<string, any>,
    columnInfo: ReturnType<typeof this.getColumnInfo>,
    validateRequired: boolean,
  ): Promise<Record<string, any>> {
    const processedRow: Record<string, any> = {}

    for (const column of columnInfo) {
      const rawValue = rawRow[column.key]

      try {
        // Handle required field validation
        if (validateRequired && column.required && this.isEmpty(rawValue)) {
          throw new Error(`Required field '${column.title}' is empty`)
        }

        // Convert and validate the value
        const processedValue = await this.convertValue(rawValue, column)
        processedRow[column.key] = processedValue
      }
      catch (error) {
        throw new Error(`Column '${column.title}': ${error instanceof Error ? error.message : "Invalid value"}`)
      }
    }

    return processedRow
  }

  /**
   * Convert value based on column type with comprehensive validation
   */
  private async convertValue(value: any, column: any): Promise<any> {
    // Handle null/undefined/empty values
    if (this.isEmpty(value)) {
      return null
    }

    try {
      switch (column.type) {
        case "integer":
          return this.convertToInteger(value, column)

        case "float":
        case "number":
          return this.convertToFloat(value, column)

        case "boolean":
          return this.convertToBoolean(value)

        case "date":
        case "datetime":
          return this.convertToDate(value, column.type)

        case "array":
          return this.convertToArray(value)

        case "enum":
          return this.convertToEnum(value, column.enum)

        case "textarea":
        case "text":
        default:
          return this.convertToString(value, column)
      }
    }
    catch (error) {
      throw new Error(`Type conversion failed: ${error instanceof Error ? error.message : "Unknown error"}`)
    }
  }

  /**
   * Convert to integer with validation
   */
  private convertToInteger(value: any, column: any): number {
    const num = Number.parseInt(String(value), 10)

    if (Number.isNaN(num)) {
      throw new TypeError("Must be a valid integer")
    }

    if (column.minimum !== undefined && num < column.minimum) {
      throw new Error(`Must be at least ${column.minimum}`)
    }

    if (column.maximum !== undefined && num > column.maximum) {
      throw new Error(`Must be at most ${column.maximum}`)
    }

    return num
  }

  /**
   * Convert to float with validation
   */
  private convertToFloat(value: any, column: any): number {
    const num = Number.parseFloat(String(value))

    if (Number.isNaN(num)) {
      throw new TypeError("Must be a valid number")
    }

    if (column.minimum !== undefined && num < column.minimum) {
      throw new Error(`Must be at least ${column.minimum}`)
    }

    if (column.maximum !== undefined && num > column.maximum) {
      throw new Error(`Must be at most ${column.maximum}`)
    }

    return num
  }

  /**
   * Convert to boolean with flexible input handling
   */
  private convertToBoolean(value: any): boolean {
    if (typeof value === "boolean") {
      return value
    }

    const strValue = String(value).toLowerCase().trim()
    const truthyValues = ["true", "1", "yes", "y", "on", "enabled", "active"]
    const falsyValues = ["false", "0", "no", "n", "off", "disabled", "inactive"]

    if (truthyValues.includes(strValue)) {
      return true
    }

    if (falsyValues.includes(strValue)) {
      return false
    }

    throw new Error(`Cannot convert '${value}' to boolean. Use: true/false, 1/0, yes/no`)
  }

  /**
   * Convert to date with multiple format support
   */
  private convertToDate(value: any, type: "date" | "datetime"): string {
    let date: Date

    if (value instanceof Date) {
      date = value
    }
    else if (typeof value === "number") {
      date = new Date(value)
    }
    else {
      const parsed = Date.parse(String(value))
      if (Number.isNaN(parsed)) {
        throw new TypeError(`Invalid date format: '${value}'`)
      }
      date = new Date(parsed)
    }

    if (Number.isNaN(date.getTime())) {
      throw new TypeError(`Invalid date: '${value}'`)
    }

    return type === "date"
      ? date.toISOString().split("T")[0]
      : date.toISOString()
  }

  /**
   * Convert to array with JSON parsing support
   */
  private convertToArray(value: any): any[] {
    if (Array.isArray(value)) {
      return value
    }

    if (typeof value === "string") {
      try {
        // Try JSON parsing first
        const parsed = JSON.parse(value)
        if (Array.isArray(parsed)) {
          return parsed
        }

        // Fallback to comma-separated values
        return value.split(",").map(v => v.trim()).filter(Boolean)
      }
      catch {
        // Fallback to comma-separated values
        return value.split(",").map(v => v.trim()).filter(Boolean)
      }
    }

    return [value]
  }

  /**
   * Convert to enum value with validation
   */
  private convertToEnum(value: any, enumOptions: Record<string, any> | undefined): any {
    if (!enumOptions) {
      return String(value)
    }

    const strValue = String(value)

    // Check if value is a valid enum key
    if (strValue in enumOptions) {
      return strValue
    }

    // Check if value matches an enum value
    const matchingKey = Object.entries(enumOptions).find(([, enumValue]) =>
      String(enumValue) === strValue,
    )?.[0]

    if (matchingKey) {
      return matchingKey
    }

    throw new Error(`Invalid enum value: '${value}'. Valid options: ${Object.values(enumOptions).join(", ")}`)
  }

  /**
   * Convert to string with pattern validation
   */
  private convertToString(value: any, column: any): string {
    const strValue = String(value)

    if (column.pattern) {
      const regex = new RegExp(column.pattern)
      if (!regex.test(strValue)) {
        throw new Error(`Does not match required pattern: ${column.pattern}`)
      }
    }

    return strValue
  }

  /**
   * Check if a value is considered empty
   */
  private isEmpty(value: any): boolean {
    return value === null || value === undefined || value === ""
  }

  /**
   * Check if a row is considered empty (all values are empty)
   */
  private isEmptyRow(row: Record<string, any>): boolean {
    return Object.values(row).every(value => this.isEmpty(value))
  }

  /**
   * Generate a batch operation that integrates with handleSetTableVariableRecord
   */
  createBatchOperation(
    handleSetTableVariableRecord: (info: any, data: any[], rowIdx: number, commit?: boolean) => any,
    fieldModel: any,
    tableVariableRecord: any,
  ) {
    return async (processedData: Record<string, any>[], mode: "append" | "replace") => {
      const { name: tableName } = this.info

      try {
        // Handle replace mode: clear existing data
        if (mode === "replace") {
          if (fieldModel.research_variable?.[tableName]) {
            fieldModel.research_variable[tableName].value = []
          }
          tableVariableRecord.value[tableName] = []
        }

        // Get current row count for append mode
        const currentRowCount = mode === "append"
          ? (tableVariableRecord.value[tableName]?.length || 0)
          : 0

        // Process each row
        const results = []
        for (let i = 0; i < processedData.length; i++) {
          const rowData = processedData[i]
          const rowIndex = currentRowCount + i

          // Create the row structure using handleSetTableVariableRecord
          const result = handleSetTableVariableRecord(
            this.info,
            [rowData], // Pass as array for compatibility
            0, // Use index 0 since we're passing single-item array
            false, // Don't commit yet, we'll handle the model updates
          )

          if (result) {
            results.push({ ...result, actualIndex: rowIndex })
          }
        }

        // Batch commit all the changes
        results.forEach(({ row, model, actualIndex }) => {
          // Add to table variable record
          if (Array.isArray(tableVariableRecord.value[tableName])) {
            tableVariableRecord.value[tableName].push(row)
          }
          else {
            tableVariableRecord.value[tableName] = [row]
          }

          // Add to field model
          const targetModel = fieldModel.research_variable?.[tableName]?.value
          if (Array.isArray(targetModel)) {
            targetModel.push(model)
          }
          else if (fieldModel.research_variable[tableName]) {
            fieldModel.research_variable[tableName].value = [model]
          }
          else {
            fieldModel.research_variable[tableName] = { value: [model] }
          }
        })

        return {
          success: true,
          processedRows: results.length,
          mode,
        }
      }
      catch (error) {
        throw new Error(`Batch operation failed: ${error instanceof Error ? error.message : "Unknown error"}`)
      }
    }
  }
}

/**
 * Utility function to create a batch processor instance
 */
export function createBatchTableProcessor(
  info: TableInfo,
  tableRecord: Record<string, Record<string, any>>,
): BatchTableProcessor {
  return new BatchTableProcessor(info, tableRecord)
}

/**
 * Validate table data structure before processing
 */
export function validateTableStructure(
  data: any[],
  info: TableInfo,
  tableRecord: Record<string, Record<string, any>>,
): { valid: boolean, errors: string[] } {
  const errors: string[] = []

  if (!Array.isArray(data)) {
    errors.push("Data must be an array")
    return { valid: false, errors }
  }

  const subvarNames = getSubvarNames(info.subvars)
  if (subvarNames.length === 0) {
    errors.push("Table has no defined columns")
    return { valid: false, errors }
  }

  const tableInfo = tableRecord[info.name] || {}
  const requiredColumns = subvarNames.filter(subvar =>
    tableInfo[subvar]?.required,
  )

  // Check if data has required columns
  if (data.length > 0) {
    const firstRow = data[0]
    const missingRequired = requiredColumns.filter(col =>
      !(col in firstRow) || firstRow[col] === null || firstRow[col] === undefined,
    )

    if (missingRequired.length > 0) {
      errors.push(`Missing required columns: ${missingRequired.join(", ")}`)
    }
  }

  return { valid: errors.length === 0, errors }
}
