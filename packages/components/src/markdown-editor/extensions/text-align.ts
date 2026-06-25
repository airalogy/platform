import type { ExtensionRenderParams, RendererSpec } from "."

import MenuBarItem from "@airalogy/components/markdown-editor/menu-bar-item.vue"
import { $t } from "@airalogy/shared/locales"
import TiptapTextAlign from "@tiptap/extension-text-align"
import AlignCenter from "~icons/tabler/align-center"

import AlignJustified from "~icons/tabler/align-justified"
import AlignLeft from "~icons/tabler/align-left"
import AlignRight from "~icons/tabler/align-right"

export type TextAlignAlignment = "left" | "center" | "right" | "justify"

const iconRecord: Record<TextAlignAlignment, Component> = {
  left: AlignLeft,
  center: AlignCenter,
  right: AlignRight,
  justify: AlignJustified,
}

const TextAlign = TiptapTextAlign.extend({
  addOptions() {
    return {
      ...this.parent?.(),
      types: ["heading", "paragraph", "list_item", "title"],
      renderer({
        editor,
        extension,
        renderLabel,
        disabled,
      }: ExtensionRenderParams<{ alignments: TextAlignAlignment[] }>) {
        return extension.options.alignments.map((alignment): RendererSpec => (
          {
            component: MenuBarItem,
            componentProps: computed(() => ({
              command: () => {
                if (editor.isActive({ textAlign: alignment })) {
                  editor.commands.unsetTextAlign()
                }
                else {
                  editor.commands.setTextAlign(alignment)
                }
              },
              isActive: alignment === "left" ? false : editor.isActive({ textAlign: alignment }),
              icon: iconRecord[alignment],
              tooltip: $t(`editor.extensions.TextAlign.buttons.align_${alignment}.tooltip`),
              label: renderLabel ? renderLabel($t, alignment) : undefined,
              disabled,
            })),
          }
        ))
      },
    }
  },
})

export default TextAlign
