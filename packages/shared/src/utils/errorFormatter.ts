import type { ValidateError } from "async-validator"

export interface PydanticError {
  loc: string[]
  msg: string
  type: string
}

// Helper function to format field names for better readability
function formatFieldName(name: string): string {
  return name
    .replace(/_/g, " ")
    .split(" ")
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ")
}

// Common format function to ensure consistent output between both formatters
function formatErrorOutput(errorGroups: Record<string, { field: string, message: string, details?: string }[]>): string[] {
  const output: string[] = []

  Object.entries(errorGroups).forEach(([group, groupErrors]) => {
    // Skip empty groups
    if (groupErrors.length === 0)
      return

    // Format the field name for better readability
    const formattedGroupName = formatFieldName(group)

    // Deduplicate error messages to avoid repetition
    const uniqueErrors = new Map<string, { messages: string[], hasDetails: boolean }>()

    groupErrors.forEach(({ field, message, details }) => {
      const key = field === group ? field : `${field}: ${message}`

      if (!uniqueErrors.has(key)) {
        uniqueErrors.set(key, {
          messages: [message],
          hasDetails: !!details,
        })
      }
      else if (details) {
        // If we have details, add as a separate message
        uniqueErrors.get(key)!.messages.push(details)
        uniqueErrors.get(key)!.hasDetails = true
      }
    })

    // Convert to error lines
    const errorLines: string[] = []
    uniqueErrors.forEach((value, key) => {
      if (key === group) {
        // For the main group field, just show messages
        value.messages.forEach(msg => errorLines.push(`• ${msg}`))
      }
      else {
        // For other fields, include the field name
        const baseMessage = `• ${key}`
        if (value.hasDetails && value.messages.length > 1) {
          // If we have additional details, format as a list
          errorLines.push(baseMessage)
          value.messages.slice(1).forEach(detail =>
            errorLines.push(`  - ${detail}`),
          )
        }
        else {
          errorLines.push(baseMessage)
        }
      }
    })

    output.push(`${formattedGroupName} validation errors:\n${errorLines.join("\n")}`)
  })

  // If no error groups were processed, provide a general error message
  if (output.length === 0) {
    output.push("Validation failed: Please check your input and try again.")
  }

  return output
}

// Helper to recursively extract field errors from potentially nested error objects
function extractFieldErrors(errorObj: unknown): { field: string, message: string, details?: string }[] {
  const result: { field: string, message: string, details?: string }[] = []

  // If it's not an object, we can't extract anything
  if (!errorObj || typeof errorObj !== "object")
    return result

  // Check if it's an array of errors
  if (Array.isArray(errorObj)) {
    // Process each item in the array
    errorObj.forEach((item, index) => {
      // If this is an object with message/field properties, it's likely an error object
      if (item && typeof item === "object") {
        const typedItem = item as Record<string, unknown>

        // Check if it has a field and message - typical ValidateError format
        if (typedItem.field && typedItem.message) {
          result.push({
            field: String(typedItem.field),
            message: String(typedItem.message),
            details: `Index: ${index}`,
          })
        }
        // If it has nested errors, process them
        else if (Array.isArray(typedItem.errors)) {
          result.push(...extractFieldErrors(typedItem.errors))
        }
        // If it doesn't fit expected patterns, but has properties, use them
        else {
          // Use field/message if available, otherwise stringify the whole object
          const message = typedItem.message ? String(typedItem.message) : JSON.stringify(item)
          const field = typedItem.field ? String(typedItem.field) : `item_${index}`

          result.push({
            field,
            message,
            details: `Index: ${index}`,
          })
        }
      }
      // For primitive values, just use them as messages
      else if (item !== null && item !== undefined) {
        result.push({
          field: `item_${index}`,
          message: String(item),
        })
      }
    })
  }
  // If it's an object with errors property that's an array, handle that
  else if ("errors" in errorObj && Array.isArray((errorObj as Record<string, unknown>).errors)) {
    result.push(...extractFieldErrors((errorObj as Record<string, unknown>).errors))
  }
  // If it's an object that looks like a standard error object with field/message
  else if ("field" in errorObj && "message" in errorObj) {
    const typedObj = errorObj as Record<string, unknown>
    result.push({
      field: String(typedObj.field),
      message: String(typedObj.message),
    })
  }

  return result
}

