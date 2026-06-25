import type { ExtensionRenderParams } from "."
import HeadingSelect from "@airalogy/components/markdown-editor/modules/heading-select.vue"
import TiptapHeading, { type HeadingOptions } from "@tiptap/extension-heading"

const Heading = TiptapHeading.extend<{ bubble?: boolean, level: 1 | 2 | 3 | 4 | 5 }>({
  addOptions() {
    return {
      ...this.parent?.(),
      renderer({ editor, extension, disabled }: ExtensionRenderParams<HeadingOptions>) {
        return {
          component: HeadingSelect,
          componentProps: computed(() => ({
            levels: extension.options.levels,
            editor,
            disabled,
          })),
        }
      },
    }
  },
})

export default Heading
