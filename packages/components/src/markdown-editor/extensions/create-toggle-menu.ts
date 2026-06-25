import type { Editor } from "@tiptap/vue-3"
import type { ExtensionRenderParams } from "."
import { Extension } from "@tiptap/core"
import TextIcon from "~icons/tabler/text-plus"
import MenuBarItem from "../menu-bar-item.vue"

export interface ToggleModeOptions {
  isExpandedMode: boolean
}

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    toggleMode: {
      /**
       * Toggle between one line and markdown editor mode
       */
      toggleExpandedMode: () => ReturnType
      /**
       * Set editor mode
       */
      setExpandedMode: (isExpandedMode: boolean) => ReturnType
    }
  }
}

export function createToggleMode(callback: (editor: Editor) => void) {
  return Extension.create<ToggleModeOptions>({
    name: "toggleMode",

    addOptions() {
      return {
        isExpandedMode: false,
        renderer({ editor, disabled }: ExtensionRenderParams) {
          return {
            component: MenuBarItem,
            componentProps: computed(() => ({
              command: () => {
                callback(editor)
              },
              isActive: editor.storage.toggleMode?.isExpandedMode || false,
              icon: TextIcon,
              tooltip: editor.storage.toggleMode?.isExpandedMode
                ? "Switch to markdown editor"
                : "Switch to single line input",
              name: "toggleMode",
              disabled,
            })),
          }
        },
      }
    },

    addStorage() {
      return {
        isExpandedMode: this.options.isExpandedMode,
      }
    },
  })
}
