import type { Editor } from "@tiptap/core"
import ColorPopover from "@airalogy/components/markdown-editor/modules/color-popover.vue"
import { COLOR_SET } from "@airalogy/components/markdown-editor/utils/color"
import TiptapColor from "@tiptap/extension-color"
import TextStyle from "@tiptap/extension-text-style"

const Color = TiptapColor.extend<{ bubble?: boolean }>({
  addOptions() {
    return {
      ...this.parent?.(),
      colors: COLOR_SET,
      renderer({ editor }: { editor: Editor }) {
        return {
          component: ColorPopover,
          componentProps: {
            editor,
          },
        }
      },
    }
  },

  addExtensions() {
    return [TextStyle]
  },
})

export default Color
