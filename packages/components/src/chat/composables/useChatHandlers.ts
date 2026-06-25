import type { ChatModel, ChatType } from "@airalogy/shared/enum"
import type { ChatProviderContext } from "../providers/useChatProvider"
import type { ChatContext } from "../utils/message"
import type { ChatAPI, ChatHandlers, ChatMutations, ChatSessionNavigation, ChatState, ChatStream } from "./types"
import { continueResponse, postStartChat } from "@airalogy/components/chat/utils/api"
import { useClosableMessage } from "@airalogy/composables"
import { useDialog } from "naive-ui"
import { nanoid } from "nanoid"
import { nextTick, toValue } from "vue"
import { updateSessionHierarchy } from "../utils/useChatMessageNavigation"
import { createUserMessage } from "./utils"

interface UseChatHandlersParams {
  state: ChatState
  mutations: ChatMutations
  stream: ChatStream
  scrollToBottom: (isBottom?: boolean) => Promise<void>
  navigation: ChatSessionNavigation
  api: ChatAPI
  provider: ChatProviderContext
}

export function useChatHandlers({ state, mutations, stream, scrollToBottom, navigation, api, provider }: UseChatHandlersParams): ChatHandlers {
  const dialog = useDialog()
  const showMessage = useClosableMessage()
  const { updateContext, handleDraftMessage } = mutations
  const { protocolId, createChatContext } = provider

  const { chatStore, chatId, session, emptyDraftId, isEmptyDraft, controller, selectedModel, loading, selectedRole, context, attachments, audioBase64, enableThinking, enableSearch, enableHubSearch } = state

  const { stopStream, endpoint, token } = api

  const { createBranch, switchBranch, deleteMessageWithHierarchy } = navigation

  /**
   * Validate chat operation prerequisites
   */
  function validateChatOperation(requireChat: boolean = true): boolean {
    if (loading.value) {
      return false
    }

    if (requireChat) {
      const currSession = toValue(session)
      if (!currSession) {
        showMessage.error("No chat")
        return false
      }
    }

    return true
  }

  /**
   * Create standard chat generator with common parameters
   */
  function createChatGenerator(params: {
    content: string
    model?: ChatModel
    attachments?: Chat.Attachment[]
    chatId?: string
  }) {
    const existingServerId = chatStore.getServerIdByUUID(chatId.value!)
    const { content, model, attachments } = params
    const injectContext = (toValue(createChatContext)?.(context.value) || {}) as ChatContext

    return postStartChat({
      chatId: params.chatId || existingServerId,
      protocolId: toValue(protocolId),
      content,
      // type,
      model: model || selectedModel.value,
      endpoint: endpoint.value,
      context: injectContext,
      attachments,
      token: token?.value,
      enableThinking: enableThinking.value,
      enableSearch: enableSearch.value,
      hubSearch: enableHubSearch.value,
    })
  }

  /**
   * Process chat stream with error handling
   */
  async function processStreamSafely(params: {
    chat: Chat.ChatSession
    generator: any
    content: string
    messageIndex: number
    requestOptions: any
  }) {
    try {
      await stream.processChatStream(params)
    }
    catch (error) {
      console.error("Stream processing error:", error)
      throw error
    }
  }

  /**
   * Update context and make items non-removable
   */
  function updateContextAfterRequest() {
    if (!context.value) {
      return
    }

    updateContext(context.value.map((item: Chat.ChatContext) =>
      ({ ...item, removable: false })))
  }

  // Helper function to update message hierarchy after operations
  function updateMessageHierarchy() {
    const currentSession = toValue(session)
    if (currentSession && currentSession.data.length > 0) {
      updateSessionHierarchy(chatStore, currentSession.uuid, currentSession.data)
    }
  }
  async function handleCreateBranch(branchMessage: Chat.ChatMessage, parentIndex: number | null = null, isBottom?: boolean) {
    const currentSession = toValue(session)
    if (!validateChatOperation() || !currentSession)
      return

    const { text, originalIndex } = branchMessage
    if (!text) {
      showMessage.error("Invalid message text")
      return
    }

    if (branchMessage.attachments?.some((item: Chat.Attachment) => item.isUploading || !item.serverId)) {
      showMessage.error("Please wait for file upload to finish")
      return
    }

    // Create the branch
    const thinkingMessageIndex = createBranch(currentSession, parentIndex ?? originalIndex, text, branchMessage.attachments)
    if (thinkingMessageIndex === null) {
      showMessage.error("Failed to create branch")
      return
    }

    updateMessageHierarchy()
    await scrollToBottom() // Force scroll when user sends new message

    try {
      const generator = createChatGenerator({
        content: text,
        attachments: branchMessage.attachments,
      })

      await processStreamSafely({
        chat: currentSession,
        generator,
        content: text,
        messageIndex: thinkingMessageIndex,
        requestOptions: { prompt: text, options: { model: selectedModel.value } },
      })

      updateMessageHierarchy()
    }
    catch (error) {
      console.error("Branch creation error:", error)
    }
  }

  async function handleSwitchBranch(branchMessage: Chat.ChatMessage, targetBranchIndex: number = 0) {
    const currentSession = toValue(session)
    if (!currentSession) {
      showMessage.error("No chat session")
      return
    }

    const success = switchBranch(currentSession, branchMessage.originalIndex, targetBranchIndex)
    if (!success) {
      showMessage.error("Failed to switch branch")
      return
    }

    updateMessageHierarchy()
    await nextTick()
    await scrollToBottom() // Force scroll when switching branch (user action)
  }

  async function handleSubmit(message: string, role?: ChatType, model?: ChatModel, parentIndex: number | null = null) {
    if (!validateChatOperation(false) || (message && message.trim() === "")) {
      return
    }

    const uuid = chatId.value || emptyDraftId.value || nanoid()
    const draftAttachments = attachments.value?.length
      ? attachments.value.map((item: Chat.Attachment) => ({ ...item }))
      : []

    if (draftAttachments.some((item: Chat.Attachment) => item.isUploading || !item.serverId)) {
      showMessage.error("Please wait for file upload to finish")
      return
    }

    const chatMessageItem = createUserMessage(message, parentIndex, {
      attachments: draftAttachments.length > 0 ? draftAttachments : undefined,
    })

    // For empty drafts, we need to create the session first without adding the user message
    // The user message will be added by handleCreateBranch
    handleDraftMessage(uuid)
    chatStore.updateChatRole(uuid, selectedRole.value)

    await nextTick()

    if (!session.value) {
      chatStore.setActive(uuid)
      await nextTick()
    }

    const currentSession = toValue(session)
    if (!currentSession) {
      showMessage.error("No active session")
      return
    }

    // Get the last message index as the branch point (0 for empty sessions)
    const lastMessageIndex = currentSession.data.length > 0 ? currentSession.data.length - 1 : 0

    // Create branch message object for handleCreateBranch
    const branchMessage: Chat.ChatMessage = {
      ...chatMessageItem,
      text: message,
      originalIndex: lastMessageIndex,
      attachments: chatMessageItem.attachments || [],
      requestOptions: { prompt: message, options: { model: model || selectedModel.value } },
    }

    try {
      updateContextAfterRequest()
      await handleCreateBranch(branchMessage)

      if (isEmptyDraft.value) {
        emptyDraftId.value = nanoid()
      }
      audioBase64.value = null
    }
    catch (error) {
      console.error("Submit error:", error)
    }
  }

  async function handleRegenerate(branchMessage: Chat.ChatMessage) {
    const currentSession = toValue(session)
    if (!validateChatOperation() || !currentSession)
      return

    const { requestOptions, originalIndex } = branchMessage
    const userMessageContent = requestOptions?.prompt ?? ""

    if (!userMessageContent) {
      showMessage.error("No message to regenerate")
      return
    }

    // Create branch message object for handleCreateBranch
    const regenerateBranchMessage: Chat.ChatMessage = {
      ...branchMessage,
      regenerate: true,
      text: userMessageContent,
      requestOptions: { prompt: userMessageContent, options: requestOptions?.options },
    }

    try {
      await handleCreateBranch(regenerateBranchMessage, originalIndex)
    }
    catch (error) {
      console.error("Regeneration error:", error)
    }
  }

  async function handleContinue(branchMessage: Chat.ChatMessage) {
    const currentSession = toValue(session)
    if (!validateChatOperation() || !currentSession)
      return

    const { originalIndex, requestOptions } = branchMessage
    const prompt = requestOptions?.prompt ?? ""

    if (!prompt) {
      showMessage.error("No message to continue")
      return
    }

    // Update message to show continuing state
    chatStore.updateMessageByUUID(currentSession.uuid, originalIndex, {
      dateTime: Date.now(),
      text: branchMessage.text,
      loading: true,
      error: false,
      conversationOptions: branchMessage.conversationOptions,
      requestOptions: { prompt, options: requestOptions?.options },
    })

    const { serverId } = currentSession
    if (!serverId) {
      showMessage.error("Cannot continue - missing server chat ID")
      return
    }

    try {
      const generator = continueResponse({
        chatId: serverId,
        protocolId: toValue(protocolId),
        type: selectedRole.value,
        model: selectedModel.value,
        endpoint: endpoint.value,
        token: token?.value,
      })

      await processStreamSafely({
        chat: currentSession,
        generator,
        content: prompt,
        messageIndex: originalIndex,
        requestOptions,
      })
    }
    catch (error) {
      console.error("Continue response error:", error)
    }
  }

  function handleClear() {
    const currentSession = toValue(session)
    if (!currentSession) {
      showMessage.error("No chat")
      return
    }

    dialog.warning({
      title: "Clear Chat",
      content: "Are you sure you want to clear the chat history?",
      positiveText: "Yes",
      negativeText: "No",
      onPositiveClick: () => {
        chatStore.clearSessionDataByUUID(currentSession.uuid)
      },
    })
  }

  function handleStop() {
    const currentSession = toValue(session)
    if (!currentSession) {
      showMessage.error("No chat")
      return
    }

    const { serverId, data } = currentSession

    if (loading.value && controller.value && controller.value.abort) {
      controller.value.abort()
      loading.value = false

      // Update the last message to show the request was stopped
      if (data) {
        const lastIndex = data.length - 1
        chatStore.updateMessage(currentSession, lastIndex, {
          loading: false,
          errorMessage: "Message generation stopped.",
        })
      }

      // Call API to stop stream
      if (serverId && stopStream) {
        stopStream({ chatId: serverId }).catch((error: any) => {
          console.error("Error stopping stream:", error)
        })
      }
    }
  }

  function handleDeleteMessage(branchMessage: Chat.ChatMessage) {
    const currentSession = toValue(session)
    if (!validateChatOperation() || !currentSession)
      return

    dialog.warning({
      title: "Delete Message",
      content: "Are you sure you want to delete this message?",
      positiveText: "Yes",
      negativeText: "No",
      onPositiveClick: () => {
        deleteMessageWithHierarchy(currentSession, branchMessage.originalIndex)
      },
    })
  }

  function handleAddNewSession(targetUuid?: string) {
    chatStore.clearActive()
    const newUuid = targetUuid || emptyDraftId.value
    if (newUuid) {
      handleDraftMessage(newUuid)
      chatStore.updateChatRole(newUuid, selectedRole.value)
    }
  }

  async function handleResent(branchMessage: Chat.ChatMessage, prompt?: string) {
    const currentSession = toValue(session)
    if (!validateChatOperation() || !currentSession) {
      return
    }

    const { requestOptions, text, originalIndex, attachments = [] } = branchMessage
    const userMessageContent = prompt || requestOptions?.prompt || text || ""

    if (!userMessageContent) {
      showMessage.error("No message to resend")
      return
    }

    if (!prompt) {
      chatStore.updateMessageByUUID(currentSession.uuid, originalIndex, {
        resent: true,
      })
    }

    // Create branch message object for handleCreateBranch
    const resentBranchMessage: Chat.ChatMessage = {
      ...branchMessage,
      text: userMessageContent,
      originalIndex,
      attachments: attachments.length > 0 ? [...attachments] : undefined,
      requestOptions: { prompt: userMessageContent, options: requestOptions?.options },
    }

    try {
      await handleCreateBranch(resentBranchMessage)
    }
    catch (error) {
      console.error("Resend error:", error)
      chatStore.updateMessageByUUID(currentSession.uuid, originalIndex, {
        error: true,
        errorMessage: "Failed to resend message. Please try again.",
        resent: false,
      })
    }
  }

  async function handleCreateEditBranch(branchMessage: Chat.ChatMessage, editedText: string) {
    if (!editedText) {
      showMessage.error("No edited text provided")
      return
    }

    const { parentIndex } = branchMessage
    // Create a modified branch message with the edited text and attachments
    const editedBranchMessage: Chat.ChatMessage = {
      ...branchMessage,
      parentIndex,
      text: editedText,
      requestOptions: { prompt: editedText, options: { model: selectedModel.value } },
    }

    // Reuse the existing branch creation logic
    await handleCreateBranch(editedBranchMessage, parentIndex)
  }

  return {
    handleSubmit,
    handleRegenerate,
    handleContinue,
    handleCreateBranch,
    handleCreateEditBranch,
    handleSwitchBranch,
    handleClear,
    handleStop,
    handleDeleteMessage,
    handleAddNewSession,
    handleResent,
  }
}
