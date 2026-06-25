import type { ChatModel } from "@airalogy/shared/enum"
import type { ChatContext } from "./message"
import { fetchEventSource } from "@airalogy/shared/utils/request"
import { chatModelToConfig, createUserMessage } from "./message"

// Define DefaultRetryInterval for fetchEventSource retries
const DefaultRetryInterval = 1000

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
  let rejectNextEvent: ((error: Error) => void) | null = null

  // Function to process the event queue
  function processQueue() {
    if (resolveNextEvent && eventQueue.length > 0) {
      const event = eventQueue.shift()!
      resolveNextEvent(event)
      resolveNextEvent = null
      rejectNextEvent = null
    }
  }

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
    onmessage: (event) => {
      const { data: eventData } = event
      // Skip empty events
      if (!eventData)
        return

      // Check for the end of the stream
      if (eventData === "[DONE]") {
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
          const chatEvent: ChatEvent = {
            type: "error",
            data,
          }
          eventQueue.push({
            done: false,
            value: chatEvent,
          })
        }
        processQueue()
      }
      catch (e) {
        console.error("Error parsing SSE message:", e)
        if (rejectNextEvent) {
          rejectNextEvent(e instanceof Error ? e : new Error(String(e)))
          rejectNextEvent = null
        }
      }
    },
    onerror: (err) => {
      if (rejectNextEvent) {
        rejectNextEvent(err instanceof Error ? err : new Error(String(err)))
        rejectNextEvent = null
      }

      // Return retry interval (default behavior) or throw to stop
      if (err instanceof Error && err.name === "AbortError") {
        throw err // Don't retry on aborts
      }
      const message = err instanceof Error ? err.message : String(err)
      const nonRetryStatusList = ["400", "401", "403", "404", "422"]
      const shouldStopRetry = nonRetryStatusList.some(status =>
        message.includes(`status ${status}`),
      )
      if (shouldStopRetry) {
        throw err
      }
      return DefaultRetryInterval
    },
  })

  // Setup a timeout
  const timeoutId = setTimeout(() => {
    controller.abort()
    if (rejectNextEvent) {
      const timeoutError = new Error("Request timed out")

      // Create an error event to be yielded before terminating
      eventQueue.push({
        done: false,
        value: {
          type: "error",
          data: { error: timeoutError, message: "Request timed out after 1 minute" },
        },
      })
      processQueue()

      // Reject the promise with the timeout error
      rejectNextEvent(timeoutError)
      rejectNextEvent = null
    }
  }, 1000 * 60 * 1) // 1 minute timeout

  // Handle fetch promise rejection
  fetchPromise.catch((error) => {
    if (rejectNextEvent) {
      rejectNextEvent(error)
      rejectNextEvent = null
    }
  })

  try {
    // Keep yielding events until done
    while (true) {
      const eventPromise = new Promise<IteratorResult<ChatEvent, ChatResponse>>((resolve, reject) => {
        resolveNextEvent = resolve
        rejectNextEvent = reject
        processQueue() // Process queue in case events arrived before promise was set
      })

      const result = await eventPromise

      if (result.done) {
        // Return the final result
        clearTimeout(timeoutId)
        return result.value
      }

      yield result.value
    }
  }
  finally {
    // Clean up
    clearTimeout(timeoutId)
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
