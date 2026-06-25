import type { ExtensionRenderParams } from "."
import MenuBarItem from "@airalogy/components/markdown-editor/menu-bar-item.vue"
import { $t } from "@airalogy/shared/locales"

import TiptapOrderedList from "@tiptap/extension-ordered-list"
import ListNumbers from "~icons/tabler/list-numbers"

const OrderedList = TiptapOrderedList.extend({
  addOptions() {
    return {
      ...this.parent?.(),
      renderer({ editor, disabled }: ExtensionRenderParams) {
        return {
          component: MenuBarItem,
          componentProps: computed(() => ({
            command: () => editor.commands.toggleOrderedList(),
            isActive: editor.isActive("orderedList"),
            icon: ListNumbers,
            tooltip: $t("editor.extensions.OrderedList.tooltip"),
            disabled,
          })),
        }
      },
    }
  },
})

export default OrderedList
