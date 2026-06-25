import type { ExtensionRenderParams } from "."
import MenuBarItem from "@airalogy/components/markdown-editor/menu-bar-item.vue"
import { $t } from "@airalogy/shared/locales"
import { Extension } from "@tiptap/core"
import CollapseIcon from "~icons/tabler/layout-sidebar-left-collapse"
import ExpandIcon from "~icons/tabler/layout-sidebar-left-expand"

export interface CompactMenuOptions {
  isCompact: boolean
}

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    compactMenu: {
      /**
       * Toggle compact menu mode
       */
      toggleCompactMenu: () => ReturnType
      /**
       * Set compact menu mode
       */
      setCompactMenu: (isCompact: boolean) => ReturnType
    }
  }
}

export const CompactMenu = Extension.create<CompactMenuOptions>({
  name: "compactMenu",

  addOptions() {
    return {
      isCompact: true,
      renderer({ editor, disabled }: ExtensionRenderParams) {
        return {
          component: MenuBarItem,
          componentProps: computed(() => ({
            command: () => {
              editor.commands.toggleCompactMenu()
            },
            isActive: !editor.storage.compactMenu?.isCompact,
            icon: editor.storage.compactMenu?.isCompact ? ExpandIcon : CollapseIcon,
            tooltip: editor.storage.compactMenu?.isCompact ? $t("editor.extensions.Uncollapsed.tooltip") : $t("editor.extensions.Collapsed.tooltip"),
            name: "compactMenu",
            disabled,
          })),
        }
      },
    }
  },

  addStorage() {
    return {
      isCompact: this.options.isCompact,
    }
  },

  addCommands() {
    return {
      toggleCompactMenu: () => ({ editor }) => {
        editor.storage.compactMenu.isCompact = !editor.storage.compactMenu.isCompact
        return true
      },
      setCompactMenu: isCompact => ({ editor }) => {
        editor.storage.compactMenu.isCompact = isCompact
        return true
      },
    }
  },

})

export default CompactMenu
