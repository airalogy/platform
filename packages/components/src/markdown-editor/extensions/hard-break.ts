import { mergeAttributes, Node } from "@tiptap/core"
import { NodeSelection } from "@tiptap/pm/state"

export interface HardBreakOptions {
  /**
   * Controls if marks should be kept after being split by a hard break.
   * @default true
   * @example false
   */
  keepMarks: boolean

  /**
   * HTML attributes to add to the hard break element.
   * @default {}
   * @example { class: 'foo' }
   */
  HTMLAttributes: Record<string, any>

  /**
   *  List of node types where we don't want Enter to create a hard break
   * @default ["bulletList", "orderedList", "listItem", "codeBlock", "heading", "blockquote"]
   */
  excludedNodes?: string[]
}

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    hardBreak: {
      /**
       * Add a hard break
       * @example editor.commands.setHardBreak()
       */
      setHardBreak: () => ReturnType
    }
  }
}

/**
 * This extension allows you to insert hard breaks.
 * @see https://www.tiptap.dev/api/nodes/hard-break
 */
export const HardBreak = Node.create<HardBreakOptions>({
  name: "hardBreak",

  addOptions() {
    return {
      keepMarks: true,
      HTMLAttributes: {},

      excludedNodes: [
        // Lists
        "bulletList",
        "orderedList",
        "listItem",
        "taskList",
        "taskItem",

        // Code blocks and preformatted text
        "codeBlock",
        "fence",
        "pre",

        // Block elements
        "heading",
        "blockquote",
        // "paragraph" is NOT excluded - Enter creates hardBreak in paragraph

        // Tables
        "table",
        "tableRow",
        "tableCell",
        "tableHeader",

        // Custom block elements that might be present
        "customBlock",
        "horizontalRule",

        // Image nodes
        // "airalogyImage",
      ],
    }
  },

  inline: true,

  group: "inline",

  selectable: false,

  linebreakReplacement: true,

  parseHTML() {
    return [
      { tag: "br" },
    ]
  },

  renderHTML({ HTMLAttributes }) {
    return ["br", mergeAttributes(this.options.HTMLAttributes, HTMLAttributes)]
  },

  renderText() {
    return "\n"
  },

  // Serialize hardBreak as single newline (or <br> in tables)
  // With breaks: true, single newline will be parsed back as <br>
  // This creates seamless experience: one newline = one line break in both modes
  addStorage() {
    return {
      markdown: {
        serialize(state: any, node: any, parent: any, index: number) {
          // Check if there are more non-hardBreak nodes after this one
          for (let i = index + 1; i < parent.childCount; i++) {
            if (parent.child(i).type !== node.type) {
              // In tables, use <br> to avoid breaking table format
              // Outside tables, use newline for clean markdown
              if (state.inTable) {
                state.write("<br>")
              }
              else {
                state.write("\n")
              }
              return
            }
          }
        },
        parse: {
          // handled by markdown-it
        },
      },
    }
  },

  addCommands() {
    return {
      setHardBreak: () => ({
        commands,
        chain,
        state,
        editor,
      }) => {
        return commands.first([
          () => commands.exitCode(),
          () => commands.command(() => {
            const { selection, storedMarks } = state

            if (selection.$from.parent.type.spec.isolating) {
              return false
            }

            const { keepMarks } = this.options
            const { splittableMarks } = editor.extensionManager
            const marks = storedMarks
              || (selection.$to.parentOffset && selection.$from.marks())

            return chain()
              .insertContent({ type: this.name })
              .command(({ tr, dispatch }) => {
                if (dispatch && marks && keepMarks) {
                  const filteredMarks = marks
                    .filter(mark => splittableMarks.includes(mark.type.name))

                  tr.ensureMarks(filteredMarks)
                }

                return true
              })
              .run()
          }),
        ])
      },
    }
  },

  addKeyboardShortcuts() {
    return {
      // Enter creates hardBreak (inline line break)
      "Enter": () => {
        const editor = this.editor
        const { selection } = editor.state

        // Check if we're in a node selection first
        if (selection instanceof NodeSelection && selection.node.type && this.options.excludedNodes?.includes(selection.node.type.name)) {
          return false
        }

        const pos = selection.$from
        let depth = pos.depth
        let isInExcludedNode = false

        // Walk up the node tree to check ancestors
        while (depth > 0) {
          const node = pos.node(depth)
          if (this.options.excludedNodes?.includes(node.type.name)) {
            isInExcludedNode = true
            break
          }
          depth--
        }

        // If in excluded node, don't create hardBreak
        if (isInExcludedNode) {
          return false
        }

        // Otherwise create hardBreak
        return editor.commands.setHardBreak()
      },
      "Mod-Enter": () => this.editor.commands.setHardBreak(),
      "Shift-Enter": () => this.editor.commands.setHardBreak(),
    }
  },
})

export default HardBreak
