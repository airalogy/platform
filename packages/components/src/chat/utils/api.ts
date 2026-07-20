import type { ChatModel } from "@airalogy/shared/enum"
import type { ChatContext } from "./message"
import { EventStreamContentType, fetchEventSource } from "@airalogy/shared/utils/request"
import { chatModelToConfig, createUserMessage } from "./message"

const ChatStreamIdleTimeoutMs = 60_000

export enum ChatType {
  NORMAL = 1,
  FIELD_INPUT = 2,
  RECORDS = 3,
  VISION = 5,
  STT = 6,
}

export interface ChatResponse {
  chatId?: string
  id?: string
  conversationId?: string
  conversation?: any[]
  messages?: any[]
  [key: string]: any
}

export interface ChatEvent {
  type: "meta" | "message" | "done" | "error"
  data: any
  done?: boolean
}

export type ChatStreamErrorStage = "connection" | "request" | "model" | "stream"

export interface ChatStreamErrorData {
  code: string
  stage: ChatStreamErrorStage
  message?: string
  chat_id?: string
  request_id?: string
  model?: string
  http_status?: number
  timeout_seconds?: number
  retryable?: boolean
  debug?: {
    exception?: string
    detail?: string
  }
}

class ChatStreamError extends Error {
  constructor(public readonly data: ChatStreamErrorData) {
    super(data.message || data.code)
    this.name = "ChatStreamError"
  }
}

interface ChatAttachmentPayload {
  name?: string | null
  type?: string | null
  serverId?: string | null
}

type ChatFileType = "image" | "audio" | "docx" | "pdf" | "text"

function resolveChatFileType(attachment: ChatAttachmentPayload): ChatFileType | null {
  const mimeType = attachment.type?.toLowerCase() || ""
  const extension = attachment.name?.split(".").pop()?.toLowerCase() || ""

  if (mimeType.startsWith("image/")) {
    return "image"
  }

  if (mimeType === "application/pdf" || extension === "pdf") {
    return "pdf"
  }

  if (
    mimeType === "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    || extension === "docx"
  ) {
    return "docx"
  }

  if (mimeType.startsWith("text/") || extension === "txt" || extension === "md") {
    return "text"
  }

  return null
}

function createChatUserMessage(content: string, attachments?: ChatAttachmentPayload[]) {
  const files = attachments?.map((attachment) => {
    if (!attachment.serverId) {
      return null
    }

    const fileType = resolveChatFileType(attachment)
    if (!fileType) {
      return null
    }

    return {
      id: attachment.serverId,
      type: fileType,
      file_name: attachment.name || "attachment",
    }
  }).filter((file): file is { id: string, type: ChatFileType, file_name: string } => file !== null)

  return {
    role: "user" as const,
    content,
    files: files && files.length > 0 ? files : undefined,
  }
}

function parseErrorResponse(rawBody: string): { code?: string, message?: string, requestId?: string } {
  if (!rawBody) {
    return {}
  }

  try {
    const payload = JSON.parse(rawBody)
    const detail = payload?.detail ?? payload
    if (typeof detail === "string") {
      return { message: detail }
    }
    if (detail && typeof detail === "object" && !Array.isArray(detail)) {
      return {
        code: typeof detail.code === "string" ? detail.code : undefined,
        message: typeof detail.message === "string" ? detail.message : undefined,
        requestId: typeof detail.request_id === "string" ? detail.request_id : undefined,
      }
    }
  }
  catch {
    return { message: rawBody }
  }

  return {}
}

