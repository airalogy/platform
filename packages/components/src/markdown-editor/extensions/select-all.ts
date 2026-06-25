import type { ExtensionRenderParams } from "."
import MenuBarItem from "@airalogy/components/markdown-editor/menu-bar-item.vue"
import { $t } from "@airalogy/shared/locales"

import { Extension } from "@tiptap/core"
import ArrowAutofitRight from "~icons/tabler/arrow-autofit-right"

const SelectAll = Extension.create({
  name: "selectAll",

  addOptions() {
    return {
      ...this.parent?.(),
      renderer({ editor, disabled }: ExtensionRenderParams) {
        return {
          component: MenuBarItem,
          componentProps: {
            command: () => editor.commands.selectAll(),
            icon: ArrowAutofitRight,
            tooltip: $t("editor.extensions.SelectAll.tooltip"),
            disabled,
          },
        }
      },
    }
  },
})

export default SelectAll
