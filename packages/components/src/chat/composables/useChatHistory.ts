import type { DialogOptions } from "naive-ui"
import type { ChatHistoryOperations, ChatState } from "./types"
import { downloadAs } from "@airalogy/shared/utils"
import { useDialog } from "naive-ui"

export function useChatHistory(state: ChatState): ChatHistoryOperations {
  const { chatStore } = state
  const dialog = useDialog()

  async function loadChat(history: Chat.ChatHistory) {
    if (!history?.uuid)
      return

    const chatItem = chatStore.findSessionByUUID(history.uuid)

    if (chatItem) {
      chatItem.data.forEach((item) => {
        item.editing = false
        item.loading = false
      })
      chatStore.setActive(history.uuid)
      chatStore.reloadRoute(history.uuid)
    }

    return chatItem
  }

  function deleteHistory(uuid: string, type: "dialog" | "popconfirm" = "dialog", options: DialogOptions = {}) {
    if (type === "dialog") {
      return dialog.warning({
        title: "Delete History",
        content: "Are you sure you want to delete this chat history?",
        positiveText: "Yes",
        negativeText: "No",
        onPositiveClick: () => {
          chatStore.deleteHistory(uuid)
        },
        ...options,
      })
    }

    chatStore.deleteHistory(uuid)
  }

  function editHistory(uuid: string, title: string) {
    chatStore.updateHistory(uuid, { title, isEdit: true, time: Date.now() })
  }

  function exportHistory(uuid: string) {
    const chat = chatStore.findSessionByUUID(uuid)
    if (!chat)
      return

    const history = chatStore.state.history.find(h => h.uuid === uuid)
    if (!history)
      return

    const exportData = {
      uuid,
      title: history.title,
      time: history.time,
      messages: chat.data,
    }

    downloadAs(
      JSON.stringify(exportData, null, 2),
      `chat-${history.title}-${new Date().toISOString()}.json`,
    )
  }

  function clearHistory() {
    chatStore.clearHistory()
  }

  function clearMessages() {
    state.messageList.value = []
    state.messageCount.value = 0
  }

  return {
    loadChat,
    deleteHistory,
    editHistory,
    exportHistory,
    clearHistory,
    clearMessages,
  }
}