function createHttpErrorData(response: Response, rawBody: string): ChatStreamErrorData {
  const parsed = parseErrorResponse(rawBody)
  const requestId = response.headers.get("x-request-id") || parsed.requestId || undefined
  const common = {
    stage: "request" as const,
    request_id: requestId,
    http_status: response.status,
    debug: import.meta.env.DEV
      ? {
          exception: "HTTPError",
          detail: parsed.message || `${response.status} ${response.statusText}`,
        }
      : undefined,
  }

  if (response.status === 401 || response.status === 403) {
    return { ...common, code: "AUTHENTICATION_FAILED", retryable: false }
  }
  if (response.status === 429) {
    return { ...common, code: "RATE_LIMITED", retryable: true }
  }
  if (response.status >= 500) {
    return {
      ...common,
      code: parsed.code === "internal_server_error" ? "SERVER_ERROR" : (parsed.code || "SERVER_ERROR"),
      retryable: true,
    }
  }
  return {
    ...common,
    code: parsed.code || "REQUEST_REJECTED",
    message: parsed.message,
    retryable: false,
  }
}

function normalizeChatStreamError(
  error: unknown,
  context: Partial<Pick<ChatStreamErrorData, "chat_id" | "request_id" | "model">>,
): ChatStreamErrorData {
  if (error instanceof ChatStreamError) {
    return { ...context, ...error.data }
  }

  const exception = error instanceof Error ? error.name : "UnknownError"
  const detail = error instanceof Error ? error.message : String(error)
  return {
    code: "NETWORK_ERROR",
    stage: "connection",
    retryable: true,
    ...context,
    debug: import.meta.env.DEV ? { exception, detail } : undefined,
  }
}

/**
 * Common function to create a streaming chat request
 */
