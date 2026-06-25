import type { ExtensionRenderParams } from "."
import MenuBarItem from "@airalogy/components/markdown-editor/menu-bar-item.vue"
import { $t } from "@airalogy/shared/locales"
import { Extension } from "@tiptap/core"
import MarkdownIcon from "~icons/tabler/markdown"
import RawIcon from "~icons/tabler/pencil"

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    rawContent: {
      /**
       * Toggle raw content mode
       */
      toggleRawContent: () => ReturnType
      /**
       * Set raw content mode
       */
      setRawContent: (isRaw: boolean) => ReturnType
    }
  }
}

const Raw = Extension.create<{ bubble?: boolean }>({
  name: "rawContent",
  addOptions() {
    return {
      ...this.parent?.(),
      renderer({ editor, disabled }: ExtensionRenderParams) {
        return {
          component: MenuBarItem,
          componentProps: computed(() => ({
            command: () => {
              editor.commands.toggleRawContent()
            },
            isActive: editor.storage.rawContent?.isRaw || false,
            // Show current state, not next state
            icon: editor.storage.rawContent?.isRaw ? MarkdownIcon : RawIcon,
            tooltip: editor.storage.rawContent?.isRaw ? $t("editor.extensions.Raw.markdown.tooltip") : $t("editor.extensions.Raw.richText.tooltip"),
            label: editor.storage.rawContent?.isRaw ? $t("editor.extensions.Raw.markdown.title") : $t("editor.extensions.Raw.richText.title"),
          })),
        }
      },
    }
  },
  addCommands() {
    return {
      toggleRawContent: () => ({ editor }) => {
        const newValue = !editor.storage.rawContent.isRaw
        editor.storage.rawContent.isRaw = newValue
        return true
      },
      setRawContent: isRaw => ({ editor }) => {
        editor.storage.rawContent.isRaw = isRaw
        return true
      },
    }
  },
  addStorage() {
    return {
      isRaw: false,
    }
  },
})

export default Raw
