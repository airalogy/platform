import type { ChatType } from "@airalogy/shared/enum/chat"
import type { ChatModels, PiniaStore } from "@airalogy/shared/types"
// import { getChatConversation } from "@airalogy/shared/service/api/chat"
import { nanoid } from "nanoid"
import { defineStore } from "pinia"
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue"
// Add router import for navigation
import { useRouter } from "vue-router"
import { createUserMessage } from "../composables/utils"
import { defaultConfig, defaultState, getLocalState, setLocalState } from "./helper"

export const useChatStore = defineStore("chat-store", () => {
  // Add mode state for routing
  const routingMode = ref<"query" | "param">("query")
  const router = useRouter()

  // state
  const state = ref<Chat.ChatState>(getLocalState())

  const context = ref<Record<string, Chat.ChatContext[]>>(
    Object.fromEntries(state.value.session.filter(chat => chat.context != null).map(chat => [chat.uuid, chat.context!])),
  )

  const allChatHistory = computed(() => {
    return state.value.history.sort((a, b) => {
      const aChat = findSessionByUUID(a.uuid)
      const bChat = findSessionByUUID(b.uuid)

      return (bChat?.data[0]?.dateTime ?? 0) - (aChat?.data[0]?.dateTime ?? 0)
    })
  })

  // Add new state for draft messages
  const draftMessages = reactive<Map<string, Chat.ChatMessage>>(new Map())

  // getters
  const getChatHistoryByCurrentActive = computed(() => {
    const target = state.value.history.find(item => item.uuid === state.value.active)
    return target || null
  })

  function findSessionByUUID(uuid?: string): Chat.ChatSession | undefined {
    const activeUuid = !uuid ? state.value.active : uuid
    if (!activeUuid)
      return undefined
    const index = findSessionIndex(activeUuid)
    return index !== -1 ? state.value.session[index] : undefined
  }

  function findHistory(uuid: string): Chat.ChatHistory | null {
    return state.value.history.find(item => item.uuid === uuid) || null
  }

  function findHistoryIndex(uuid?: string): number {
    return uuid ? state.value.history.findIndex(item => item.uuid === uuid) : -1
  }

  function findSessionIndex(uuid: string): number {
    return uuid ? state.value.session.findIndex(item => item.uuid === uuid) : -1
  }

  function getChatDataByUUID(uuid?: string): Chat.ChatMessage[] | null {
    if (!uuid) {
      return null
    }
    const session = findSessionByUUID(uuid)
    return session?.data || null
  }

  function findChatByUUIDAndIndex(uuid: string | undefined, index: number): Chat.ChatMessage | null {
    const data = getChatDataByUUID(uuid)
    return data?.[index] || null
  }

  function updateSessionByUUID(uuid: string, session: Partial<Chat.ChatSession>) {
    const target = findSessionByUUID(uuid)
    if (target) {
      return updateSession(target, session)
    }

    return null
  }

  function updateSession(session: Chat.ChatSession, properties: Partial<Chat.ChatSession>) {
    if (!session) {
      return
    }

    Object.assign(session, properties)
    recordState()

    return session
  }

  function addHistory(
    history: Chat.ChatHistory,
    chatData?: Chat.ChatMessage[],
    source: Chat.ChatSource = "global",
  ) {
    const { uuid, airalogyId } = history

    if (findSessionIndex(uuid) === -1) {
      if (chatData) {
        state.value.session.unshift({ uuid, data: chatData, source, airalogyId, config: defaultConfig, rootBranchIndex: 0, rootBranchIndices: [] })
        const firstUserMessage = chatData.find(msg => !msg.inversion)?.text
        if (firstUserMessage) {
          history.title = firstUserMessage
        }
      }
    }

    const historyIndex = findHistoryIndex(uuid)
    if (historyIndex === -1) {
      state.value.history.unshift(history)
    }
    else {
      state.value.history[historyIndex] = history
    }

    reloadRoute(uuid)
  }

  function updateHistory(uuid: string, edit: Partial<Chat.ChatHistory>) {
    const history = findHistory(uuid)
    if (history) {
      Object.assign(history, edit)
      recordState()
    }

    return history
  }

  function deleteHistory(uuid: string) {
    const index = findHistoryIndex(uuid)
    if (index === -1) {
      return
    }

    state.value.history.splice(index, 1)
    state.value.session.splice(index, 1)

    if (state.value.history.length === 0) {
      state.value.active = null
      return
    }

    if (uuid === state.value.active) {
      state.value.active = null
    }

    void recordState()
  }

  function setActive(uuid: string) {
    state.value.active = uuid
  }

  function clearActive() {
    state.value.active = null
    reloadRoute()
  }

  function setMessage(chat: Chat.ChatSession, index: number, message: Chat.ChatMessage) {
    const { data } = chat
    if (data) {
      data[index] = message
      recordState()
    }
  }

  function setMessageByUUID(uuid: string, index: number, message: Chat.ChatMessage) {
    const chat = findSessionByUUID(uuid)
    if (chat) {
      setMessage(chat, index, message)
    }
  }

  function updateMessageByUUID(uuid: string, index: number, properties: Partial<Chat.ChatMessage>) {
    const chat = findSessionByUUID(uuid)
    if (chat) {
      updateMessage(chat, index, properties)
    }
  }

  function updateMessage(session: Chat.ChatSession, index: number, properties: Partial<Chat.ChatMessage>) {
    const { data } = session
    if (data) {
      if (properties.cancelled) {
        properties.loading = false
      }
      Object.assign(data[index], properties)

      recordState()
    }
  }

  function deleteMessageByUUID(uuid: string, index: number) {
    const data = getChatDataByUUID(uuid)
    if (data) {
      data.splice(index, 1)
      recordState()
    }
  }

  function clearSessionDataByUUID(uuid: string) {
    if (!uuid) {
      if (state.value.session.length) {
        setSessionData(0, [])
        recordState()
      }
      return
    }

    const index = findSessionIndex(uuid)
    if (index !== -1) {
      setSessionData(index, [])
      recordState()
    }
  }

  function getTargetHistory(source: Chat.ChatSource, airalogyId?: string | null) {
    return state.value.history.filter(
      item => item.source === source && (!airalogyId || item.airalogyId === airalogyId),
    )
  }

  function clearHistory() {
    state.value = defaultState(false)
    recordState()
  }

  function setRoutingMode(mode: "query" | "param") {
    routingMode.value = mode
  }

  async function reloadRoute(uuid?: string | null) {
    try {
      if (!router) {
        return
      }

      const currentRoute = router.currentRoute.value

      if (routingMode.value === "query") {
        // Handle query parameter routing
        // Use history.replaceState to update URL without triggering Vue Router navigation
        // This avoids the page transition effect in GlobalContent
        const currentUrl = new URL(window.location.href)

        if (uuid) {
          if (currentUrl.searchParams.get("chat") === uuid) {
            return
          }
          currentUrl.searchParams.set("chat", uuid)
        }
        else {
          if (!currentUrl.searchParams.has("chat")) {
            return
          }
          currentUrl.searchParams.delete("chat")
        }

        // Use history.replaceState to update URL without navigation
        window.history.replaceState(
          { ...window.history.state },
          "",
          currentUrl.toString(),
        )
      }
      else {
        // Handle route parameter routing - need to use router for path changes
        if (uuid) {
          if (uuid === currentRoute.params.chatId) {
            return
          }
          await router.push({
            name: currentRoute.name || "root",
            params: { chatId: uuid },
          })
        }
        else {
          if (!currentRoute.params.chatId) {
            return
          }
          await router.push({
            name: currentRoute.name || "root",
            params: { chatId: undefined },
          })
        }
      }
    }
    catch (error) {
      console.error("[reloadRoute] Router navigation failed:", error)
      // Fallback to just recording state if router navigation fails
    }
  }

  function recordState() {
    setLocalState(state.value)
  }

  function getLatestSessionBySource(source: Chat.ChatSource): Chat.ChatSession | null {
    return state.value.session.find(item => item.source === source) || null
  }

  function updateAiralogyIdByUuid(uuid: string, airalogyId: string | null) {
    // Update in chat array
    const chat = findSessionByUUID(uuid)
    if (chat) {
      chat.airalogyId = airalogyId
    }

    // Update in history array
    const history = findHistory(uuid)
    if (history) {
      history.airalogyId = airalogyId
    }

    recordState()

    return { chat, history }
  }

  function updateServerIdByUuid(uuid: string, serverId: string) {
    const chat = findSessionByUUID(uuid)
    if (chat) {
      chat.serverId = serverId
    }

    recordState()

    return chat
  }

  /**
   * Replace both session and history UUIDs with server ID
   * This function atomically updates all references to use server ID as the primary identifier
   */
  function replaceUUIDWithServerId(oldUuid: string, serverId: string) {
    if (oldUuid === serverId) {
      return
    }

    // Check if server ID already exists to avoid duplicates
    const existingSessionWithServerId = findSessionByUUID(serverId)
    if (existingSessionWithServerId && existingSessionWithServerId.uuid !== oldUuid) {
      console.warn(`Server ID ${serverId} already exists for a different session`)
      return null
    }

    // Find the session and history by old UUID
    const session = findSessionByUUID(oldUuid)
    const history = findHistory(oldUuid)

    if (!session || !history) {
      console.warn(`Session or history not found for UUID: ${oldUuid}`)
      return null
    }

    // Store the old context and draft message if they exist
    const oldContext = context.value[oldUuid]
    const oldDraftMessage = draftMessages.get(oldUuid)

    // Update session UUID
    session.uuid = serverId
    session.serverId = serverId

    // Update history UUID
    history.uuid = serverId

    // Update active state if it matches the old UUID
    if (state.value.active === oldUuid) {
      state.value.active = serverId
    }

    // Migrate context mapping
    if (oldContext) {
      context.value[serverId] = oldContext
      delete context.value[oldUuid]
    }

    // Migrate draft messages
    if (oldDraftMessage) {
      draftMessages.set(serverId, oldDraftMessage)
      draftMessages.delete(oldUuid)
    }

    setActive(serverId)
    // Explicitly trigger route reload to ensure URL is updated
    reloadRoute(serverId)
    recordState()

    return { session, history }
  }

  function updateChatRole(uuid: string, role: ChatType) {
    const chat = findSessionByUUID(uuid)
    if (chat) {
      chat.role = role
    }

    recordState()
  }

  function getServerIdByUUID(uuid: string) {
    const chat = findSessionByUUID(uuid)
    return chat?.serverId
  }

  async function restoreChatHistory(uuid: string, getChatConversation: (id: string) => Promise<ChatModels.ChatResponse>) {
    const chat = findSessionByUUID(uuid)
    if (!chat?.serverId)
      return

    try {
      const data = await getChatConversation(chat.serverId)
      if (!data?.messages)
        return

      // Convert server history format to local chat messages
      const messages = data.messages
        .filter(({ role, content }) => (role === "user" || role === "assistant") && !!content)
        .map(
          (item, index): Chat.ChatMessage => ({
            dateTime: Date.now(),
            text: item.content || "",
            inversion: item.role === "user",
            error: false,
            loading: false,
            editing: false,
            tool: index > 0 ? data.messages[index - 1] : null,
            conversationOptions: {
              conversationId: data.id,
              parentMessageId: data.id,
            },
            requestOptions: {
              prompt: item.role === "user" ? item.content || "" : "",
              options: null,
            },
            originalIndex: index,
            parentIndex: index > 0 ? index - 1 : null,
            childIndices: [],
            currentChildIndex: 0,
          }),
        )

      // Update the chat with restored messages
      const chatIndex = findSessionIndex(uuid)
      if (chatIndex !== -1) {
        setSessionData(chatIndex, messages)
      }

      recordState()
    }
    catch (error) {
      console.error("Failed to restore chat history:", error)
    }
  }

  function getHistoryByAiralogyId(airalogyId: string) {
    return state.value.history.filter(item => item.airalogyId === airalogyId)
  }

  function getHistoryBySource(source: Chat.ChatSource) {
    return state.value.history.filter(item => item.source === source)
  }

  function addAttachment(uuid: string, file: Chat.Attachment) {
    // Create or get draft message
    let draftMessage = draftMessages.get(uuid)

    if (!draftMessage) {
      const newDraftMessage: Chat.ChatMessage = {
        dateTime: Date.now(),
        text: "",
        inversion: true,
        isDraft: true,
        attachments: [],
        requestOptions: { prompt: "" },
        originalIndex: 0,
        parentIndex: null,
        childIndices: [],
        currentChildIndex: 0,
        context: [],
      }
      draftMessages.set(uuid, newDraftMessage)
      draftMessage = newDraftMessage
    }

    if (!draftMessage.attachments) {
      draftMessage.attachments = []
    }

    draftMessage.attachments.push({
      ...file,
    })

    recordState()
  }

  function removeAttachment(uuid: string, fileId: string, removeDraftMessage: boolean = true) {
    const draftMessage = draftMessages.get(uuid)
    if (!draftMessage?.attachments) {
      return
    }

    const fileIndex = draftMessage.attachments.findIndex((f: Chat.Attachment) => f.id === fileId)

    if (fileIndex !== -1) {
      const file = draftMessage.attachments[fileIndex]
      if (file.url?.startsWith("blob:")) {
        URL.revokeObjectURL(file.url)
      }

      draftMessage.attachments.splice(fileIndex, 1)

      // Remove draft message if it has no attachments
      if (draftMessage.attachments.length === 0 && removeDraftMessage) {
        draftMessages.delete(uuid)
      }

      recordState()
    }
  }

  function updateAttachmentUploadStatus(uuid: string, fileId: string, isUploading: boolean) {
    const draftMessage = draftMessages.get(uuid)
    if (!draftMessage?.attachments)
      return

    const fileIndex = draftMessage.attachments.findIndex((f: Chat.Attachment) => f.id === fileId)
    if (fileIndex !== -1) {
      draftMessage.attachments[fileIndex].isUploading = isUploading
      draftMessage.attachments[fileIndex].status = isUploading ? "uploading" : "finished"
      draftMessage.attachments[fileIndex].percentage = isUploading ? draftMessage.attachments[fileIndex].percentage || 0 : 100
      recordState()
    }
  }

  function updateAttachmentServerId(uuid: string, fileId: string, payload: { serverId: string, url?: string, name?: string }) {
    const draftMessage = draftMessages.get(uuid)
    if (!draftMessage?.attachments)
      return

    const fileIndex = draftMessage.attachments.findIndex((f: Chat.Attachment) => f.id === fileId)
    if (fileIndex !== -1) {
      draftMessage.attachments[fileIndex].serverId = payload.serverId
      draftMessage.attachments[fileIndex].url = payload.url || draftMessage.attachments[fileIndex].url
      draftMessage.attachments[fileIndex].name = payload.name || draftMessage.attachments[fileIndex].name
      draftMessage.attachments[fileIndex].isUploading = false
      draftMessage.attachments[fileIndex].status = "finished"
      draftMessage.attachments[fileIndex].percentage = 100
      recordState()
    }
  }

  function getMessageAttachments(uuid: string): Chat.Attachment[] | null {
    const draftMessage = draftMessages.get(uuid)
    if (draftMessage) {
      if (!draftMessage.attachments) {
        draftMessage.attachments = []
      }

      return draftMessage.attachments
    }

    return null
  }

  // Add function to get draft message
  function getDraftMessage(uuid: string | null): Chat.ChatMessage | undefined {
    if (!uuid) {
      return undefined
    }

    return draftMessages.get(uuid)
  }

  function resetDraftMessage(uuid: string | null, draftContext: Chat.ChatContext[] = []) {
    if (!uuid) {
      return
    }

    const prevMessage = getDraftMessage(uuid)
    if (prevMessage) {
      return prevMessage
    }

    const newMessage: Chat.ChatMessage = createUserMessage("", null, { context: draftContext })
    draftMessages.set(uuid, newMessage)

    return newMessage
  }

  // Add function to update draft context
  function updateDraftContext(uuid: string | null, contextData: Chat.ChatContext[]) {
    if (!uuid) {
      return
    }

    const prevMessage = getDraftMessage(uuid)
    // Create draft message if it doesn't exist
    if (!prevMessage) {
      resetDraftMessage(uuid, contextData)
    }
    else {
      // Update context of existing draft message
      prevMessage.context = contextData
    }

    return prevMessage
  }

  // Add function to clear draft message
  function clearDraftMessage(uuid: string | null) {
    if (!uuid) {
      return
    }

    draftMessages.delete(uuid)
  }

  function getLastMessage(uuid: string) {
    const chat = findSessionByUUID(uuid)
    if (!chat)
      return null

    const lastMessage = chat.data[chat.data.length - 1]
    return lastMessage
  }

  function updateAttachment(uuid: string, fileId: string, updates: Partial<Chat.Attachment>) {
    const lastMessage = getLastMessage(uuid)
    if (!lastMessage?.attachments)
      return

    const fileIndex = lastMessage.attachments.findIndex((file: Chat.Attachment) => file.id === fileId)
    if (fileIndex === -1)
      return

    Object.assign(lastMessage.attachments[fileIndex], updates)
  }

  function updateSessionContext(session: Chat.ChatSession, contextData: Chat.ChatContext[]) {
    if (!session) {
      return
    }
    context.value[session.uuid] = contextData
    session.context = contextData
    recordState()
  }

  function updateSessionContextByUUID(uuid: string | null, contextData: Chat.ChatContext[]) {
    if (!uuid) {
      return
    }

    // Update both reactive context and state
    const session = findSessionByUUID(uuid)

    if (session) {
      updateSessionContext(session, contextData)
    }
  }

  /**
   * Replace a child ID in a parent message's childIndices array
   */
  function replaceChildIndexByUUID(uuid: string, parentIndex: number, replacement: { from: number, to: number }) {
    const session = findSessionByUUID(uuid)
    if (!session) {
      return false
    }

    return replaceChildIndex(session, parentIndex, replacement)
  }

  function replaceChildIndex(session: Chat.ChatSession, parentIndex: number, replacement: { from: number, to: number }) {
    const parentMessage = session.data[parentIndex]
    if (!parentMessage || !parentMessage.childIndices)
      return false

    const childIndex = parentMessage.childIndices.indexOf(replacement.from)
    if (childIndex !== -1) {
      parentMessage.childIndices[childIndex] = replacement.to

      // Update currentChildIndex if it was pointing to the replaced child
      if (parentMessage.currentChildIndex === childIndex) {
        parentMessage.currentChildIndex = childIndex // Keep same position
      }

      recordState()
      return true
    }

    return false
  }

  /**
   * Replace a root branch ID in a session's rootBranchIndices array
   */
  function replaceRootBranchIndexByUUID(sessionId: string, replacement: { from: number, to: number }) {
    const session = findSessionByUUID(sessionId)
    if (!session) {
      return false
    }

    return replaceRootBranchIndex(session, replacement)
  }

  function replaceRootBranchIndex(session: Chat.ChatSession, replacement: { from: number, to: number }) {
    const { rootBranchIndices, rootBranchIndex } = session
    if (!rootBranchIndices) {
      session.rootBranchIndices = []
    }

    const branchIndex = rootBranchIndices.indexOf(replacement.from)
    if (branchIndex !== -1) {
      rootBranchIndices[branchIndex] = replacement.to

      // Update rootBranchIndex if it was pointing to the replaced branch
      if (session.rootBranchIndex === branchIndex) {
        session.rootBranchIndex = branchIndex // Keep same position
      }

      recordState()
      return true
    }

    return false
  }

  /**
   * Update all message indices after a message deletion
   */
  function updateIndicesAfterDeletion(sessionId: string, deletedIndex: number) {
    const session = findSessionByUUID(sessionId)
    if (!session)
      return

    // Update all messages that have indices greater than the deleted index
    session.data.forEach((message, index) => {
      // Update originalIndex for messages after the deleted one
      if (message.originalIndex > deletedIndex) {
        message.originalIndex = message.originalIndex - 1
      }

      // Update parentIndex if it points to a message after the deleted one
      if (message.parentIndex !== null && message.parentIndex > deletedIndex) {
        message.parentIndex = message.parentIndex - 1
      }

      // Update childIndices if they point to messages after the deleted one
      if (message.childIndices && message.childIndices.length > 0) {
        message.childIndices = message.childIndices.map(childIndex =>
          childIndex > deletedIndex ? childIndex - 1 : childIndex,
        )
      }
    })

    // Update root branch indices if they point to messages after the deleted one
    if (session.rootBranchIndices && session.rootBranchIndices.length > 0) {
      session.rootBranchIndices = session.rootBranchIndices.map(branchIndex =>
        branchIndex > deletedIndex ? branchIndex - 1 : branchIndex,
      )
    }

    recordState()
  }

  /**
   * Update all message indices after a message insertion
   */
  function updateIndicesAfterInsertion(sessionId: string, insertedIndex: number) {
    const session = findSessionByUUID(sessionId)
    if (!session)
      return

    // Update all messages that have indices greater than or equal to the inserted index
    session.data.forEach((message, index) => {
      // Update originalIndex for messages after the inserted one
      if (message.originalIndex >= insertedIndex && index !== insertedIndex) {
        message.originalIndex = message.originalIndex + 1
      }

      // Update parentIndex if it points to a message after the inserted one
      if (message.parentIndex !== null && message.parentIndex >= insertedIndex) {
        message.parentIndex = message.parentIndex + 1
      }

      // Update childIndices if they point to messages after the inserted one
      if (message.childIndices && message.childIndices.length > 0) {
        message.childIndices = message.childIndices.map(childIndex =>
          childIndex >= insertedIndex ? childIndex + 1 : childIndex,
        )
      }
    })

    // Update root branch indices if they point to messages after the inserted one
    if (session.rootBranchIndices && session.rootBranchIndices.length > 0) {
      session.rootBranchIndices = session.rootBranchIndices.map(branchIndex =>
        branchIndex >= insertedIndex ? branchIndex + 1 : branchIndex,
      )
    }

    recordState()
  }

  /**
   * Enhanced delete message function with hierarchy management
   */
  function deleteMessageWithHierarchy(uuid: string, index: number) {
    const session = findSessionByUUID(uuid)
    if (!session)
      return false

    const data = session.data
    if (!data || index < 0 || index >= data.length)
      return false

    const messageToDelete = data[index]

    // Remove this message from its parent's childIndices
    if (messageToDelete.parentIndex !== null) {
      const parentMessage = data[messageToDelete.parentIndex]
      if (parentMessage && parentMessage.childIndices) {
        const childIndex = parentMessage.childIndices.indexOf(index)
        if (childIndex !== -1) {
          parentMessage.childIndices.splice(childIndex, 1)

          // Update currentChildIndex if necessary
          if (parentMessage.currentChildIndex >= childIndex) {
            parentMessage.currentChildIndex = Math.max(0, parentMessage.currentChildIndex - 1)
          }
        }
      }
    }

    // Remove this message from root branch indices if it's a root message
    if (messageToDelete.parentIndex === null && session.rootBranchIndices) {
      const rootIndex = session.rootBranchIndices.indexOf(index)
      if (rootIndex !== -1) {
        session.rootBranchIndices.splice(rootIndex, 1)

        // Update rootBranchIndex if necessary
        if (session.rootBranchIndex >= rootIndex) {
          session.rootBranchIndex = Math.max(0, session.rootBranchIndex - 1)
        }
      }
    }

    // Remove the message from the array
    data.splice(index, 1)

    // Update all indices after deletion
    updateIndicesAfterDeletion(uuid, index)

    return true
  }

  function getMessageByIndex(session: Chat.ChatSession, index: number): Chat.ChatMessage | null {
    if (!session.data)
      return null

    return session.data.find(msg => msg.originalIndex === index) || null
  }

  /**
   * Get message by original index
   */
  function getMessageByUUIDAndIndex(sessionId: string, index: number): Chat.ChatMessage | null {
    const session = findSessionByUUID(sessionId)
    return session ? getMessageByIndex(session, index) : null
  }

  /**
   * Get parent message by message index
   */
  function getParentMessageByIndex(session: Chat.ChatSession, messageIndex: number): Chat.ChatMessage | null {
    const message = getMessageByIndex(session, messageIndex)
    if (!message || message.parentIndex === null)
      return null

    return getMessageByIndex(session, message.parentIndex)
  }

  function getParentMessageByUUIDAndIndex(sessionId: string, messageIndex: number): Chat.ChatMessage | null {
    const session = findSessionByUUID(sessionId)
    return session ? getParentMessageByIndex(session, messageIndex) : null
  }

  function setSessionData(index: number, data: Chat.ChatMessage[]) {
    if (index !== -1) {
      state.value.session[index].data = data
      recordState()
    }
  }

  function resetMessageLoadingState(message: Chat.ChatMessage) {
    if (message.loading) {
      message.loading = false
      message.cancelled = true
    }
  }

  function resetLoadingStates(chat: Chat.ChatState["session"]) {
    chat.forEach((chatItem) => {
      const hasLoadingMessages = chatItem.data.some(msg => msg.loading)
      if (!hasLoadingMessages)
        return

      chatItem.data.forEach(resetMessageLoadingState)
    })
    return chat
  }

  function addMessageToSessionByUUID(
    uuid: string | undefined,
    message: Omit<Chat.ChatMessage, "originalIndex">,
    source: Chat.ChatSource = "global",
    airalogyId?: string | null,
  ) {
    const finalUuid = uuid || nanoid()
    const session = findSessionByUUID(finalUuid)

    if (session) {
      return addMessageToSession(session, message)
    }

    const newSession: Chat.ChatSession = {
      uuid: finalUuid,
      data: [],
      source,
      airalogyId,
      config: defaultConfig,
      rootBranchIndex: 0,
      rootBranchIndices: [],
    }

    state.value.session.push(newSession)

    return addMessageToSession(newSession, message)
  }

  function createEmptySession(
    uuid: string,
    source: Chat.ChatSource = "global",
    airalogyId?: string | null,
  ) {
    const existingSession = findSessionByUUID(uuid)
    if (existingSession) {
      return existingSession
    }

    const newSession: Chat.ChatSession = {
      uuid,
      data: [],
      source,
      airalogyId,
      config: defaultConfig,
      rootBranchIndex: 0,
      rootBranchIndices: [],
    }

    state.value.session.push(newSession)

    // Create history entry
    const title = `New ${source.charAt(0).toUpperCase() + source.slice(1)} Chat`
    state.value.history.push({
      uuid,
      title,
      isEdit: false,
      source,
      time: Date.now(),
      airalogyId,
    })

    setActive(uuid)
    recordState()

    return newSession
  }

  function addMessageToSession(session: Chat.ChatSession, message: Omit<Chat.ChatMessage, "originalIndex">) {
    const { data, uuid, source, airalogyId } = session
    const history = findHistory(uuid)

    // Reset any existing loading states if chat exists
    if (data) {
      data.forEach(resetMessageLoadingState)
    }

    // Set originalIndex before adding
    const originalIndex = data.length

    // Only auto-assign parent if parentIndex is undefined (not explicitly null)
    // null means "explicitly no parent" (for first messages and branch roots)
    // undefined means "auto-assign parent for linear conversation"
    let parentIndex = message?.parentIndex ?? null
    if (typeof parentIndex !== "number") {
      const previousMessageIndex = originalIndex - 1
      if (previousMessageIndex >= 0) {
        parentIndex = previousMessageIndex
      }
    }

    const messageWithIndex: Chat.ChatMessage = { ...message, originalIndex, parentIndex }

    // Update parent's childIndices if this message has a parent
    if (typeof parentIndex === "number" && parentIndex >= 0) {
      const parentMessage = data[parentIndex]
      if (parentMessage) {
        if (!parentMessage.childIndices) {
          parentMessage.childIndices = []
        }

        const newIndex = parentMessage.childIndices.push(originalIndex) - 1
        parentMessage.currentChildIndex = newIndex
      }
    }

    data.push(messageWithIndex)

    // Create or update history
    if (!history) {
      const title = message?.text
        ?? (message?.inversion ? message.text : `New ${source.charAt(0).toUpperCase() + source.slice(1)} Chat`)

      state.value.history.push({
        uuid,
        title,
        isEdit: false,
        source,
        time: Date.now(),
        airalogyId,
      })
    }
    else if (message?.inversion && data?.length === 1) {
      history.title = message.text
    }

    setActive(uuid)
    recordState()

    return data ? data.length - 1 : 0
  }

  watch(
    state,
    (newState) => {
      if (newState.isInit) {
        state.value.isInit = false
      }
    },
    { deep: true },
  )

  onBeforeUnmount(() => {
    resetLoadingStates(state.value.session)
  })

  return {
    // expose state as refs
    state,
    draftMessages,
    context,
    // activeChat,
    allChatHistory,
    // getters
    getChatHistoryByCurrentActive,
    // getServerIdByCurrentActive,
    getTargetHistory,
    getLatestSessionBySource,
    getLastMessage,
    getChatDataByUUID,
    getDraftMessage,
    getMessageAttachments,
    getServerIdByUUID,
    getHistoryByAiralogyId,
    getHistoryBySource,
    getMessageByIndex,
    getMessageByUUIDAndIndex,
    getParentMessageByIndex,
    getParentMessageByUUIDAndIndex,

    // actions
    findSessionByUUID,
    findHistory,
    addHistory,
    updateHistory,
    deleteHistory,
    clearHistory,
    setActive,
    clearActive,
    findChatByUUIDAndIndex,
    addMessageToSessionByUUID,
    addMessageToSession,
    createEmptySession,

    updateSessionByUUID,
    updateSession,

    setMessage,
    setMessageByUUID,
    updateMessageByUUID,
    updateMessage,
    deleteMessageByUUID,
    deleteMessageWithHierarchy,
    clearSessionDataByUUID,
    reloadRoute,
    recordState,
    updateAiralogyIdByUuid,
    updateServerIdByUuid,
    updateChatRole,
    restoreChatHistory,
    addAttachment,
    removeAttachment,
    updateAttachmentUploadStatus,
    updateAttachmentServerId,
    updateDraftContext,
    resetDraftMessage,
    clearDraftMessage,
    updateAttachment,
    updateSessionContext,
    updateSessionContextByUUID,
    replaceChildIndex,
    replaceChildIndexByUUID,
    replaceRootBranchIndex,
    replaceRootBranchIndexByUUID,
    updateIndicesAfterDeletion,
    updateIndicesAfterInsertion,
    replaceUUIDWithServerId,
    setRoutingMode,
  }
})

export type ChatStoreState = PiniaStore<typeof useChatStore>
