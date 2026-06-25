import type { ExtensionRenderParams } from "."
import MenuBarItem from "@airalogy/components/markdown-editor/menu-bar-item.vue"
import { $t } from "@airalogy/shared/locales"
import TiptapHorizontalRule from "@tiptap/extension-horizontal-rule"
import HorizontalRuleIcon from "~icons/radix-icons/divider-horizontal"

const HorizontalRule = TiptapHorizontalRule.extend({
  addOptions() {
    return {
      ...this.parent?.(),
      renderer({ editor, disabled }: ExtensionRenderParams) {
        return {
          component: MenuBarItem,
          componentProps: {
            command: () => editor.commands.setHorizontalRule(),
            icon: HorizontalRuleIcon,
            tooltip: $t("editor.extensions.HorizontalRule.tooltip"),
            disabled,
          },
        }
      },
    }
  },
})

export default HorizontalRule