export function formatPydanticError(error: PydanticError, errorGroups: Record<string, { field: string, message: string, details?: string }[]>) {
  // Get the main field name (first part of location path)
  const fieldPath = error.loc
  if (!fieldPath || !Array.isArray(fieldPath) || fieldPath.length === 0) {
    // Handle errors with missing location
    const mainField = "form"
    if (!errorGroups[mainField]) {
      errorGroups[mainField] = []
    }

    // Extract as much useful information as possible
    let message = error.msg || "Validation error"
    const details: string[] = []

    if (error.type) {
      details.push(`Error type: ${error.type}`)

      // Make the error message more user-friendly based on error type
      if (!error.msg) {
        if (error.type === "missing") {
          message = "Missing required field"
        }
        else if (error.type === "int_type") {
          message = "Please enter a valid integer"
        }
        else if (error.type === "float_type") {
          message = "Please enter a valid number"
        }
        else if (error.type === "string_type") {
          message = "Please enter valid text"
        }
        else if (error.type.includes("value_error")) {
          message = "Invalid value provided"
        }
      }
    }

    // Check for any other properties that might contain useful information
    const errorObj = error as unknown as Record<string, any>
    Object.entries(errorObj)
      .filter(([key]) => !["loc", "msg", "type"].includes(key) && errorObj[key] !== undefined)
      .forEach(([key, value]) => {
        const formattedValue = typeof value === "object"
          ? JSON.stringify(value)
          : String(value)

        if (formattedValue && formattedValue.trim()) {
          details.push(`${formatFieldName(key)}: ${formattedValue}`)
        }
      })

    errorGroups[mainField].push({
      field: mainField,
      message,
      details: details.length > 0 ? details.join(", ") : undefined,
    })
    return
  }

  const mainField = String(fieldPath[0])

  // Initialize group if it doesn't exist
  if (!errorGroups[mainField]) {
    errorGroups[mainField] = []
  }

  // Format the field name for display
  let displayField = ""
  if (fieldPath.length > 1) {
    // For nested fields like sample_record.0.column_number
    const nestedParts = fieldPath.slice(1)
    // Format array indices better (convert [0] to item #1)
    displayField = nestedParts.map(part =>
      typeof part === "number" ? `item #${part + 1}` : part,
    ).join(" > ")
  }
  else {
    displayField = mainField
  }

  // Format the error message based on error type
  let errorMessage = error.msg || "Invalid value"
  const details: string[] = []

  if (error.type) {
    details.push(`Error type: ${error.type}`)

    // Make the error message more user-friendly based on error type
    if (!error.msg) {
      if (error.type === "missing") {
        errorMessage = "This field is required"
      }
      else if (error.type === "int_type") {
        errorMessage = "Please enter a valid integer"
      }
      else if (error.type === "float_type") {
        errorMessage = "Please enter a valid number"
      }
      else if (error.type === "string_type") {
        errorMessage = "Please enter text"
      }
      else if (error.type.includes("value_error")) {
        errorMessage = "Invalid value provided"
      }
    }
  }

  // Check for any other properties that might contain useful information
  const errorObj = error as unknown as Record<string, any>
  Object.entries(errorObj)
    .filter(([key]) => !["loc", "msg", "type"].includes(key) && errorObj[key] !== undefined)
    .forEach(([key, value]) => {
      const formattedValue = typeof value === "object"
        ? JSON.stringify(value)
        : String(value)

      if (formattedValue && formattedValue.trim()) {
        details.push(`${formatFieldName(key)}: ${formattedValue}`)
      }
    })

  // Add to the group
  errorGroups[mainField].push({
    field: displayField,
    message: errorMessage,
    details: details.length > 0 ? details.join(", ") : undefined,
  })
}

