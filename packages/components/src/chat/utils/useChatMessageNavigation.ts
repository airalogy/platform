import type { ChatStoreState } from "@airalogy/components/chat/store"

/**
 * Finds the root message ID from business data
 */
export function findRootMessageIndex(messages: Chat.ChatMessage[]): number | null {
  // Find the message with no parent or with parentIndex as null
  const rootMessage = messages.find(msg => isNullish(msg.parentIndex))
  return rootMessage?.originalIndex ?? null
}

/**
 * Builds parent-child relationship mapping
 */
export function buildMessageHierarchy(messages: Chat.ChatMessage[]): {
  parentToChildren: Record<string, number[]>
  messageMap: Record<string, Chat.ChatMessage>
} {
  const parentToChildren: Record<string, number[]> = {}
  const messageMap: Record<string, Chat.ChatMessage> = {}

  // Build message map and parent-child relationships
  messages.forEach((message) => {
    messageMap[message.originalIndex] = message

    const parentKey = String(message.parentIndex)
    if (!parentToChildren[parentKey]) {
      parentToChildren[parentKey] = []
    }
    parentToChildren[parentKey].push(message.originalIndex)
  })

  // Sort children by message ID for consistent ordering
  Object.keys(parentToChildren).forEach((parentIndex) => {
    parentToChildren[parentIndex].sort((a, b) => a - b)
  })

  return { parentToChildren, messageMap }
}

/**
 * Builds the message path from root to a specific message
 */
export function buildMessagePath(
  targetMessageIndex: number | null,
  messageMap: Record<string, Chat.ChatMessage>,
): number[] {
  if (isNullish(targetMessageIndex))
    return []

  const path: number[] = []
  let currentIndex: number | null = targetMessageIndex

  // Traverse up the parent chain
  do {
    const message = messageMap[currentIndex] as Chat.ChatMessage
    if (!message)
      break

    path.unshift(currentIndex)
    currentIndex = message.parentIndex
  } while (currentIndex)

  return path
}

/**
 * Calculates the root branch index
 */
export function calculateRootBranchIndex(
  messagePath: number[],
  rootBranchIndices: number[],
): number {
  if (messagePath.length === 0)
    return 0

  const firstMessageIndex = messagePath[0]
  const index = rootBranchIndices.indexOf(firstMessageIndex)
  return Math.max(0, index)
}

/**
 * Transforms server messages to client format
 */
export function transformMessages(
  message: Chat.ChatMessage,
  parentToChildren: Record<string, number[]>,
  messagePath: number[],
): void {
  const childIndices = parentToChildren[message.originalIndex] || []
  const currentChildIndex = childIndices.length > 0
    ? Math.max(0, childIndices.findIndex(idx => messagePath.includes(idx)))
    : 0

  // const messageStatus = transformMessageStatus(serverMessage.status)
  // const clientFiles = serverMessage.files.map(FileTransformer.transformServerFileInfoToClient)

  message.childIndices = childIndices
  message.currentChildIndex = currentChildIndex
}

export function updateSessionHierarchy(
  chatStore: ChatStoreState,
  sessionId: string,
  messages: Chat.ChatMessage[],
) {
  try {
    // Build message hierarchy
    const { parentToChildren, messageMap } = buildMessageHierarchy(messages)

    // Find root message and build path
    const rootMessageIndex = findRootMessageIndex(messages)
    const messagePath = buildMessagePath(rootMessageIndex, messageMap)

    // Calculate root branch information
    const rootBranchIndices = parentToChildren.null || []
    const rootBranchIndex = calculateRootBranchIndex(messagePath, rootBranchIndices)
    // Build session data
    // const sessionData: Chat.ChatSession = {
    //   rootBranchIndices,
    //   rootBranchIndex,
    // }

    const session = chatStore.updateSessionByUUID(sessionId, {
      rootBranchIndices,
      rootBranchIndex,
    })

    if (session) {
      const { data } = session
      if (data) {
        data.forEach((message) => {
          transformMessages(message, parentToChildren, messagePath)
        })
      }
    }
  }
  catch (error) {
    console.error("Error retrieving chat history:", error)
    throw new Error(`Failed to retrieve chat history: ${error instanceof Error ? error.message : "Unknown error"}`)
  }
}

/**
 * Temporary message ID generator
 */
let tempIdCounter = -2

/**
 * Generates a new temporary message ID
 */
export function generateTempId(): number {
  return tempIdCounter--
}

/**
 * Checks if an ID is a temporary (negative) ID
 */
export function isTempId(index: number | null): boolean {
  return index !== null && index <= -2
}

