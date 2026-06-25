import type { ExtensionRenderParams } from "."
import MenuBarItem from "@airalogy/components/markdown-editor/menu-bar-item.vue"
import { $t } from "@airalogy/shared/locales"

import { Extension } from "@tiptap/core"
import IndentDecrease from "~icons/tabler/indent-decrease"
import IndentIncrease from "~icons/tabler/indent-increase"
import { createIndentCommand, IndentEnum } from "../utils/indent"

export interface IndentOptions {
  types: string[]
  minIndent: number
  maxIndent: number
}

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    indent: {
      /**
       * Set the indent attribute
       */
      indent: () => ReturnType
      /**
       * Set the dedent attribute
       */
      outdent: () => ReturnType
    }
  }
}

export type IndentAlignment = "indent" | "dedent"

const Indent = Extension.create<IndentOptions>({
  name: "indent",

  addOptions() {
    return {
      types: ["paragraph", "heading", "blockquote"],
      minIndent: IndentEnum.Min,
      maxIndent: IndentEnum.Max,
      renderer({ editor, renderLabel, disabled }: ExtensionRenderParams) {
        return [
          {
            component: MenuBarItem,
            componentProps: computed(() => ({
              command: () => editor.commands.indent(),
              icon: IndentDecrease,
              tooltip: $t("editor.extensions.Indent.buttons.indent.tooltip"),
              label: renderLabel ? renderLabel($t, "indent") : undefined,
              disabled,
            })),
          },
          {
            component: MenuBarItem,
            componentProps: computed(() => ({
              command: () => editor.commands.outdent(),
              icon: IndentIncrease,
              tooltip: $t("editor.extensions.Indent.buttons.dedent.tooltip"),
              label: renderLabel ? renderLabel($t, "dedent") : undefined,
              disabled,
            })),
          },
        ]
      },
    }
  },

  addGlobalAttributes() {
    return [
      {
        types: this.options.types,
        attributes: {
          indent: {
            default: 0,
            parseHTML: (element) => {
              const identAttr = element.getAttribute("data-indent")
              return typeof identAttr === "string" ? Number.parseInt(identAttr, 10) : 0
            },
            renderHTML: (attributes) => {
              if (!attributes.indent) {
                return {}
              }

              return { "data-indent": attributes.indent }
            },
          },
        },
      },
    ]
  },

  addCommands() {
    return {
      indent: () =>
        createIndentCommand({
          delta: IndentEnum.More,
          types: this.options.types,
        }),
      outdent: () =>
        createIndentCommand({
          delta: IndentEnum.Less,
          types: this.options.types,
        }),
    }
  },

  addKeyboardShortcuts() {
    return {
      "Tab": () => this.editor.commands.indent(),
      "Shift-Tab": () => this.editor.commands.outdent(),
    }
  },
})

export default Indent
