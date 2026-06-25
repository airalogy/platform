import type { ChainedCommands, Editor, UnionCommands } from "@tiptap/core"
import MenuBarItem from "@airalogy/components/markdown-editor/menu-bar-item.vue"
import { $t } from "@airalogy/shared/locales"
import { Extension } from "@tiptap/core"
import ClearFormatting from "~icons/tabler/clear-formatting"

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    formatClear: {
      formatClear: () => ReturnType
    }
  }
}
const commandsMap: Record<string, keyof UnionCommands> = {
  bold: "unsetBold",
  italic: "unsetItalic",
  underline: "unsetUnderline",
  strike: "unsetStrike",
  link: "unsetLink",
  fontFamily: "unsetFontFamily",
  fontSize: "unsetFontSize",
  color: "unsetColor",
  highlight: "unsetHighlight",
  textAlign: "unsetTextAlign",
  lineHeight: "unsetLineHeight",
}
const commandEntries = Object.entries(commandsMap)
const FormatClear = Extension.create({
  name: "formatClear",

  addCommands() {
    return {
      formatClear:
        () =>
          ({ editor }) => {
            const chainedCommand: ChainedCommands = commandEntries.reduce<ChainedCommands>(
              (chain, [name, command]) => {
                const extension = editor.extensionManager.extensions.find(e => e.name === name)
                if (extension) {
                  return (chain[command] as () => ChainedCommands)()
                }
                return chain
              },
              editor.chain(),
            )

            return chainedCommand.focus().run()
          },
    }
  },

  addOptions() {
    return {
      ...this.parent?.(),
      renderer({ editor }: { editor: Editor }) {
        return {
          component: MenuBarItem,
          componentProps: {
            command: () => {
              editor.commands.formatClear()
            },
            icon: ClearFormatting,
            tooltip: $t("editor.extensions.FormatClear.tooltip"),
          },
        }
      },
    }
  },
})

export default FormatClear
