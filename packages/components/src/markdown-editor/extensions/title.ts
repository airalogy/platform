import { mergeAttributes, Node } from "@tiptap/core"

const Title = Node.create({
  name: "title",

  // schema
  content: "inline*",

  addOptions() {
    return {
      ...this.parent?.(),
      placeholder: "",
    } as Record<string, any>
  },

  parseHTML() {
    return [{ tag: "h1" }]
  },

  renderHTML({ HTMLAttributes }) {
    return ["h1", mergeAttributes(HTMLAttributes), 0]
  },
})

export default Title
