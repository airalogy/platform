import type { ChatModel } from "@/enum/model"
import type { ChatEvent, ChatResponse } from "@airalogy/components/chat/utils/api"
import { streamRequest } from "@/service/request/stream"
import { chatModelToConfig, createChatContext, createUserMessage } from "@/utils/chat"
import { localStg } from "@/utils/storage"
import { createChatStream } from "@airalogy/components/chat/utils/api"
import { ChatType } from "@airalogy/shared/enum"
import { baseURL, request } from "../request"

export async function postToolResultChat(payload: {
  protocolId?: string | number | null
  content: string
  chatId?: string | null
  toolCallId: string
  type: ChatType
}) {
  if (!payload.protocolId) {
    throw new Error("protocol id is required")
  }

  const { content, protocolId, chatId, toolCallId, type } = payload

  const { data, error } = await streamRequest<Api.Chat.ChatResponse>({
    url: "/chats/normal_chat/message",
    method: "POST",
    data: {
      message: { role: "tool", content },
      protocol_id: protocolId,
      chat_id: chatId,
      tool_call_id: toolCallId,
      type,
    },
    metadata: {
      showError: false,
    },
  })

  if (error) {
    throw error
  }

  if (data) {
    return data
  }

  return null
}

export async function getChatConversation(chatId: string) {
  if (!chatId) {
    throw new Error("chatId is required")
  }

  const { data, error } = await request<Api.Chat.ChatResponse>({
    url: `/chats/${chatId}`,
    method: "GET",
  })

  if (error) {
    throw error
  }

  if (data) {
    return data
  }

  return null
}

export async function getChatHistory(payload: {
  protocol_id: string | number
  type: 1 | 2 | 3 | 4 | 5 | 6
  page?: number
  pageSize?: number
}) {
  const { protocol_id, type, page = 1, pageSize = 10 } = payload

  const { data, error } = await request<Api.Chat.ChatResponse>({
    url: "/chats/",
    method: "GET",
    params: {
      protocol_id,
      type,
      page,
      page_size: pageSize,
    },
  })

  if (error) {
    throw error
  }

  if (data) {
    return data
  }

  return null
}

export async function deleteChatContext(payload: { chatId: string, resourceId: string }) {
  const { chatId, resourceId } = payload
  if (!chatId || !resourceId) {
    throw new Error("chatId and resourceId are required")
  }

  return await request({
    url: `/chats/${chatId}/remove_tool_call`,
    method: "PUT",
    data: {
      content_resource_id: resourceId,
    },
  })
}

export async function stopStream(payload: { chatId: string }) {
  const { chatId } = payload
  if (!chatId) {
    throw new Error("chatId is required")
  }

  const { data, error } = await request({
    url: "/chats/stop_stream",
    method: "POST",
    data: { chat_id: chatId },
    metadata: {
      showError: false,
    },
  })

  if (error) {
    throw error
  }

  return data
}

export async function* regenerateResponse(payload: {
  chatId: string
  protocolId?: string | null
  type?: ChatType
  model?: ChatModel
}): AsyncGenerator<ChatEvent, ChatResponse, unknown> {
  const { chatId, protocolId, type, model } = payload
  if (!chatId) {
    throw new Error("chatId is required")
  }

  const url = `${baseURL}/chats/regenerate`
  const body: Record<string, any> = {
    chat_id: chatId,
    type,
    model_type: model,
  }

  // Only add protocol_id if it's not empty
  if (protocolId) {
    body.protocol_id = protocolId
  }

  return yield * createChatStream(url, body)
}

export async function* continueResponse(payload: {
  chatId: string
  protocolId?: string | null
  type?: ChatType
  model?: ChatModel
}): AsyncGenerator<ChatEvent, ChatResponse, unknown> {
  const { chatId, protocolId, type, model } = payload
  if (!chatId) {
    throw new Error("chatId is required")
  }

  const url = `${baseURL}/chats/continue`
  const body: Record<string, any> = {
    chat_id: chatId,
    type,
    model_type: model,
  }

  // Only add protocol_id if it's not empty
  if (protocolId) {
    body.protocol_id = protocolId
  }

  return yield * createChatStream(url, body)
}

export async function* postNewChat(payload: {
  protocolId?: string | null
  content: string
  chatId?: string | null
  model?: ChatModel
  type?: ChatType
  file?: File
}) {
  const url = `${baseURL}/chats/`
  const formData = new FormData()

  // Add basic parameters
  formData.append("content", payload.content)
  formData.append("type", String(payload.type || ChatType.NORMAL))

  if (payload.protocolId) {
    formData.append("protocol_id", String(payload.protocolId))
  }

  if (payload.chatId) {
    formData.append("chat_id", payload.chatId)
  }

  if (payload.model) {
    formData.append("model", String(payload.model))
  }

  if (payload.file) {
    formData.append("file", payload.file)
  }

  // Create response structure
  const responseData: ChatResponse = {
    conversation: [],
    messages: [],
  }

  // Create controller for abort functionality
  const controller = new AbortController()

  try {
    const token = localStg.get("token")
    const response = await streamRequest({
      url,
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
  protocolIds?: string[]
  recordIds?: string[]
  attachments?: {
    type: string
    payload: any
  }[]
  type?: ChatType
  discussionIds?: string[]
  documentIds?: string[]
  model?: ChatModel
  enableDiscussion?: boolean
  endpoint?: string
}): AsyncGenerator<ChatEvent, ChatResponse, unknown> {
  const { content, protocolId, chatId, protocolIds, recordIds, model, enableDiscussion, discussionIds, documentIds, type } = payload

  // Determine which endpoint to use based on ChatType
  let apiEndpoint = "qa"
  if (payload.endpoint === "hub") {
    apiEndpoint = "hub"
  }

  const context = createChatContext({
    protocolIds: { ids: protocolIds ?? [], enabled: true },
    recordIds: { ids: recordIds ?? [], enabled: true },
    discussionIds: { ids: discussionIds, enabled: enableDiscussion ?? true, scope: "protocol" },
    documentIds: { ids: documentIds ?? [], enabled: true },
  })

  const url = `${baseURL}/chats/${apiEndpoint}/message`
  const body: Record<string, any> = {
    message: createUserMessage(content),
    context,
    chat_id: chatId,
    model: chatModelToConfig(model, {
      enableThinking: false,
      enableSearch: false,
    }),
  }

  // Only non-hub endpoints require protocol_id, and only if it's not empty
  if (apiEndpoint !== "hub" && protocolId) {
    body.protocol_id = protocolId
  }

  return yield * createChatStream(url, body)
}
