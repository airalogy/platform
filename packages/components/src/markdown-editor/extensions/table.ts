import type { ExtensionRenderParams } from "."
import TableMenuBarItem from "@airalogy/components/markdown-editor/modules/table/create-table-popover-body.vue"
import TableView from "@airalogy/components/markdown-editor/modules/table/table-view.vue"
import { Table as TiptapTable } from "@tiptap/extension-table"
import TableCell from "@tiptap/extension-table-cell"
import TableHeader from "@tiptap/extension-table-header"
import TableRow from "@tiptap/extension-table-row"
import { TextSelection } from "@tiptap/pm/state"
import { tableEditing } from "@tiptap/pm/tables"
import { columnResizing } from "../modules/table/columnResizing"
import { fixTables } from "../modules/table/fixtables"
import { TableBody, TableCaption, TableCol, TableColgroup, TableFoot, TableHead } from "../modules/table/schema"
import { tableTab } from "../modules/table/tableTab"
import { createTable } from "../modules/table/utils"
import tableSerializer from "./markdown/table"

import { VueNodeViewRenderer } from "./tiptapView"
import "../modules/table/patch"

const Table = TiptapTable.extend({
  addOptions() {
    return {
      ...this.parent?.(),
      allowTableNodeSelection: true,
      slash: true,
      renderer({ editor, disabled }: ExtensionRenderParams) {
        return {
          component: TableMenuBarItem,
          componentProps: computed(() => ({
            editor,
            command: ({ range, rows, cols, withHeaderRow }: any) => {
              range
                ? editor
                  .chain()
                  .focus()
                  .deleteRange(range)
                  .insertTable({
                    rows,
                    cols,
                    withHeaderRow,
                  })
                  .run()
                : editor.commands.insertTable({
                  rows,
                  cols,
                  withHeaderRow,
                })
            },
            isActive: editor.isActive("table"),
            isDisabled: !editor.can().insertTable(),
            HTMLAttributes: {
              class: "tiptap-editor__table",
            },
            disabled,
          })),
        }
      },
    }
  },
  // addKeyboardShortcuts() {
  //   return {
  //     "Enter": ({ editor }) => {
  //     },

  //     "Shift-Enter": ({ editor }) => {
  //     },
  //   }
  // },
  content: "tableCaption? tableColgroup? tableHead? tableBody* tableFoot?",
  // renderHTML({ node, HTMLAttributes }) {
  //   const { colgroup, tableWidth, tableMinWidth } = createColGroup(
  //     node,
  //     this.options.cellMinWidth,
  //   )

  //   const table: DOMOutputSpec = [
  //     "table",
  //     mergeAttributes(this.options.HTMLAttributes, HTMLAttributes, {
  //       style: tableWidth
  //         ? `width: ${tableWidth}`
  //         : `min-width: ${tableMinWidth}`,
  //     }),
  //     colgroup,
  //     ["thead", 0],
  //     ["tbody", 0],
  //     ["tfoot", 0],
  //   ]

  //   return table
  // },
  addCommands() {
    return {
      ...this.parent?.(),
      insertTable:
        ({ rows = 3, cols = 3, withHeaderRow = true } = {}) => ({ tr, dispatch, editor }) => {
          const node = createTable(editor.schema, rows, cols, withHeaderRow)

          if (dispatch) {
            const offset = tr.selection.from + 1

            tr.replaceSelectionWith(node)
              .scrollIntoView()
              .setSelection(TextSelection.near(tr.doc.resolve(offset)))
          }

          return true
        },
      fixTables:
        () => ({ state, dispatch }) => {
          if (dispatch) {
            fixTables(state)
          }

          return true
        },
    }
  },
  addStorage() {
    return {
      markdown: {
        serialize: tableSerializer,
      },
    }
  },

  addExtensions() {
    return [TableRow, TableHeader, TableCell, TableCaption, TableHead, TableBody, TableFoot, TableColgroup, TableCol]
  },

  addNodeView() {
    return VueNodeViewRenderer(TableView)
  },

  addProseMirrorPlugins() {
    return [
      columnResizing({
        cellMinWidth: this.options.cellMinWidth || 25,
        defaultCellMinWidth: 100,
        handleWidth: 5,
        lastColumnResizable: true,
      }),
      tableEditing({
        allowTableNodeSelection: true,
      }),
      tableTab(),
    ]
  },

})

export default Table
