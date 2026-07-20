import type { ChatModel } from "@airalogy/shared/enum/chat"
import type { ChatStreamErrorData } from "../utils/api"
import type { ValidationError } from "./types"
import { $t } from "@airalogy/shared/locales"
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

const chatErrorMessageKeys: Record<string, Parameters<typeof $t>[0]> = {
  CONNECTION_TIMEOUT: "chat.errors.connectionTimeout",
  MODEL_START_TIMEOUT: "chat.errors.modelStartTimeout",
  STREAM_IDLE_TIMEOUT: "chat.errors.streamIdleTimeout",
  STREAM_INTERRUPTED: "chat.errors.streamInterrupted",
  NETWORK_ERROR: "chat.errors.networkError",
  AUTHENTICATION_FAILED: "chat.errors.authenticationFailed",
  RATE_LIMITED: "chat.errors.rateLimited",
  REQUEST_REJECTED: "chat.errors.requestRejected",
  SERVER_ERROR: "chat.errors.serverError",
  INVALID_STREAM_RESPONSE: "chat.errors.invalidStreamResponse",
  MODEL_TIMEOUT: "chat.errors.modelTimeout",
  MODEL_UNAVAILABLE: "chat.errors.modelUnavailable",
  MODEL_AUTHENTICATION_FAILED: "chat.errors.modelAuthenticationFailed",
  MODEL_RATE_LIMITED: "chat.errors.modelRateLimited",
  MODEL_REQUEST_REJECTED: "chat.errors.modelRequestRejected",
  MODEL_UPSTREAM_ERROR: "chat.errors.modelUpstreamError",
  MODEL_STREAM_ERROR: "chat.errors.modelStreamError",
}

function getChatErrorStageLabel(stage: ChatStreamErrorData["stage"]): string {
  const stageKeys: Record<ChatStreamErrorData["stage"], Parameters<typeof $t>[0]> = {
    connection: "chat.errors.stages.connection",
    request: "chat.errors.stages.request",
    model: "chat.errors.stages.model",
    stream: "chat.errors.stages.stream",
  }
  return $t(stageKeys[stage])
}

export function formatChatErrorMessage(value: any): string {
  const data = value?.data?.code ? value.data : value
  if (!data?.code || !data?.stage) {
    return data?.message || formatErrorMessage(data?.error ?? data)
  }

  const errorData = data as ChatStreamErrorData
  const messageKey = chatErrorMessageKeys[errorData.code]
  const summary = messageKey
    ? $t(messageKey, { seconds: errorData.timeout_seconds ?? 60 })
    : errorData.message || $t("chat.errors.unknown")
  const details = [
    $t("chat.errors.stage", { stage: getChatErrorStageLabel(errorData.stage) }),
    $t("chat.errors.errorCode", { code: errorData.code }),
  ]

  if (errorData.model) {
    details.push($t("chat.errors.model", { model: errorData.model }))
  }
  if (errorData.http_status) {
    details.push($t("chat.errors.httpStatus", { status: errorData.http_status }))
  }
  if (errorData.request_id) {
    details.push($t("chat.errors.requestId", { id: errorData.request_id }))
  }
  else if (errorData.chat_id) {
    details.push($t("chat.errors.chatId", { id: errorData.chat_id }))
  }
  if (errorData.retryable) {
    details.push($t("chat.errors.retryHint"))
  }

  if (import.meta.env.DEV && errorData.debug) {
    const debugDetail = [errorData.debug.exception, errorData.debug.detail].filter(Boolean).join(": ")
    if (debugDetail) {
      details.push($t("chat.errors.debug", { detail: debugDetail }))
    }
  }

  return [summary, ...details].join("\n")
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