export async function* createChatStream(url: string, body: Record<string, any>, token?: string): AsyncGenerator<ChatEvent, ChatResponse, unknown> {
  // Create response structure
  const responseData: ChatResponse = {
    conversation: [],
    messages: [],
  }

  // Create controller for abort functionality
  const controller = new AbortController()

  // Message content to accumulate the streamed content
  const messageMap = new Map<number, any>()

  // Queue for incoming events to avoid race conditions
  const eventQueue: IteratorResult<ChatEvent, ChatResponse>[] = []
  let resolveNextEvent: ((value: IteratorResult<ChatEvent, ChatResponse>) => void) | null = null
  let responseOpened = false
  let modelOutputStarted = false
  let streamCompleted = false
  let terminalErrorQueued = false
  let requestId: string | undefined
  let modelName: string | undefined
  let timeoutId: ReturnType<typeof setTimeout> | undefined

  // Function to process the event queue
  function processQueue() {
    if (resolveNextEvent && eventQueue.length > 0) {
      const event = eventQueue.shift()!
      resolveNextEvent(event)
      resolveNextEvent = null
    }
  }

  function clearStreamTimeout() {
    if (timeoutId !== undefined) {
      clearTimeout(timeoutId)
      timeoutId = undefined
    }
  }

  function queueTerminalError(data: ChatStreamErrorData) {
    if (terminalErrorQueued || streamCompleted) {
      return
    }

    terminalErrorQueued = true
    clearStreamTimeout()
    eventQueue.push({
      done: false,
      value: {
        type: "error",
        data: {
          chat_id: responseData.chatId,
          request_id: requestId,
          model: modelName,
          ...data,
        },
      },
    })
    eventQueue.push({ done: true, value: responseData })
    processQueue()
  }

  function armStreamTimeout() {
    clearStreamTimeout()
    timeoutId = setTimeout(() => {
      const timeoutSeconds = ChatStreamIdleTimeoutMs / 1000
      const data: ChatStreamErrorData = modelOutputStarted
        ? {
            code: "STREAM_IDLE_TIMEOUT",
            stage: "stream",
            timeout_seconds: timeoutSeconds,
            retryable: true,
          }
        : responseOpened
          ? {
              code: "MODEL_START_TIMEOUT",
              stage: "model",
              timeout_seconds: timeoutSeconds,
              retryable: true,
            }
          : {
              code: "CONNECTION_TIMEOUT",
              stage: "connection",
              timeout_seconds: timeoutSeconds,
              retryable: true,
            }

      queueTerminalError(data)
      controller.abort()
    }, ChatStreamIdleTimeoutMs)
  }

  armStreamTimeout()

  // Start fetch request
  const fetchPromise = fetchEventSource(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "text/event-stream",
      "Auth-Token": token || "",
    },
    signal: controller.signal,
    body: JSON.stringify(body, null, 0),
    onopen: async (response) => {
      responseOpened = true
      requestId = response.headers.get("x-request-id") || undefined
      armStreamTimeout()

      if (!response.ok) {
        if (response.status === 401) {
          const handler = (window as any)?.$handleUnauthorized
          if (typeof handler === "function") {
            handler()
          }
        }
        throw new ChatStreamError(createHttpErrorData(response, await response.text()))
      }

      const contentType = response.headers.get("content-type")
      if (!contentType?.startsWith(EventStreamContentType)) {
        throw new ChatStreamError({
          code: "INVALID_STREAM_RESPONSE",
          stage: "connection",
          request_id: requestId,
          http_status: response.status,
          retryable: false,
          debug: import.meta.env.DEV
            ? {
                exception: "InvalidContentType",
                detail: `Expected ${EventStreamContentType}, received ${contentType || "no content type"}`,
              }
            : undefined,
        })
      }
    },
    onmessage: (event) => {
      const { data: eventData } = event
      // Skip empty events
      if (!eventData)
        return

      // Check for the end of the stream
      if (eventData === "[DONE]") {
        streamCompleted = true
        clearStreamTimeout()
        eventQueue.push({
          done: true,
          value: responseData,
        })
        processQueue()
        return
      }

      try {
        const { type, data } = JSON.parse(eventData) || {}

        // Handle meta events
        if (type === "meta" && data.chat_id) {
          responseData.chatId = data.chat_id
          responseData.id = data.chat_id
          modelName = typeof data.model === "string" ? data.model : modelName

          const chatEvent: ChatEvent = {
            type: "meta",
            data,
          }
          eventQueue.push({
            done: false,
            value: chatEvent,
          })
        }

        // Handle message events
        if (type === "message" && data) {
          const { index, message } = data
          const priorMessage = messageMap.get(index)

          if (
            (message?.role === "assistant" || priorMessage?.role === "assistant")
            && typeof message.content === "string"
            && message.content.length > 0
          ) {
            modelOutputStarted = true
            armStreamTimeout()
          }

          // Initialize this message in the map if it doesn't exist
          if (!messageMap.has(index)) {
            messageMap.set(index, { ...message })
          }
          else {
            // Update existing message
            const existingMessage = messageMap.get(index)

            // For content updates, we append the content
            if (message.content !== undefined) {
              existingMessage.content = (existingMessage.content || "") + (message.content || "")
            }

            // For tool calls or other properties, we update them
            if (message.tool_calls) {
              existingMessage.tool_calls = message.tool_calls
            }

            if (message.tool_call_id) {
              existingMessage.tool_call_id = message.tool_call_id
            }

            if (message.role) {
              existingMessage.role = message.role
            }

            messageMap.set(index, existingMessage)
          }

          // Update response data with messages
          responseData.conversation = Array.from(messageMap.values())
          responseData.messages = Array.from(messageMap.values())

          const chatEvent: ChatEvent = {
            type: "message",
            data: {
              index,
              message: messageMap.get(index),
              allMessages: responseData.messages,
            },
          }
          eventQueue.push({
            done: false,
            value: chatEvent,
          })
        }
        if (type === "error" && data) {
          queueTerminalError(data)
          controller.abort()
          return
        }
        processQueue()
      }
      catch (e) {
        console.error("Error parsing SSE message:", e)
        throw new ChatStreamError({
          code: "INVALID_STREAM_RESPONSE",
          stage: "stream",
          retryable: false,
          debug: import.meta.env.DEV
            ? {
                exception: e instanceof Error ? e.name : "ParseError",
                detail: e instanceof Error ? e.message : String(e),
              }
            : undefined,
        })
      }
    },
    onclose: () => {
      if (!streamCompleted && !terminalErrorQueued) {
        throw new ChatStreamError({
          code: "STREAM_INTERRUPTED",
          stage: modelOutputStarted ? "stream" : "model",
          retryable: true,
        })
      }
    },
    onerror: (err) => {
      if (err instanceof Error && err.name === "AbortError") {
        throw err
      }
      // Retrying a POST stream can invoke the model twice. Let the user retry explicitly.
      throw err
    },
  })

  // Handle fetch promise rejection
  fetchPromise.catch((error) => {
    queueTerminalError(normalizeChatStreamError(error, {
      chat_id: responseData.chatId,
      request_id: requestId,
      model: modelName,
    }))
  })

  try {
    // Keep yielding events until done
    while (true) {
      const eventPromise = new Promise<IteratorResult<ChatEvent, ChatResponse>>((resolve) => {
        resolveNextEvent = resolve
        processQueue() // Process queue in case events arrived before promise was set
      })

      const result = await eventPromise

      if (result.done) {
        // Return the final result
        clearStreamTimeout()
        return result.value
      }

      yield result.value
    }
  }
  finally {
    // Clean up
    clearStreamTimeout()
    controller.abort()
  }
}

