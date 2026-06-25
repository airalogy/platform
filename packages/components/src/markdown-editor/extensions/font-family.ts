import type { ExtensionRenderParams } from "."
import FontFamilySelect from "@airalogy/components/markdown-editor/modules/font-family-select.vue"
import { DEFAULT_FONT_FAMILY_MAP } from "@airalogy/components/markdown-editor/utils/font-type"
import { Extension } from "@tiptap/core"

export interface FontFamilyOptions {
  types: string[]
}

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    fontFamily: {
      /**
       * Set the font family
       */
      setFontFamily: (fontFamily: string) => ReturnType
      /**
       * Unset the font family
       */
      unsetFontFamily: () => ReturnType
    }
  }
}

const FontFamily = Extension.create<FontFamilyOptions>({
  name: "fontFamily",

  addOptions() {
    return {
      types: ["textStyle"],
      fontFamilyMap: DEFAULT_FONT_FAMILY_MAP,
      renderer({ editor, disabled }: ExtensionRenderParams) {
        return {
          component: FontFamilySelect,
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
          fontFamily: {
            default: null,
            parseHTML: element => element.style.fontFamily.replace(/['"]/g, ""),
            renderHTML: (attributes) => {
              const { fontFamily } = attributes
              if (!fontFamily) {
                return {}
              }

              return {
                style: `font-family: ${fontFamily}`,
              }
            },
          },
        },
      },
    ]
  },

  addCommands() {
    return {
      setFontFamily:
        fontFamily =>
          ({ chain }) => {
            return chain().setMark("textStyle", { fontFamily }).run()
          },

      unsetFontFamily:
        () =>
          ({ chain }) => {
            return chain().setMark("textStyle", { fontFamily: null }).removeEmptyTextStyle().run()
          },
    }
  },
})

export default FontFamily
