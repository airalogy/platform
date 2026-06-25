import type { Editor } from "@tiptap/core"
import type { Node } from "@tiptap/pm/model"
import type { Transaction } from "@tiptap/pm/state"
import { isUrl } from "@airalogy/shared/utils"
import { computed, type ComputedRef } from "vue"

interface UseImageActionsProps {
  editor: Editor
  node: Node
  src: string
  onViewClick: (value: boolean) => void
}

export interface ImageActionHandlers {
  onView?: () => void
  onDownload?: () => void
  onCopy?: () => void
  onCopyLink?: () => void
  onRemoveImg?: () => void
}

export function useImageActions(props: ComputedRef<UseImageActionsProps>) {
  const isLink = computed(() => isUrl(toValue(props).src))

  const onView = () => {
    const { onViewClick } = toValue(props)
    onViewClick(true)
  }

  const onDownload = () => {
    const { editor, src } = toValue(props)
    editor.commands.downloadImage({ src, action: "download" })
  }

  const onCopy = () => {
    const { editor, src } = toValue(props)
    editor.commands.copyImage({ src, action: "copyImage" })
  }

  const onCopyLink = () => {
    const { editor, src } = toValue(props)
    editor.commands.copyLink({ src, action: "copyLink" })
  }

  const onRemoveImg = () => {
    const { editor } = toValue(props)
    editor.commands.command(
      ({ tr, dispatch }: { tr: Transaction, dispatch?: (tr: Transaction) => void }) => {
        const { selection } = tr
        const nodeAtSelection = tr.doc.nodeAt(selection.from)

        if (nodeAtSelection && nodeAtSelection.type.name === "image") {
          if (dispatch) {
            tr.deleteSelection()
            return true
          }
        }
        return false
      },
    )
  }
  const onCopyId = () => {
    const { editor, src, node } = toValue(props)
    editor.commands.copyImage({ src, id: node.attrs.id, action: "copyId" })
  }

  return { isLink, onView, onDownload, onCopy, onCopyLink, onRemoveImg, onCopyId }
}
