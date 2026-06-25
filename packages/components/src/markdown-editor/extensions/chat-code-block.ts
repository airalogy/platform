import { mergeAttributes, Node } from "@tiptap/core"
import { VueNodeViewRenderer } from "@tiptap/vue-3"
import CodeBlockComponent from "./chat/code-block.vue"

export const ChatCodeBlockExtension = Node.create({
  name: "ChatCodeBlock",

  group: "block",

  content: "inline*",

  atom: true,

  selectable: true,

  parseHTML() {
    return [
      {
        tag: "code-block",
      },
    ]
  },

  addAttributes() {
    return {
      item: {
        default: "",
      },
      inputId: {
        default: "",
      },
    }
  },

  renderHTML({ HTMLAttributes }) {
    return ["code-block", mergeAttributes(HTMLAttributes), 0]
  },

  addNodeView() {
    return VueNodeViewRenderer(CodeBlockComponent)
  },
})