export function formatPydanticErrors(errors: PydanticError[]) {
  if (!Array.isArray(errors)) {
    return ["Validation failed with unknown error format"]
  }

  if (errors.length === 0) {
    return ["Validation failed: No specific errors were provided."]
  }

  // Group errors by field category
  const errorGroups: Record<string, { field: string, message: string, details?: string }[]> = {}

  errors.forEach((error) => {
    formatPydanticError(error, errorGroups)
  })

  return formatErrorOutput(errorGroups)
}

export function formatValidateErrors(errors: ValidateError[]) {
  if (!Array.isArray(errors)) {
    return ["Validation failed with unknown error format"]
  }

  if (errors.length === 0) {
    return ["Validation failed: No specific errors were provided."]
  }

  // Group errors by field category
  const errorGroups: Record<string, { field: string, message: string, details?: string }[]> = {}

  // Check if we have a nested error structure
  const extractedErrors: { field: string, message: string, details?: string }[] = []

  // Try to extract nested errors first if they exist
  errors.forEach((error, index) => {
    // Check if this is potentially a container with nested errors
    if (typeof error === "object" && error !== null) {
      // Handle array-like structures where errors might be nested inside
      if ("field" in error && typeof error.field === "string") {
        // It's a regular field error, will be handled in the next step
      }
      else if (Array.isArray(error)) {
        // It's an array of errors
        extractedErrors.push(...extractFieldErrors(error))
      }
      else {
        // Check all properties for potential error objects or arrays
        Object.entries(error as Record<string, unknown>).forEach(([key, value]) => {
          if (Array.isArray(value) || (value && typeof value === "object")) {
            const nestedErrors = extractFieldErrors(value)
            if (nestedErrors.length > 0) {
              extractedErrors.push(...nestedErrors)
            }
          }
        })

        // If we didn't find any nested errors, treat it as a regular error
        if (extractedErrors.length === 0 && JSON.stringify(error) !== "{}") {
          const errorStr = JSON.stringify(error)
          extractedErrors.push({
            field: `index_${index}`,
            message: errorStr,
            details: `Original error object at index ${index}`,
          })
        }
      }
    }
  })

  // If we found nested errors, use them instead of the original array
  if (extractedErrors.length > 0) {
    // Group extracted errors by field
    extractedErrors.forEach(({ field, message, details }) => {
      // Extract the main field from the path
      const fieldPath = field.split(".")
      const mainField = fieldPath[0]

      // Initialize the group if needed
      if (!errorGroups[mainField]) {
        errorGroups[mainField] = []
      }

      // Format nested field for display
      let displayField = ""
      if (fieldPath.length > 1) {
        const nestedParts = fieldPath.slice(1)
        displayField = nestedParts.map((part) => {
          const numberIndex = Number.parseInt(part)
          return !Number.isNaN(numberIndex) ? `item #${numberIndex + 1}` : part
        }).join(" > ")
      }
      else {
        displayField = mainField
      }

      // Add the error to the appropriate group
      errorGroups[mainField].push({
        field: displayField,
        message,
        details,
      })
    })

    return formatErrorOutput(errorGroups)
  }

  // First pass - identify all field-specific errors
  errors.forEach((error) => {
    // Skip errors without fields for now - we'll handle them in a second pass
    if (!error.field)
      return

    const fieldPath = error.field.split(".")
    const mainField = fieldPath[0]

    // Initialize group if it doesn't exist
    if (!errorGroups[mainField]) {
      errorGroups[mainField] = []
    }

    // Format the field name for display
    let displayField = ""
    if (fieldPath.length > 1) {
      // For nested fields like sample_record.0.column_number
      const nestedParts = fieldPath.slice(1)
      // Format array indices better (convert [0] to item #1)
      displayField = nestedParts.map((part) => {
        const numberIndex = Number.parseInt(part)
        return !Number.isNaN(numberIndex) ? `item #${numberIndex + 1}` : part
      }).join(" > ")
    }
    else {
      displayField = mainField
    }

    // Try to get a more specific message
    let message = error.message || "Invalid value"

    // Some common validator errors can be made more user-friendly
    if (message.includes("required")) {
      message = "This field is required"
    }
    else if (message.includes("email")) {
      message = "Please enter a valid email address"
    }
    else if (message.includes("url")) {
      message = "Please enter a valid URL"
    }
    else if (message.includes("number") || message.includes("integer")) {
      message = "Please enter a valid number"
    }
    else if (message.includes("length") || message.includes("between")) {
      message = message.replace(/\[\d+, \d+\]/, (range) => {
        const [min, max] = range.slice(1, -1).split(", ")
        return `between ${min} and ${max} characters`
      })
    }

    // Extract additional information if available
    const details = typeof error === "object" && error !== null
      ? Object.entries(error as Record<string, unknown>)
        .filter(([key]) => !["field", "message"].includes(key) && (error as Record<string, unknown>)[key] !== undefined)
        .map(([key, value]) => `${formatFieldName(key)}: ${JSON.stringify(value)}`)
        .join(", ")
      : undefined

    // Add to the group with the formatted field name
    errorGroups[mainField].push({
      field: displayField,
      message,
      details: details || (typeof error.message === "string" && error.message !== message ? error.message : undefined),
    })
  })

  // Second pass - handle general errors without fields
  // Only add to "form" group if we don't have field-specific errors or if they contain unique information
  const fieldlessErrors = errors.filter(error => !error.field)

  if (fieldlessErrors.length > 0) {
    // Look for errors with actual information
    const uniqueErrorMessages = new Set<string>()
    const formErrors: { field: string, message: string, details?: string }[] = []

    fieldlessErrors.forEach((error) => {
      // Extract as much information as possible
      const errorObj = error as unknown as Record<string, any>
      let message = ""
      const details: string[] = []

      // Get message
      if (typeof error.message === "string" && error.message.trim()) {
        message = error.message.trim()
        uniqueErrorMessages.add(message)
      }

      // Check for validation type/code
      if (errorObj.type) {
        details.push(`Error type: ${errorObj.type}`)
      }
      if (errorObj.code) {
        details.push(`Error code: ${errorObj.code}`)
      }

      // Check for any other properties that might contain useful information
      Object.entries(errorObj)
        .filter(([key]) => !["field", "message", "type", "code"].includes(key) && errorObj[key] !== undefined)
        .forEach(([key, value]) => {
          const formattedValue = typeof value === "object"
            ? JSON.stringify(value)
            : String(value)

          if (formattedValue && formattedValue.trim()) {
            details.push(`${formatFieldName(key)}: ${formattedValue}`)
          }
        })

      // If we have no message but have details, use the first detail as the message
      if (!message && details.length > 0) {
        message = details.shift() || "Validation error"
        uniqueErrorMessages.add(message)
      }

      // Default message if we still have nothing
      if (!message) {
        message = "Please check your input for errors"
        uniqueErrorMessages.add(message)
      }

      formErrors.push({
        field: "form",
        message,
        details: details.length > 0 ? details.join(", ") : undefined,
      })
    })

    // Only add form errors if there are no field-specific errors or if they provide unique information
    const hasFieldErrors = Object.keys(errorGroups).length > 0
    if (!hasFieldErrors || uniqueErrorMessages.size > 0) {
      if (!errorGroups.form) {
        errorGroups.form = []
      }

      errorGroups.form.push(...formErrors)
    }
  }

  return formatErrorOutput(errorGroups)
}
