import type { Editor } from "@tiptap/core"
import HighlightPopover from "@airalogy/components/markdown-editor/modules/highlight-popover.vue"
import TiptapHighlight from "@tiptap/extension-highlight"
import { COLOR_SET } from "../utils/color"

const Highlight = TiptapHighlight.extend<{ bubble?: boolean }>({
  addOptions() {
    return {
      ...this.parent?.(),
      multicolor: true,
      colors: COLOR_SET,
      renderer({ editor }: { editor: Editor }) {
        return {
          component: HighlightPopover,
          componentProps: {
            editor,
          },
        }
      },
    }
  },
})

export default Highlight
