import type { NodeSpec } from "@tiptap/pm/model"
import { mergeAttributes, Node } from "@tiptap/core"

/**
 * Converts a ProseMirror NodeSpec to a Tiptap Node extension
 * @param name The name of the node
 * @param spec The NodeSpec definition
 * @param options Additional options for the Tiptap extension
 * @returns A Tiptap Node extension
 */
export function nodeSpecToExtension(
  name: string,
  spec: NodeSpec,
  options: {
    HTMLAttributes?: Record<string, any>
    addOptions?: () => Record<string, any>
    addCommands?: () => Record<string, any>
    addKeyboardShortcuts?: () => Record<string, any>
    addNodeView?: () => any
  } = {},
) {
  return Node.create({
    name,

    // Map NodeSpec content to Tiptap content
    content: spec.content as string,

    // Map NodeSpec marks to Tiptap marks
    marks: spec.marks as string,

    // Map NodeSpec group to Tiptap group
    group: spec.group as string,

    // Map other properties
    inline: spec.inline || false,
    atom: spec.atom || false,
    selectable: spec.selectable !== false,
    draggable: spec.draggable || false,
    code: !!spec.code,

    // Handle isolating property
    defining: spec.defining || spec.isolating || false,

    // Add tableRole if present
    ...(spec.tableRole ? { tableRole: spec.tableRole } : {}),

    // Add custom options
    addOptions() {
      return {
        HTMLAttributes: {},
        ...options.addOptions?.() || {},
      }
    },

    // Map attributes
    addAttributes() {
      if (!spec.attrs)
        return {}

      const attrs: Record<string, any> = {}

      Object.entries(spec.attrs).forEach(([name, attr]) => {
        attrs[name] = {
          default: attr.default,
          parseHTML: (element: HTMLElement) => element.getAttribute(name) || attr.default,
          renderHTML: (attributes: Record<string, string>) => {
            if (attributes[name] !== attr.default) {
              return { [name]: attributes[name] }
            }
            return {}
          },
        }
      })

      return attrs
    },

    // Map parseDOM
    parseHTML() {
      return spec.parseDOM || []
    },

    // Map toDOM
    renderHTML({ HTMLAttributes, node }) {
      if (!spec.toDOM)
        return ["div", 0]

      const rendered = spec.toDOM(node)

      // If rendered is an array, merge attributes at position 1
      if (Array.isArray(rendered) && rendered.length > 1) {
        const [tag, attrs, ...rest] = rendered

        if (typeof attrs === "object" && attrs !== null && !Array.isArray(attrs)) {
          return [tag, mergeAttributes(options.HTMLAttributes || {}, attrs, HTMLAttributes), ...rest]
        }

        return [tag, mergeAttributes(options.HTMLAttributes || {}, HTMLAttributes), attrs, ...rest]
      }

      return rendered
    },

    // Add custom commands if provided
    ...(options.addCommands ? { addCommands: options.addCommands } : {}),

    // Add custom keyboard shortcuts if provided
    ...(options.addKeyboardShortcuts ? { addKeyboardShortcuts: options.addKeyboardShortcuts } : {}),

    // Add custom node view if provided
    ...(options.addNodeView ? { addNodeView: options.addNodeView } : {}),
  })
}
