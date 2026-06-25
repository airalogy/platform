import type { ChatModel } from "@airalogy/shared/enum/chat"
import type { ValidationError } from "./types"
import { generateTempId } from "../utils/useChatMessageNavigation"

/**
 * Formats API error messages for display to the user
 * Handles both simple error messages and complex FastAPI validation errors
 */
export function formatErrorMessage(error: any): string {
  // Handle FastAPI validation errors which come as an array
  if (Array.isArray(error?.response?.data?.detail)) {
    const validationErrors = error.response.data.detail as ValidationError[]

    // Format validation errors in a readable way
    return validationErrors.map((err: ValidationError) => {
      // Extract the field name from location path (usually the last element)
      const fieldName = err.loc && err.loc.length > 0 ? err.loc[err.loc.length - 1] : "unknown field"

      // Format message
      return `${fieldName}: ${err.msg}`
    }).join("\n")
  }
  // Fallback to simple error messages
  return error?.response?.data?.detail ?? error?.message ?? "Something went wrong"
}

/**
 * Create standard user message
 */
export function createUserMessage(text: string, parentIndex?: number | null, baseMessage?: Partial<Chat.ChatMessage>): Chat.ChatMessage {
  return {
    dateTime: Date.now(),
    text,
    inversion: true,
    error: false,
    loading: false,
    conversationOptions: null,
    requestOptions: { prompt: text, options: null },
    originalIndex: generateTempId(), // Use temporary ID for new messages
    parentIndex: parentIndex || null,
    childIndices: [],
    currentChildIndex: 0,
    errorMessage: undefined,
    cancelled: false,
    resent: false,
    regenerate: false,
    ...baseMessage,
  }
}

/**
 * Create standard thinking message
 */
export function createThinkingMessage(prompt: string, model?: ChatModel, parentIndex?: number | null): Chat.ChatMessage {
  return {
    dateTime: Date.now(),
    text: "",
    loading: true,
    inversion: false,
    error: false,
    conversationOptions: null,
    requestOptions: { prompt, options: { model } },
    originalIndex: generateTempId(), // Use temporary ID for new messages
    parentIndex: parentIndex || null,
    childIndices: [],
    currentChildIndex: 0,
  }
}
