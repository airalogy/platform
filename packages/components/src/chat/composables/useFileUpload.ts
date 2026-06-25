import type { UploadCustomRequestOptions } from "naive-ui"
import type { ChatProviderContext } from "../providers/useChatProvider"
import { useClosableMessage } from "@airalogy/composables"
import { nanoid } from "nanoid"
import { formatErrorMessage } from "./utils"

export function useFileUpload(state: any, providerContext: ChatProviderContext) {
  const { chatStore, chatId, emptyDraftId } = state
  const { uploadAttachment } = providerContext

  // Function to handle file uploads
  async function handleUpload(options: UploadCustomRequestOptions) {
    // Create message instance inside the function to avoid accumulation
    const showMessage = useClosableMessage()

    const currentChatId = chatId.value || emptyDraftId.value
    if (!currentChatId) {
      showMessage.error("No chat ID")
      return false
    }
    const { file: fileInfo, onFinish, onError } = options
    if (!fileInfo.file) {
      showMessage.error("No file")
      return false
    }

    const { size, type } = fileInfo.file

    const maxSize = 10 * 1024 * 1024 // 10MB limit

    if (size && size > maxSize) {
      showMessage.error("File size cannot exceed 10MB")
      return false
    }

    const allowedTypes = ["image/jpeg", "image/jpg", "image/png", "image/gif", "application/pdf"]
    if (!allowedTypes.includes(type || "")) {
      showMessage.error("Only images (JPG, PNG, GIF) and PDF files are allowed")
      return false
    }

    const fileId = String(fileInfo.id || nanoid())
    const previewUrl = URL.createObjectURL(fileInfo.file)
    const newFileInfo: Chat.Attachment = {
      ...fileInfo,
      id: fileId,
      name: fileInfo.name || fileInfo.file.name,
      status: "uploading",
      percentage: 0,
      url: previewUrl,
      isUploading: true,
      serverId: undefined,
    }

    // Store the file in the chat store
    chatStore.addAttachment(currentChatId, newFileInfo)

    try {
      const upload = uploadAttachment?.value
      if (!upload) {
        throw new Error("Attachment upload is not configured")
      }

      const uploadedFile = await upload(fileInfo.file)
      if (!uploadedFile?.id) {
        throw new Error("Attachment upload did not return a file id")
      }

      chatStore.updateAttachmentServerId(currentChatId, fileId, {
        serverId: uploadedFile.id,
        url: uploadedFile.url || previewUrl,
        name: uploadedFile.filename || newFileInfo.name,
      })

      if (uploadedFile.url) {
        URL.revokeObjectURL(previewUrl)
      }

      onFinish()
      return true
    }
    catch (error) {
      chatStore.removeAttachment(currentChatId, fileId)
      onError()
      showMessage.error(formatErrorMessage(error))
      return false
    }
  }

  function removeAttachment(fileId: string) {
    const currentChatId = chatId.value || emptyDraftId.value
    if (!currentChatId) {
      return
    }

    chatStore.removeAttachment(currentChatId, fileId, false)
  }

  return {
    handleUpload,
    removeAttachment,
  }
}
