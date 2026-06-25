import type { ExtensionRenderParams } from "."
import MenuBarItem from "@airalogy/components/markdown-editor/menu-bar-item.vue"
import { $t } from "@airalogy/shared/locales"

import TiptapItalic from "@tiptap/extension-italic"
import ItalicIcon from "~icons/tabler/italic"

const Italic = TiptapItalic.extend<{ bubble?: boolean }>({
  addOptions() {
    return {
      ...this.parent?.(),
      renderer({ editor, disabled }: ExtensionRenderParams) {
        return {
          component: MenuBarItem,
          componentProps: computed(() => ({
            command: () => editor.commands.toggleItalic(),
            isActive: editor.isActive("italic"),
            icon: ItalicIcon,
            tooltip: $t("editor.extensions.Italic.tooltip"),
            disabled,
          })),
        }
      },
    }
  },
})

export default Italic
