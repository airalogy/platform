import type { ChatProviderContext } from "../providers/useChatProvider"
import type { ChatEvent } from "../utils/api"
import type { ChatState, ChatStream, ChatStreamProcessorParams } from "./types"
import { fieldEventKey } from "@airalogy/shared/constants"
import { useEventBus } from "@vueuse/core"
import { formatChatErrorMessage } from "./utils"

export function useChatStream(state: ChatState, scrollToBottom: () => Promise<void>, postToolResultChat: ChatProviderContext["postToolResultChat"], provider: ChatProviderContext): ChatStream {
  const { chatStore, startLoading, endLoading } = state
  const { protocolId } = provider
  const fieldEventBus = useEventBus<string>(fieldEventKey)

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

  // Handler for tool call events
  async function handleToolCallEvent(
    toolCallMessage: any,
    chat: Chat.ChatSession,
    messageIndex: number,
    responseData: { id?: string, chatId?: string, conversationId?: string, messages?: any[] },
    content: string,
    requestOptions?: Chat.RequestOptions,
  ) {
    if (!toolCallMessage?.tool_calls) {
      return
    }

    try {
      const toolCallId = toolCallMessage.tool_calls[0].id!

      const resultPromise = await Promise.allSettled(
        toolCallMessage.tool_calls
          .map((call: any) => {
            const { function: { name } = { name: "" }, id, type, arguments: payloadStr } = call

            // Currently only handle slot_filling tool calls
            if (!(name === "slot_filling" && payloadStr)) {
              console.warn(`Unsupported tool call: ${name}`)
              return null
            }

            try {
              const payload = JSON.parse(payloadStr) as {
                operations: {
                  operation: "update"
                  rf_name: string
                  rf_value: any
                }[]
              }

              if (Array.isArray(payload.operations)) {
                return payload.operations
                  .map((action) => {
                    if (action.operation === "update") {
                      return new Promise((resolve, reject) =>
                        fieldEventBus.emit("operation-form-field-update", {
                          action,
                          id,
                          type,
                          resolve,
                          reject,
                        }),
                      )
                    }
                    console.warn(`Unsupported operation: ${action.operation}`)
                    return null
                  })
                  .filter(Boolean)
                  .flat()
              }

              return null
            }
            catch (parseError) {
              console.error("Error parsing tool call payload:", parseError)
              return null
            }
          })
          .filter(Boolean)
          .flat(),
      )

      const fn = toValue(postToolResultChat)
      if (!fn) {
        console.error("Function postToolResultChat not implement")
        return
      }

      const res = await fn({
        protocolId: protocolId.value,
        content: JSON.stringify({
          operation_results: resultPromise
            .map((result: any) => {
              if (result.status === "fulfilled")
                return result.value
              if (result.status === "rejected") {
                console.error("Tool operation failed:", result.reason)
                return result.reason
              }
              return null
            })
            .filter(Boolean),
        }),
        chatId: responseData.id,
        toolCallId,
        type: state.selectedRole.value,
      })

      if (res && state.session.value) {
        chatStore.updateMessage(chat, messageIndex, {
          dateTime: Date.now(),
          text: res.messages[res.messages.length - 1].content!,
          inversion: false,
          error: false,
          loading: false,
          conversationOptions: {
            conversationId: responseData.conversationId,
            parentMessageId: responseData.id,
          },
          // requestOptions: { prompt: content, options: requestOptions?.options || null },
        })
      }
    }
    catch (error) {
      console.error("Tool call processing error:", error)
      // Reuse existing error handling
      await handleErrorEvent({ data: error, type: "error" }, chat, messageIndex, content, requestOptions)
    }
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
          await handleToolCallEvent(lastItem, chat, messageIndex, responseData, content, requestOptions)
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
