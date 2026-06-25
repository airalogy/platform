import type { ExtensionRenderParams } from "."
import MenuBarItem from "@airalogy/components/markdown-editor/menu-bar-item.vue"
import { $t } from "@airalogy/shared/locales"
import TiptapCodeBlock from "@tiptap/extension-code-block"
import CodeIcon from "~icons/tabler/code"

const CodeBlock = TiptapCodeBlock.extend({
  addOptions() {
    return {
      ...this.parent?.(),
      renderer({ editor, disabled }: ExtensionRenderParams) {
        return {
          component: MenuBarItem,
          componentProps: computed(() => ({
            command: () => {
              editor.commands.toggleCodeBlock()
            },
            isActive: editor.isActive("codeBlock"),
            icon: CodeIcon,
            tooltip: $t("editor.extensions.CodeBlock.tooltip"),
            disabled,
          })),
        }
      },
    }
  },
})

export default CodeBlock
