import type { ExtensionRenderParams } from "."
import FontSizeSelect from "@airalogy/components/markdown-editor/modules/font-size-select.vue"
import { Extension } from "@tiptap/core"

import { convertToPX, DEFAULT_FONT_SIZE, DEFAULT_FONT_SIZES } from "../utils/font-size"

export interface FontSizeOptions {
  types: string[]
}

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    fontSize: {
      /**
       * Set the font size
       */
      setFontSize: (fontSize: string) => ReturnType
      /**
       * Unset the font size
       */
      unsetFontSize: () => ReturnType
    }
  }
}

const FontSize = Extension.create<FontSizeOptions>({
  name: "fontSize",

  addOptions() {
    return {
      types: ["textStyle"],
      fontSizes: DEFAULT_FONT_SIZES,
      renderer({ editor, disabled }: ExtensionRenderParams) {
        return {
          component: FontSizeSelect,
          componentProps: {
            editor,
            disabled,
          },
        }
      },
    }
  },

  addGlobalAttributes() {
    return [
      {
        types: this.options.types,
        attributes: {
          fontSize: {
            default: null,
            parseHTML: element => convertToPX(element.style.fontSize) || "",
            renderHTML: (attributes) => {
              if (!attributes.fontSize) {
                return {}
              }

              return {
                style: `font-size: ${attributes.fontSize}px`,
              }
            },
          },
        },
      },
    ]
  },

  addCommands() {
    return {
      setFontSize:
        fontSize =>
          ({ chain }) => {
            return chain().setMark("textStyle", { fontSize }).run()
          },
      unsetFontSize:
        () =>
          ({ chain }) => {
            return chain()
              .setMark("textStyle", { fontSize: DEFAULT_FONT_SIZE })
              .removeEmptyTextStyle()
              .run()
          },
    }
  },
})

export default FontSize
