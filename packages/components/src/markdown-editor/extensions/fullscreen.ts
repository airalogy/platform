import type { Editor } from "@tiptap/core"
import FullscreenItem from "@airalogy/components/markdown-editor/modules/fullscreen-item.vue"
import { Extension } from "@tiptap/core"

const Fullscreen = Extension.create({
  name: "fullscreen",

  addOptions() {
    return {
      ...this.parent?.(),
      renderer({ editor }: { editor: Editor }) {
        return {
          component: FullscreenItem,
        }
      },
    }
  },
})

export default Fullscreen
