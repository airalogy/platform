import { useChatStore } from "@airalogy/components/chat/store"
import { downloadAs } from "@airalogy/shared"
import { useDialog, useMessage } from "naive-ui"

export function useExport() {
  const dialog = useDialog()
  const ms = useMessage()
  const chatStore = useChatStore()

  const handleExport = async (uuid: string) => {
    const d = dialog.warning({
      title: "Export Chat",
      content: "Are you sure you want to export this chat?",
      positiveText: "Yes",
      negativeText: "No",
      onPositiveClick: async () => {
        try {
          d.loading = true
          const chatData = chatStore.findSessionByUUID(uuid)

          const jsonString = JSON.stringify(chatData, null, 2)
          const blob = new Blob([jsonString], { type: "application/json" })

          downloadAs(blob, `chat-export-${uuid}.json`)

          ms.success("Export successful")
        }
        catch (error: any) {
          ms.error("Export failed")
        }
        finally {
          d.loading = false
        }
      },
    })
  }

  return {
    handleExport,
  }
}