/**
 * Creates a chat stream that yields events as they arrive
 * @returns An async generator that yields ChatEvent objects
 */
export async function* postStartChat(payload: {
  protocolId?: string | null
  content: string
  attachments?: ChatAttachmentPayload[]
  role?: "user" | "tool"
  chatId?: string | null
  // type?: ChatType
  model?: ChatModel
  endpoint?: string
  token?: string
  context: ChatContext
  enableThinking?: boolean
  enableSearch?: boolean
  hubSearch?: boolean
}): AsyncGenerator<ChatEvent, ChatResponse, unknown> {
  const { content, protocolId, chatId, model, endpoint = "normal_chat", token, context } = payload

  if (payload.endpoint?.includes("normal_chat") && !payload.protocolId) {
    throw new Error("protocol id is required")
  }

  const body: Record<string, any> = {
    message: createChatUserMessage(content, payload.attachments),
    context,
    chat_id: chatId,
    model: chatModelToConfig(model, {
      enableThinking: payload.enableThinking,
      enableSearch: payload.enableSearch,
    }),
    hub_search: payload.hubSearch ?? false,
  }

  // Only non-hub endpoints require protocol_id
  if (!payload.endpoint?.includes("hub") && protocolId) {
    body.protocol_id = protocolId
  }

  return yield * createChatStream(endpoint, body, token)
}

export async function* regenerateResponse(payload: {
  chatId: string
  protocolId?: string | null
  type?: ChatType
  model?: ChatModel
  endpoint?: string
  token?: string
}): AsyncGenerator<ChatEvent, ChatResponse, unknown> {
  const { chatId, protocolId, type, model, endpoint = "normal_chat", token } = payload
  if (!chatId) {
    throw new Error("chatId is required")
  }

  const body: Record<string, any> = {
    chat_id: chatId,
    type,
    model_type: model,
  }

  // Only add protocol_id if it's not empty
  if (protocolId) {
    body.protocol_id = protocolId
  }

  return yield * createChatStream(endpoint, body, token)
}

export async function* continueResponse(payload: {
  chatId: string
  protocolId?: string | null
  type?: ChatType
  model?: ChatModel
  endpoint?: string
  token?: string
}): AsyncGenerator<ChatEvent, ChatResponse, unknown> {
  const { chatId, protocolId, type, model, endpoint = "normal_chat", token } = payload
  if (!chatId) {
    throw new Error("chatId is required")
  }

  const body: Record<string, any> = {
    chat_id: chatId,
    type,
    model_type: model,
  }

  // Only add protocol_id if it's not empty
  if (protocolId) {
    body.protocol_id = protocolId
  }

  return yield * createChatStream(endpoint, body, token)
}

