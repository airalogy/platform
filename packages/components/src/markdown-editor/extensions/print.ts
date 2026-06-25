import type { ExtensionRenderParams } from "."

import MenuBarItem from "@airalogy/components/markdown-editor/menu-bar-item.vue"

import { $t } from "@airalogy/shared/locales"
import { Extension } from "@tiptap/core"

import Printer from "~icons/tabler/printer"
import { printEditorContent } from "../utils/print"

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    print: {
      /**
       * print the editor content
       */
      print: () => ReturnType
    }
  }
}

const Print = Extension.create({
  name: "print",

  addOptions() {
    return {
      renderer({ editor, disabled }: ExtensionRenderParams) {
        return {
          component: MenuBarItem,
          componentProps: {
            command: () => editor.commands.print(),
            icon: Printer,
            tooltip: $t("editor.extensions.Print.tooltip"),
            disabled,
          },
        }
      },
    }
  },

  addCommands() {
    return {
      print() {
        return ({ view }) => printEditorContent(view)
      },
    }
  },

  addKeyboardShortcuts() {
    return {
      "Mod-p": () => this.editor.commands.print(),
    }
  },
})

export default Print
