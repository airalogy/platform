import type { ChatProviderProps } from "../providers/useChatProvider"
import type { ChatMutations, ChatState } from "./types"
import { nanoid } from "nanoid"

export function useChatMutations(state: ChatState, providerContext: ChatProviderProps): ChatMutations {
  const { chatStore, chatId, emptyDraftId, isEmptyDraft, source, airalogyId } = state

  function clearActive() {
    chatStore.clearActive()
    emptyDraftId.value = nanoid()
  }

  function updateContext(value: Chat.ChatContext[] | null) {
    if (!value || !chatId.value) {
      return
    }

    if (isEmptyDraft.value) {
      // Update draft context when no chatId exists
      chatStore.updateDraftContext(emptyDraftId.value, value || [])
      return
    }

    // Update existing chat context
    chatStore.updateSessionContextByUUID(chatId.value, value)
  }

  function handleDraftMessage(uuid: string, draftMessage?: Chat.ChatMessage) {
    // Create empty session (messages will be added by handleCreateBranch)
    const newSession = chatStore.createEmptySession(uuid, source.value, airalogyId.value)

    if (newSession) {
      // Save draft context if it exists
      const draftContext = chatStore.getDraftMessage(emptyDraftId.value)?.context
      if (draftContext) {
        chatStore.updateSessionContext(newSession, draftContext)
      }
    }

    // Clean up old draft and create new one
    if (emptyDraftId.value) {
      chatStore.clearDraftMessage(emptyDraftId.value)
    }

    // emptyDraftId.value = nanoid()
  }

  return {
    clearActive,
    updateContext,
    handleDraftMessage,
  }
}
