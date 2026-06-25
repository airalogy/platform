import { createStorage } from "@airalogy/shared/utils"

export const LOCAL_CHAT_STORAGE_NAME = "chatStorage" as const
export const chatStorage = createStorage<{
  [LOCAL_CHAT_STORAGE_NAME]: Chat.ChatState
}>("local", null)
