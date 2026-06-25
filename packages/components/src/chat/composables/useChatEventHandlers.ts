import type { ChatProviderContext } from "../providers/useChatProvider"
import type { ChatHistoryOperations, ChatMutations, ChatState } from "./types"
import { useRouteParams, useRouteQuery } from "@vueuse/router"
import { toValue, watch } from "vue"
import { useChatStore } from "../store"

export function useChatEventHandlers(state: ChatState, mutations: ChatMutations, history: ChatHistoryOperations, mode: ChatProviderContext["mode"], provider: ChatProviderContext) {
  const { chatId, emptyDraftId, defaultChatId, airalogyId, session, selectedRole, context } = state
  const { contextDialog } = provider
  const { updateContext, clearActive } = mutations
  const { loadChat } = history

  const chatStore = useChatStore()

  let chatRouteId = ref<string | undefined | null>(null)

  watch (() => toValue(mode) || false, (val) => {
  // Initialize store with the correct routing mode
    chatStore.setRoutingMode(val)

    chatRouteId = val ? useRouteQuery<string | undefined | null>("chat") : useRouteParams<string | undefined | null>("chatId")

    const stop = watch(chatRouteId, async (newId) => {
      if (newId) {
        chatStore.setActive(newId)

        const chat = await loadChat({ uuid: newId } as Chat.ChatHistory)

        if (chat) {
          if (!chatStore.context[newId]) {
            chatStore.updateSessionContextByUUID(newId, [])
          }
        }
        else {
          chatStore.clearActive()
        }
      }
      else {
        clearActive()
      }
    }, { immediate: true })

    return stop
  }, { immediate: true })

  watch(chatId, (newId) => {
    const draftId = toValue(emptyDraftId)
    if (newId && newId !== draftId) {
      // Use store's reloadRoute instead of direct assignment
      chatStore.reloadRoute(newId)
    }
    else if (draftId) {
      chatStore.resetDraftMessage(draftId)
      chatStore.setActive(draftId)
    }
  }, { immediate: true })

  // Watchers
  // watch(emptyDraftId, (newId, prevId) => {
  //   if (prevId) {
  //     chatStore.clearDraftMessage(prevId)
  //   }

  //   if (newId) {
  //     chatStore.resetDraftMessage(newId)
  //     if (!chatId.value || !chatStore.getChatData(newId)) {
  //       chatStore.setActive(newId)
  //     }
  //   }
  // }, { immediate: true })

  if (defaultChatId) {
    watch(defaultChatId, (id) => {
      if (id) {
        chatStore.setActive(id)
      }
    }, { immediate: true })
  }

  // watch(() => chatStore.state.active, (id) => {
  //   if (id) {
  //     return
  //   }

  //   const draftId = emptyDraftId.value || nanoid()
  //   chatStore.setActive(draftId)
  //   chatInfo.value = null
  //   emptyDraftId.value = draftId
  // }, { immediate: true })

  watch(airalogyId, (val) => {
    if (val) {
      const currentChatId = chatId.value
      if (!currentChatId) {
        return
      }
      chatStore.updateAiralogyIdByUuid(currentChatId, val)
    }
  })

  // Update role from chat info if it exists
  watch(() => session.value, (newChatInfo) => {
    if (newChatInfo?.role) {
      selectedRole.value = newChatInfo.role
    }
  }, { immediate: true })

  // Store role in chat info whenever it changes
  watch(selectedRole, (role) => {
    if (chatId.value) {
      chatStore.updateChatRole(chatId.value, role)
    }
  })

  // watch(chatId, async (id) => {
  //   if (!id) {
  //     chatStore.clearActive()
  //     return
  //   }

  //   const chat = await loadChat({ uuid: id } as Chat.History)

  //   if (chat && !chatStore.context[id]) {
  //     chatStore.updateHistoryContext(id, [])
  //   }
  // }, { immediate: true })

  // Watchers for context updates
  watch(session, (newVal) => {
    if (newVal) {
      updateContext(newVal.context || [])
    }
  })

  watch([context, contextDialog], ([currContext, currDialog]) => {
    if (!currContext) {
      currDialog.selected = []
      return
    }

    currDialog.selected = currDialog.selected.filter(id => !currContext.find(it => it.id === id)).concat(currContext.filter(it => !it.removable).map(({ id }) => id))
  })

  // This will be handled by mutations composable
  // watch(chatInfo, (newVal) => {
  //   if (newVal) {
  //     updateContext(newVal.context || [])
  //   }
  // })

  // watch(
  //   history,
  //   (val, prev) => {
  //     if (val.length === 0 && (prev && prev.length === 0)) {
  //       return
  //     }

  //     // Check if current chat exists in history
  //     const currentChatExists = chatId.value && val?.some(chat => chat.uuid === chatId.value)

  //     // Clear chat if:
  //     // 1. History is empty OR
  //     // 2. Current chat ID exists but not found in history
  //     if (!val?.length || (chatId.value && !currentChatExists)) {
  //     // Clear chat info
  //       chatInfo.value = null

  //       // If we're clearing due to history being empty, switch to draft mode
  //       if (!val?.length) {
  //       // Generate new draft ID if needed
  //         if (!emptyDraftId.value) {
  //           emptyDraftId.value = nanoid()
  //         }
  //         chatId.value = undefined
  //       }
  //       // If we're clearing because current chat was not found, just clear the ID
  //       else {
  //         chatId.value = undefined
  //         // Clean up any existing draft
  //         chatStore.clearDraftMessage(emptyDraftId.value)
  //       }
  //     }
  //   },
  //   { flush: "post", immediate: true },
  // )
}
