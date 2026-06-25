import type { ExtensionRenderParams } from "."
import MenuBarItem from "@airalogy/components/markdown-editor/menu-bar-item.vue"

import { $t } from "@airalogy/shared/locales"
import TiptapUnderline from "@tiptap/extension-underline"
import UnderlineIcon from "~icons/tabler/underline"

const Underline = TiptapUnderline.extend<{ bubble?: boolean }>({
  addOptions() {
    return {
      ...this.parent?.(),
      renderer({ editor, disabled }: ExtensionRenderParams) {
        return {
          component: MenuBarItem,
          componentProps: computed(() => ({
            command: () => {
              editor.commands.toggleUnderline()
            },
            isActive: editor.isActive("underline"),
            icon: UnderlineIcon,
            tooltip: $t("editor.extensions.Underline.tooltip"),
            disabled,
          })),
        }
      },
    }
  },
})

export default Underline
