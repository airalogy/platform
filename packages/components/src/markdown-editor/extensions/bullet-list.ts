import type { ExtensionRenderParams } from "."
import MenuBarItem from "@airalogy/components/markdown-editor/menu-bar-item.vue"
import { $t } from "@airalogy/shared/locales"
import TiptapBulletList from "@tiptap/extension-bullet-list"
import ListICon from "~icons/tabler/list"

const BulletList = TiptapBulletList.extend({
  addOptions() {
    return {
      ...this.parent?.(),
      renderer({ editor, disabled }: ExtensionRenderParams) {
        return {
          component: MenuBarItem,
          componentProps: computed(() => ({
            command: () => {
              editor.commands.toggleBulletList()
            },
            isActive: editor.isActive("bulletList"),
            icon: ListICon,
            tooltip: $t("editor.extensions.BulletList.tooltip"),
            disabled,
          })),
        }
      },
    }
  },
})

export default BulletList
