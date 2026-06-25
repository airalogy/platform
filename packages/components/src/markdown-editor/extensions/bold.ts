import type { ExtensionRenderParams } from "."
import MenuBarItem from "@airalogy/components/markdown-editor/menu-bar-item.vue"
import { $t } from "@airalogy/shared/locales"
import TiptapBold from "@tiptap/extension-bold"
import BoldICon from "~icons/tabler/bold"

const Bold = TiptapBold.extend<{ bubble?: boolean }>({
  addOptions() {
    return {
      ...this.parent?.(),
      renderer({ editor, disabled }: ExtensionRenderParams) {
        return {
          component: MenuBarItem,
          componentProps: computed(() => ({
            command: () => {
              editor.commands.toggleBold()
            },
            isActive: editor.isActive("bold"),
            icon: BoldICon,
            tooltip: $t("editor.extensions.Bold.tooltip"),
            disabled,
          })),
        }
      },
    }
  },
})

export default Bold
