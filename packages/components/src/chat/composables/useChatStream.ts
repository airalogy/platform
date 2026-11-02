import type { ChatEvent } from "../utils/api"
import type { ChatState, ChatStream, ChatStreamProcessorParams } from "./types"
import { $t } from "@airalogy/shared/locales"
import { formatChatErrorMessage } from "./utils"

export function useChatStream(state: ChatState, scrollToBottom: () => Promise<void>): ChatStream {
  const { chatStore, startLoading, endLoading } = state

  // Handler for meta events
  async function handleMetaEvent(
    event: ChatEvent,
    responseData: { id?: string, chatId?: string, conversationId?: string, messages?: any[] },
    chat: Chat.ChatSession,
  ) {
    const { data } = event

    if (data.chat_id) {
      responseData.chatId = data.chat_id
      responseData.id = data.chat_id

      // Replace both session and history chat ID with server ID
      const result = chatStore.replaceUUIDWithServerId(chat.uuid, data.chat_id)
      if (result) {
        // Update the chat reference to the updated session
        Object.assign(chat, result.session)
      }
    }
  }

  // Handler for error events
  async function handleErrorEvent(
    event: ChatEvent,
    chat: Chat.ChatSession,
    messageIndex: number,
    content: string,
    requestOptions?: Chat.RequestOptions,
  ) {
    const { data } = event

    if (!data) {
      return
    }

    // Handle error events - Update user message with error status
    const errorMessage = formatChatErrorMessage(data)

    // Update user message (messageIndex - 1) with error status
    if (messageIndex > 0) {
      chatStore.updateMessage(chat!, messageIndex - 1, {
        error: true,
        loading: false,
        errorMessage,
      })
    }

    // Flag assistant message as cancelled/failed instead of showing error
    chatStore.updateMessage(chat!, messageIndex, {
      dateTime: Date.now(),
      text: "",
      inversion: false,
      error: true,
      loading: false,
      cancelled: true, // Flag as cancelled/failed
      conversationOptions: null,
      // requestOptions: { prompt: content, options: requestOptions?.options || null },
    })
  }

  // Handler for message events
  async function handleMessageEvent(
    event: ChatEvent,
    chat: Chat.ChatSession,
    messageIndex: number,
    responseData: { id?: string, chatId?: string, conversationId?: string, messages?: any[] },
    requestOptions?: Chat.RequestOptions,
  ) {
    const { data, done } = event

    let toolCallMessage: any = null
    let message: any = null
    if (data.message) {
      // Handle message events
      const { message: eventMessage, terminated = false } = data

      // If we have a tool call message, save it
      if (eventMessage.tool_calls || eventMessage.role === "tool") {
        toolCallMessage = eventMessage
      }

      message = eventMessage
      // Store all messages for final processing
      responseData.messages = event.data.allMessages || []

      // Live update the UI with the current message content if it's an assistant message
      if (eventMessage.role === "assistant" && eventMessage.content && state.session.value) {
        chatStore.updateMessage(chat!, messageIndex, {
          dateTime: Date.now(),
          text: eventMessage.content,
          inversion: false,
          error: false,
          loading: true,
          cancelled: terminated,
          tool: toolCallMessage || null,
          conversationOptions: responseData.id
            ? {
                conversationId: responseData.conversationId,
                parentMessageId: responseData.id,
              }
            : null,
          // requestOptions: { prompt: eventMessage, options: requestOptions?.options || null },
        })
      }

      // Add handling for "done" type events in processChatStream
      if (done && state.session.value) {
        chatStore.updateMessage(chat!, messageIndex, {
          loading: false,
        })
      }
    }
    return { message, toolCallMessage }
  }

  // Handler for successful message responses
  async function handleMessageResponse(
    message: any,
    chat: Chat.ChatSession,
    messageIndex: number,
    responseData: { id?: string, chatId?: string, conversationId?: string, messages?: any[] },
    content: string,
    lastToolCall: any,
    requestOptions?: Chat.RequestOptions,
  ) {
    if (!message?.content || !state.session.value) {
      return
    }

    chatStore.updateMessage(chat, messageIndex, {
      dateTime: Date.now(),
      text: message.content,
      inversion: false,
      error: false,
      loading: false,
      tool: lastToolCall || null,
      conversationOptions: {
        conversationId: responseData.conversationId,
        parentMessageId: responseData.id,
      },
      // requestOptions: { prompt: content, options: requestOptions?.options || null },
    })
    await scrollToBottom() // Smart scroll for streaming content
  }

  // Handler for empty response cases
  async function handleEmptyResponse(
    message: any,
    chat: Chat.ChatSession,
    messageIndex: number,
    responseData: { id?: string, chatId?: string, conversationId?: string, messages?: any[] },
    content: string,
    requestOptions?: Chat.RequestOptions,
  ) {
    if (message?.content !== "" || message?.tool_calls || !state.session.value) {
      return
    }

    // Update user message with error status for empty response
    if (messageIndex > 0) {
      chatStore.updateMessage(chat, messageIndex - 1, {
        error: true,
        loading: false,
        errorMessage: "Received an empty response from the server",
      })
    }

    // Flag assistant message as cancelled/failed for empty response
    chatStore.updateMessage(chat, messageIndex, {
      dateTime: Date.now(),
      text: "",
      inversion: false,
      error: true,
      loading: false,
      cancelled: true,
      conversationOptions: {
        conversationId: responseData.conversationId,
        parentMessageId: responseData.id,
      },
      // requestOptions: { prompt: content, options: requestOptions?.options || null },
    })
  }

  async function processChatStreamByUUID({
    chatUuid,
    generator,
    content,
    messageIndex,
    requestOptions,
  }: ChatStreamProcessorParams & { chatUuid: string }) {
    const chat = chatStore.findSessionByUUID(chatUuid)
    if (!chat) {
      throw new Error("Chat not found")
    }

    return processChatStream({ chat, generator, content, messageIndex, requestOptions })
  }

  async function processChatStream({
    chat,
    generator,
    content,
    messageIndex,
    requestOptions,
  }: ChatStreamProcessorParams & { chat: Chat.ChatSession }) {
    // Create controller for aborting
    state.controller.value = {
      abort: () => {
        if (generator.return)
          generator.return(null as any)
      },
    }

    if (!chat) {
      throw new Error("Chat not found")
    }

    try {
      startLoading()
      // Create a response data structure
      const responseData: {
        id?: string
        chatId?: string
        conversationId?: string
        messages?: any[]
      } = {}

      // Use refs for mutable state that handlers need to update
      let lastMessage: any = null
      let lastToolCallMessage: any = null
      let streamFailed = false

      // Process events from generator
      try {
        for await (const event of generator) {
          const { type } = event

          // Route events to appropriate handlers
          if (type === "meta") {
            await handleMetaEvent(event, responseData, chat)
          }
          else if (type === "error") {
            await handleErrorEvent(event, chat, messageIndex, content, requestOptions)
            streamFailed = true
            break
          }
          else if (type === "message") {
            const { message, toolCallMessage } = await handleMessageEvent(event, chat, messageIndex, responseData, requestOptions)

            lastMessage = message
            lastToolCallMessage = toolCallMessage
          }

          await scrollToBottom() // Smart scroll during streaming
        }
      }
      finally {
        await scrollToBottom() // Smart scroll after streaming
      }

      if (streamFailed) {
        return responseData
      }

      // When generator completes, final data is available
      // Handle no response case
      if (!responseData.messages?.length) {
        throw new Error("No response data")
      }

      if (!state.session.value) {
        throw new Error("No chat info")
      }

      // Process the last message and tool call
      const lastItem = lastMessage || (responseData.messages && responseData.messages.length > 0
        ? responseData.messages.findLast(msg => msg.role === "assistant" && msg.content !== undefined) || responseData.messages.at(-1)
        : null)

      const lastToolCall = lastToolCallMessage || (responseData.messages && responseData.messages.length > 0
        ? responseData.messages.findLast(msg => msg.tool_calls || msg.role === "tool")
        : null)

      if (lastItem && lastItem.role === "assistant") {
        const { content, tool_calls } = lastItem
        if (content) {
          await handleMessageResponse(lastItem, chat, messageIndex, responseData, content, lastToolCall, requestOptions)
        }
        else if (content === "" && !tool_calls) {
          await handleEmptyResponse(lastItem, chat, messageIndex, responseData, content, requestOptions)
        }
        else if (tool_calls) {
          // Unscoped legacy tool messages may be displayed, but only the active
          // Recorder can apply a response associated with its own live request.
          chatStore.updateMessage(chat, messageIndex, { text: $t("page.recorderAira.openForm"), tool: lastToolCall, loading: false })
        }
      }

      if (state.session.value) {
        chatStore.updateMessage(chat, messageIndex, {
          loading: false,
        })
      }

      return responseData
    }
    catch (error: any) {
      // Use consistent error handling
      await handleErrorEvent({ data: error, type: "error" }, chat, messageIndex, content, requestOptions)

      // Abort any ongoing requests
      if (state.controller.value && state.controller.value.abort) {
        state.controller.value.abort()
        state.controller.value = null
      }

      // Log the error for debugging
      console.error("Chat processing error:", error)

      throw error
    }
    finally {
      await scrollToBottom() // Smart scroll on completion
      endLoading()
    }
  }

  return {
    processChatStream,
    processChatStreamByUUID,
  }
}
