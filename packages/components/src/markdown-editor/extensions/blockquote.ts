import type { ExtensionRenderParams } from "."
import MenuBarItem from "@airalogy/components/markdown-editor/menu-bar-item.vue"
import { $t } from "@airalogy/shared/locales"

import TiptapBlockquote from "@tiptap/extension-blockquote"
import BlockquoteIcon from "~icons/tabler/blockquote"

const Blockquote = TiptapBlockquote.extend({
  addOptions() {
    return {
      ...this.parent?.(),
      renderer({ editor, disabled }: ExtensionRenderParams) {
        return {
          component: MenuBarItem,
          componentProps: computed(() => ({
            command: () => {
              editor.commands.toggleBlockquote()
            },
            isActive: editor.isActive("blockquote"),
            icon: BlockquoteIcon,
            tooltip: $t("editor.extensions.Blockquote.tooltip"),
            disabled,
          })),
        }
      },
    }
  },
})

export default Blockquote
