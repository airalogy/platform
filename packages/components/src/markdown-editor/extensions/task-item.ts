import TaskItemView from "@airalogy/components/markdown-editor/modules/task-item-view.vue"
import { mergeAttributes } from "@tiptap/core"
import TiptapTaskItem from "@tiptap/extension-task-item"

import { VueNodeViewRenderer } from "@tiptap/vue-3"

const TaskItem = TiptapTaskItem.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      done: {
        default: false,
        parseHTML: element => element.getAttribute("data-done") === "true",
      },
    }
  },

  renderHTML({ node, HTMLAttributes }) {
    const { done } = node.attrs
    return [
      "li",
      mergeAttributes(this.options.HTMLAttributes, HTMLAttributes, {
        "data-type": this.name,
      }),
      // naive checkbox instance
      [
        "span",
        {
          contenteditable: "false",
        },
        [
          "span",
          {
            class: `tiptap-checkbox ${done ? "is-checked" : ""}`,
            style: "pointer-events: none;",
          },
          [
            "span",
            { class: `tiptap-checkbox__input ${done ? "is-checked" : ""}` },
            ["span", { class: "el-checkbox__inner" }],
          ],
        ],
      ],
      ["div", { class: "todo-content" }, 0],
    ]
  },

  addNodeView() {
    return VueNodeViewRenderer(TaskItemView)
  },
})

export default TaskItem
