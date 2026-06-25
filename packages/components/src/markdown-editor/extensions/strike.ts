import type { ExtensionRenderParams } from "."
import MenuBarItem from "@airalogy/components/markdown-editor/menu-bar-item.vue"
import { $t } from "@airalogy/shared/locales"

import TiptapStrike from "@tiptap/extension-strike"
import Strikethrough from "~icons/tabler/strikethrough"

const Strike = TiptapStrike.extend<{ bubble?: boolean }>({
  addOptions() {
    return {
      ...this.parent?.(),
      renderer({ editor, disabled }: ExtensionRenderParams) {
        return {
          component: MenuBarItem,
          componentProps: computed(() => ({
            command: () => {
              editor.commands.toggleStrike()
            },
            isActive: editor.isActive("strike"),
            icon: Strikethrough,
            tooltip: $t("editor.extensions.Strike.tooltip"),
            disabled,
          })),
        }
      },
    }
  },
})

export default Strike