export async function* postNewChat(payload: {
  protocolId?: string | null
  content: string
  chatId?: string | null
  model?: ChatModel
  type?: ChatType
  file?: File
  endpoint?: string
  token?: string
}, streamRequest: (config: any) => Promise<any>) {
  const formData = new FormData()
  const { endpoint, token, type, content, protocolId, chatId, model, file } = payload

  // Add basic parameters
  formData.append("content", content)
  formData.append("type", String(type || ChatType.NORMAL))

  if (protocolId) {
    formData.append("protocol_id", String(protocolId))
  }

  if (chatId) {
    formData.append("chat_id", chatId)
  }

  if (model) {
    formData.append("model", String(model))
  }

  if (file) {
    formData.append("file", file)
  }

  // Create response structure
  const responseData: ChatResponse = {
    conversation: [],
    messages: [],
  }

  // Create controller for abort functionality
  const controller = new AbortController()

  try {
    const response = await streamRequest({
      url: endpoint,
      method: "POST",
      headers: {
        "Auth-Token": token || "",
      },
      data: formData,
      signal: controller.signal,
    })

    // Process the stream
    const reader = response.body?.getReader()
    if (!reader) {
      throw new Error("Failed to get reader from response")
    }

    const decoder = new TextDecoder()
    let buffer = ""

    while (true) {
      const { done, value } = await reader.read()

      if (done) {
        break
      }

      buffer += decoder.decode(value, { stream: true })

      // Process complete events in the buffer
      const events = buffer.split("\n\n")
      buffer = events.pop() || ""

      for (const event of events) {
        if (!event.trim())
          continue

        const lines = event.split("\n")
        const dataLine = lines.find(line => line.startsWith("data: "))

        if (!dataLine)
          continue

        const data = dataLine.slice(6)

        if (data === "[DONE]") {
          yield { type: "done", data: responseData }
          return responseData
        }

        try {
          const parsedData = JSON.parse(data)
          const { type, data: eventData } = parsedData

          if (type === "meta" && eventData.chat_id) {
            responseData.chatId = eventData.chat_id
            responseData.id = eventData.chat_id
            yield { type: "meta", data: eventData }
          }
          else if (type === "message" && eventData) {
            const { message } = eventData
            if (message) {
              responseData.conversation = [...(responseData.conversation || []), message]
              responseData.messages = [...(responseData.messages || []), message]
              yield {
                type: "message",
                data: {
                  message,
                  allMessages: responseData.messages,
                },
              }
            }
          }
          else if (type === "error") {
            yield { type: "error", data: eventData }
          }
        }
        catch (e) {
          console.error("Error parsing SSE message:", e)
        }
      }
    }

    return responseData
  }
  catch (error) {
    console.error("Stream error:", error)
    throw error
  }
}

export async function* createNormalChat(payload: {
  content: string
  protocolId?: string | number
  chatId?: string | null
  attachments?: {
    type: string
    payload: any
  }[]
  type?: ChatType
  model?: ChatModel
  enableDiscussion?: boolean
  endpoint?: string
  token?: string
  context: ChatContext
  enableThinking?: boolean
  enableSearch?: boolean
}): AsyncGenerator<ChatEvent, ChatResponse, unknown> {
  const { content, protocolId, chatId, model, context, endpoint = "normal_chat", type, token } = payload

  if (payload.endpoint === "normal_chat" && !payload.protocolId) {
    throw new Error("protocol id is required")
  }

  const body: Record<string, any> = {
    message: createUserMessage(content),
    context,
    chat_id: chatId,
    model: chatModelToConfig(model, {
      enableThinking: payload.enableThinking,
      enableSearch: payload.enableSearch,
    }),
  }

  // Only non-hub endpoints require protocol_id, and only if it's not empty
  if (!payload.endpoint?.includes("hub") && protocolId) {
    body.protocol_id = protocolId
  }

  return yield * createChatStream(endpoint, body, token)
}
