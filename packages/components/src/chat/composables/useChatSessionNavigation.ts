import type { ChatSessionNavigation, ChatState } from "./types"
import { computed, toValue } from "vue"
import { useChatMessageNavigation } from "../utils/useChatMessageNavigation"
import { createThinkingMessage, createUserMessage } from "./utils"

/**
 * Chat navigation composable that integrates with the chat store
 * Provides utilities for navigating through chat message hierarchies
 */
export function useChatSessionNavigation(state: Pick<ChatState, "session" | "chatStore" | "selectedModel">): ChatSessionNavigation {
  const { session, chatStore, selectedModel } = state

  // Get the navigation methods
  const messageNavigation = useChatMessageNavigation()

  /**
   * Get branch information for a message
   */
  function getBranchInfo(session: Chat.ChatSession, messageIndex: number): {
    count: number
    index: number
    isInBranch: boolean
    parentMessage: Chat.ChatMessage | null
  } {
    const parentMessage = chatStore.getParentMessageByIndex(session, messageIndex)

    if (!parentMessage) {
      // This is a root message, check root branches
      const rootBranchCount = session?.rootBranchIndices?.length || 0
      const rootBranchIndex = session?.rootBranchIndex || 0

      return {
        count: rootBranchCount,
        index: rootBranchIndex,
        isInBranch: rootBranchCount > 1,
        parentMessage: null,
      }
    }

    const branchCount = parentMessage.childIndices?.length || 0
    const branchIndex = parentMessage.currentChildIndex || 0

    return {
      count: branchCount,
      index: branchIndex,
      isInBranch: branchCount > 1,
      parentMessage,
    }
  }

  /**
   * Switch to a different branch
   */
  function switchBranch(session: Chat.ChatSession, messageIndex: number, targetBranchIndex: number): boolean {
    const branchInfo = getBranchInfo(session, messageIndex)

    if (!branchInfo.isInBranch || targetBranchIndex < 0 || targetBranchIndex >= branchInfo.count) {
      return false
    }

    if (branchInfo.parentMessage) {
      // Switch child branch
      const parentIndex = branchInfo.parentMessage.originalIndex
      chatStore.updateMessageByUUID(session.uuid, parentIndex, {
        currentChildIndex: targetBranchIndex,
      })
    }
    else {
      // Switch root branch
      chatStore.updateSessionByUUID(session.uuid, {
        rootBranchIndex: targetBranchIndex,
      })
    }

    return true
  }

  /**
   * Create a new branch from a message
   */
  function createBranch(session: Chat.ChatSession, fromMessageIndex: number, content: string, attachments?: Chat.Attachment[]): number | null {
    const fromMessage = chatStore.getMessageByIndex(session, fromMessageIndex)

    // Create user message for the branch with attachments
    const userMessage = createUserMessage(content, fromMessage?.originalIndex ?? null, {
      attachments: attachments && attachments.length > 0 ? [...attachments] : undefined,
    })
    const userMessageIndex = chatStore.addMessageToSession(session, userMessage)

    // Create thinking message for the branch
    const thinkingMessage = createThinkingMessage(content, selectedModel.value, userMessageIndex)
    const thinkingMessageIndex = chatStore.addMessageToSession(session, thinkingMessage)

    return thinkingMessageIndex
  }

  /**
   * Update message index and maintain hierarchy
   */
  function updateFakeMessageIndex(session: Chat.ChatSession, oldIndex: number, newIndex: number): boolean {
    // Find the message with the old index
    const message = session.data[oldIndex]
    if (!message)
      return false

    const parentIndex = message.parentIndex

    const replacement = { from: oldIndex, to: newIndex }

    if (parentIndex === null) {
      // Update root branch indices
      chatStore.replaceRootBranchIndex(session, replacement)
    }
    else {
      // Update parent's childIndices if this message has a parent
      chatStore.replaceChildIndex(session, parentIndex, replacement)
    }

    return true
  }

  /**
   * Delete a message and maintain hierarchy
   */
  function deleteMessageWithHierarchy(session: Chat.ChatSession, messageIndex: number): boolean {
    return chatStore.deleteMessageWithHierarchy(session.uuid, messageIndex)
  }

  /**
   * Get the message path for the current session
   */
  const currentMessagePath = computed(() => {
    const currentSession = toValue(session)
    if (!currentSession)
      return []
    return messageNavigation.getMessagePath(currentSession)
  })

  /**
   * Get the latest message ID for the current session
   */
  const latestMessageId = computed(() => {
    const currentSession = toValue(session)
    if (!currentSession)
      return null
    return messageNavigation.getLatestMessageId(currentSession)
  })

  /**
   * Get the latest sent message ID for the current session
   */
  const latestSentMessageId = computed(() => {
    const currentSession = toValue(session)
    if (!currentSession)
      return null
    return messageNavigation.getLatestSentMessageId(currentSession)
  })

  return {
    // Reactive state
    currentMessagePath,
    latestMessageId,
    latestSentMessageId,

    // Branch management functions
    getBranchInfo,
    switchBranch,
    createBranch,
    updateFakeMessageIndex,
    deleteMessageWithHierarchy,

    // Access to the underlying navigation methods
    ...messageNavigation,
  }
}
