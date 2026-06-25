// Helper for creating a schema that supports tables.

import type {
  AttributeSpec,
  Attrs,
  NodeSpec,
  Node as ProseMirrorNode,
} from "@tiptap/pm/model"
import type { CellAttributes, MutableAttrs } from "@tiptap/pm/tables"
import type { CellAttrs } from "./utils"
import { Node } from "@tiptap/core"

function getCellAttrs(dom: HTMLElement | string, extraAttrs: Attrs): Attrs {
  if (typeof dom === "string") {
    return {}
  }

  const widthAttr = dom.getAttribute("data-colwidth")
  const widths
    = widthAttr && /^\d+(?:,\d+)*$/.test(widthAttr)
      ? widthAttr.split(",").map(s => Number(s))
      : null
  const colspan = Number(dom.getAttribute("colspan") || 1)
  const result: MutableAttrs = {
    colspan,
    rowspan: Number(dom.getAttribute("rowspan") || 1),
    colwidth: widths && widths.length === colspan ? widths : null,
  } satisfies CellAttrs
  for (const prop in extraAttrs) {
    const getter = extraAttrs[prop].getFromDOM
    const value = getter && getter(dom)
    if (value != null) {
      result[prop] = value
    }
  }
  return result
}

function setCellAttrs(node: ProseMirrorNode, extraAttrs: Attrs): Attrs {
  const attrs: MutableAttrs = {}
  if (node.attrs.colspan !== 1)
    attrs.colspan = node.attrs.colspan
  if (node.attrs.rowspan !== 1)
    attrs.rowspan = node.attrs.rowspan
  if (node.attrs.colwidth)
    attrs["data-colwidth"] = node.attrs.colwidth.join(",")
  for (const prop in extraAttrs) {
    const setter = extraAttrs[prop].setDOMAttr
    if (setter)
      setter(node.attrs[prop], attrs)
  }
  return attrs
}

/**
 * @public
 */
export interface TableNodesOptions {
  /**
   * A group name (something like `"block"`) to add to the table
   * node type.
   */
  tableGroup?: string

  /**
   * The content expression for table cells.
   */
  cellContent: string

  /**
   * Additional attributes to add to cells. Maps attribute names to
   * objects with the following properties:
   */
  cellAttributes: { [key: string]: CellAttributes }
}

/**
 * @public
 */
export type TableNodes = Record<
  | "table"
  | "table_caption"
  | "table_head"
  | "table_body"
  | "table_foot"
  | "table_row"
  | "table_cell"
  | "table_header",
  NodeSpec
>

/**
 * This function creates a set of [node
 * specs](http://prosemirror.net/docs/ref/#model.SchemaSpec.nodes) for
 * `table`, `table_caption`, `table_head`, `table_body`, `table_foot`,
 * `table_row`, `table_cell` and `table_header` nodes types as used
 * by this module.
 * The result can then be added to the set of nodes when
 * creating a schema.
 *
 * @public
 */
export function tableProseMirrorNodes(options: TableNodesOptions): TableNodes {
  const extraAttrs = options.cellAttributes || {}
  const cellAttrs: Record<string, AttributeSpec> = {
    colspan: { default: 1 },
    rowspan: { default: 1 },
    colwidth: { default: null },
  }

  for (const prop in extraAttrs)
    cellAttrs[prop] = { default: extraAttrs[prop].default }

  return {
    table: {
      content: "table_caption? table_head? table_body* table_foot?",
      tableRole: "table",
      isolating: true,
      group: options.tableGroup,
      parseDOM: [{ tag: "table" }],
      toDOM() {
        return ["table", 0]
      },
    },
    table_caption: {
      content: "block+",
      tableRole: "caption",
      isolating: true,
      parseDOM: [{ tag: "caption" }],
      toDOM() {
        return ["caption", 0]
      },
    },
    table_head: {
      content: "table_row+",
      tableRole: "head",
      isolating: true,
      parseDOM: [{ tag: "thead" }],
      toDOM() {
        return ["thead", 0]
      },
    },
    table_foot: {
      content: "table_row+",
      tableRole: "foot",
      isolating: true,
      parseDOM: [{ tag: "tfoot" }],
      toDOM() {
        return ["tfoot", 0]
      },
    },
    table_body: {
      content: "table_row+",
      tableRole: "body",
      isolating: true,
      parseDOM: [{ tag: "tbody" }],
      toDOM() {
        return ["tbody", 0]
      },
    },
    table_row: {
      content: "(table_cell | table_header)*",
      tableRole: "row",
      parseDOM: [{ tag: "tr" }],
      toDOM() {
        return ["tr", 0]
      },
    },
    table_cell: {
      content: options.cellContent,
      attrs: cellAttrs,
      tableRole: "cell",
      isolating: true,
      parseDOM: [
        { tag: "td", getAttrs: dom => getCellAttrs(dom, extraAttrs) },
      ],
      toDOM(node) {
        return ["td", setCellAttrs(node, extraAttrs), 0]
      },
    },
    table_header: {
      content: options.cellContent,
      attrs: cellAttrs,
      tableRole: "header_cell",
      isolating: true,
      parseDOM: [
        { tag: "th", getAttrs: dom => getCellAttrs(dom, extraAttrs) },
      ],
      toDOM(node) {
        return ["th", setCellAttrs(node, extraAttrs), 0]
      },
    },
  }
}

export const TableCaption = Node.create({
  name: "tableCaption",
  content: "block+",
  tableRole: "caption",
  isolating: true,
  parseHTML() {
    return [{ tag: "tr" }]
  },

  renderHTML({ HTMLAttributes }) {
    return ["tr", HTMLAttributes, 0]
  },
})

export const TableFoot = Node.create({
  name: "tableFoot",
  content: "tableRow+",
  tableRole: "foot",
  isolating: true,
  parseHTML() {
    return [{ tag: "tfoot" }]
  },
  renderHTML({ HTMLAttributes }) {
    return ["tfoot", HTMLAttributes, 0]
  },
})

export const TableHead = Node.create({
  name: "tableHead",
  content: "tableRow+",
  tableRole: "head",
  isolating: true,
  parseHTML() {
    return [{ tag: "thead" }]
  },
  renderHTML({ HTMLAttributes }) {
    return ["thead", HTMLAttributes, 0]
  },
})

export const TableBody = Node.create({
  name: "tableBody",
  content: "tableRow+",
  tableRole: "body",
  isolating: true,
  parseHTML() {
    return [{ tag: "tbody" }]
  },
  renderHTML({ HTMLAttributes }) {
    return ["tbody", HTMLAttributes, 0]
  },
})

export const TableColgroup = Node.create({
  name: "tableColgroup",
  content: "tableCol+",
  tableRole: "colgroup",
  isolating: true,
  parseHTML() {
    return [{ tag: "colgroup" }]
  },
  renderHTML({ HTMLAttributes }) {
    return ["colgroup", HTMLAttributes, 0]
  },
})

export const TableCol = Node.create({
  name: "tableCol",
  tableRole: "col",
  isolating: true,
  atom: false,
  parseHTML() {
    return [{ tag: "col" }]
  },
  renderHTML({ HTMLAttributes }) {
    return ["col", HTMLAttributes]
  },
  extendNodeSchema(extension) {
    return {
      atom: false,
      leaf: false,
    }
  },
})
