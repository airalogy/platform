import type { ExtensionRenderParams } from "."
import MenuBarItem from "@airalogy/components/markdown-editor/menu-bar-item.vue"
import { $t } from "@airalogy/shared/locales"

import TiptapTaskList from "@tiptap/extension-task-list"

import ListCheck from "~icons/tabler/list-check"
import TaskItem from "./task-item"

const TaskList = TiptapTaskList.extend({
  addOptions() {
    return {
      ...this.parent?.(),
      renderer({ editor, disabled }: ExtensionRenderParams) {
        return {
          component: MenuBarItem,
          componentProps: computed(() => ({
            command: () => editor.commands.toggleTaskList(),
            isActive: editor.isActive("taskList"),
            icon: ListCheck,
            tooltip: $t("editor.extensions.TodoList.tooltip"),
            disabled,
          })),
        }
      },
    }
  },

  addExtensions() {
    return [TaskItem]
  },
})

export default TaskList