/**
 * Checks if a value is null or undefined
 */
export function isNullish<T>(value: T | null | undefined): value is null | undefined {
  return value == null
}
/**
 * Gets a message from a specific session
 */
export function getMessage(session: Chat.ChatSession, messageIndex: number): Chat.ChatMessage | null {
  return session.data[messageIndex] || null
}

/**
 * Gets the parent message of a specific message
 */
export function getParentMessage(session: Chat.ChatSession, messageIndex: number): Chat.ChatMessage | null {
  const message = getMessage(session, messageIndex)
  return message && message.parentIndex !== null ? getMessage(session, message.parentIndex) : null
}

/**
 * Splits an array of IDs into temporary and permanent IDs
 */
export function splitIndexByType(indexes: number[]): [number[], number[]] {
  const tempIndex = indexes.findIndex(index => !isTempId(index))
  return [indexes.slice(0, tempIndex), indexes.slice(tempIndex)]
}

/**
 * Chat message navigation composable
 * Provides utilities for navigating through chat message hierarchies
 */
export function useChatMessageNavigation() {
  /**
   * Gets the complete message path from root to current message
   */
  function getMessagePath(session: Chat.ChatSession): number[] {
    if (!session)
      return []

    const { rootBranchIndices, rootBranchIndex } = session

    const path: number[] = []
    let currentIndex = rootBranchIndices[rootBranchIndex]

    if (!isNullish(currentIndex)) {
      path.push(currentIndex)
    }

    while (!isNullish(currentIndex)) {
      const message = getMessage(session, currentIndex)
      if (!message)
        break

      const { childIndices, currentChildIndex } = message

      const [tempIndexes] = splitIndexByType(childIndices)
      path.push(...tempIndexes)

      const nextIndex = childIndices[currentChildIndex]
      if (isNullish(nextIndex))
        break

      if (!tempIndexes.includes(nextIndex)) {
        path.push(nextIndex)
      }
      currentIndex = nextIndex
    }

    return path
  }

  /**
   * Gets the number of branches for a message
   */
  function getMessageBranchCount(session: Chat.ChatSession, messageIndex: number): number {
    const parentMessage = getParentMessage(session, messageIndex)
    if (parentMessage) {
      const [tempIndexes, realIndexes] = splitIndexByType(parentMessage.childIndices)
      return tempIndexes.includes(messageIndex) ? 1 : realIndexes.length
    }

    return session.rootBranchIndices.length
  }

  /**
   * Gets the branch index for a message
   */
  function getMessageBranchIndex(session: Chat.ChatSession, messageIndex: number): number {
    const parentMessage = getParentMessage(session, messageIndex)
    if (!parentMessage) {
      return session.rootBranchIndex
    }

    const [tempIndexes, realIndexes] = splitIndexByType(parentMessage.childIndices)
    return tempIndexes.includes(messageIndex) ? 0 : realIndexes.indexOf(messageIndex)
  }

  /**
   * Gets the latest sent (non-temporary) message ID
   */
  function getLatestSentMessageId(session: Chat.ChatSession): number | null {
    const messagePath = getMessagePath(session)
    const latestSentIndex = messagePath.findLast(index => !isTempId(index))
    return latestSentIndex || null
  }

  /**
   * Gets the latest message ID in the path
   */
  function getLatestMessageId(session: Chat.ChatSession): number | null {
    const messagePath = getMessagePath(session)
    return messagePath.at(-1) || null
  }

  /**
   * Checks if a message is the last showing user message
   */
  function getIsLastShowingUserMessage(session: Chat.ChatSession, messageIndex: number): boolean {
    const getNextMessage = (message: Chat.ChatMessage): Chat.ChatMessage | null => {
      const nextIndex = message.childIndices[message.currentChildIndex] ?? 0
      return getMessage(session, nextIndex)
    }

    const message = getMessage(session, messageIndex)
    if (!message || !message.inversion) {
      return false
    }

    if (!isTempId(messageIndex)) {
      const nextMessage = getNextMessage(message)
      return !nextMessage || !getNextMessage(nextMessage)
    }

    const parentMessage = getParentMessage(session, messageIndex)
    if (!parentMessage) {
      return true
    }

    const [, realIndexes] = splitIndexByType(parentMessage.childIndices)
    return realIndexes.includes(messageIndex)
  }

  return {
    getMessagePath,
    getMessageBranchCount,
    getMessageBranchIndex,
    getLatestSentMessageId,
    getLatestMessageId,
    getIsLastShowingUserMessage,
  }
}
