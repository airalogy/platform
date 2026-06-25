import type { ExtensionRenderParams } from "."
import MenuBarItem from "@airalogy/components/markdown-editor/menu-bar-item.vue"

import { $t } from "@airalogy/shared/locales"

import TiptapHistory from "@tiptap/extension-history"

import ArrowBack from "~icons/tabler/arrow-back"
import ArrowForward from "~icons/tabler/arrow-forward"

const History = TiptapHistory.extend({
  addOptions() {
    return {
      ...this.parent?.(),
      renderer({ editor, renderLabel, disabled }: ExtensionRenderParams) {
        return [
          {
            component: MenuBarItem,
            componentProps: {
              command: () => editor.commands.undo(),
              icon: ArrowBack,
              tooltip: $t("editor.extensions.History.tooltip.undo"),
              label: renderLabel ? renderLabel($t, "undo") : undefined,
              disabled,
            },
          },
          {
            component: MenuBarItem,
            componentProps: {
              command: () => editor.commands.redo(),
              icon: ArrowForward,
              tooltip: $t("editor.extensions.History.tooltip.redo"),
              label: renderLabel ? renderLabel($t, "redo") : undefined,
              disabled,
            },
          },
        ]
      },
    }
  },
})

export default History
export { TiptapHistory }
