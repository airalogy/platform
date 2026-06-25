import type { Node, ResolvedPos, Slice } from "@tiptap/pm/model"
import type { EditorState, Selection, Transaction } from "@tiptap/pm/state"
import type { Mappable } from "@tiptap/pm/transform"
import type { DecorationSet, EditorView } from "@tiptap/pm/view"
import { Plugin, SelectionRange } from "@tiptap/pm/state"
import { CellSelection as CellSelectionBase, type CellSelectionJSON } from "@tiptap/pm/tables"
// @ts-expect-error declare missing functions from the @tiptap/pm/tables module
import { cellAround, cellUnderMouse, domInCell, drawCellSelection, handleKeyDown, handlePaste, handleTripleClick, inSameTable, normalizeSelection, tableEditingKey } from "@tiptap/pm/tables"
import { fixTables } from "./fixtables"
import { TableMap } from "./tableMap"
import { getTableNode } from "./utils"

// Declare missing functions from the @tiptap/pm/tables module
declare module "@tiptap/pm/tables" {
  export const drawCellSelection: (state: EditorState) => DecorationSet
  export const handleTripleClick: (view: EditorView, event: MouseEvent) => boolean
  export const handleKeyDown: (view: EditorView, event: KeyboardEvent) => boolean
  export const normalizeSelection: (state: EditorState, tr?: Transaction, allowTableNodeSelection?: boolean) => Transaction | null
  export const domInCell: (view: EditorView, dom: Node) => Element | null
  export const cellUnderMouse: (view: EditorView, event: MouseEvent) => ResolvedPos | null
}
function tableEditing({
  allowTableNodeSelection = false,
} = {}) {
  return new Plugin({
    key: tableEditingKey,
    // This piece of state is used to remember when a mouse-drag
    // cell-selection is happening, so that it can continue even as
    // transactions (which might move its anchor cell) come in.
    state: {
      init() {
        return null
      },
      apply(tr, cur) {
        const set = tr.getMeta(tableEditingKey)
        if (set != null)
          return set === -1 ? null : set
        if (cur == null || !tr.docChanged)
          return cur
        const { deleted, pos } = tr.mapping.mapResult(cur)
        return deleted ? null : pos
      },
    },
    props: {
      decorations: drawCellSelection,
      handleDOMEvents: {
        mousedown: handleMouseDown,
      },
      createSelectionBetween(view) {
        return tableEditingKey.getState(view.state) != null ? view.state.selection : null
      },
      handleTripleClick,
      handleKeyDown,
      handlePaste,
    },
    appendTransaction(_, oldState, state) {
      return normalizeSelection(
        state,
        fixTables(state, oldState),
        allowTableNodeSelection,
      )
    },
  })
}

// Proxy class for CellSelection that maintains the same interface but allows us to customize the constructor
class CellSelection implements CellSelectionBase {
  _instance: CellSelectionBase
  constructor($anchorCell: ResolvedPos, $headCell: ResolvedPos = $anchorCell) {
    // Find the table node by traversing up until we find a node with tableRole="table"
    const tableInfo = getTableNode($anchorCell)
    if (!tableInfo) {
      throw new RangeError("CellSelection not in a table")
    }
    const { table, start: tableStart } = tableInfo
    const map = TableMap.get(table)
    const rect = map.rectBetween(
      $anchorCell.pos - tableStart,
      $headCell.pos - tableStart,
    )
    const doc = $anchorCell.node(0)
    const cells = map.cellsInRect(rect).filter(p => p !== $headCell.pos - tableStart)
    cells.unshift($headCell.pos - tableStart)

    const ranges = cells.map((pos) => {
      const cell = table.nodeAt(pos)
      if (!cell) {
        throw new RangeError(`No cell with offset ${pos} found`)
      }
      const from = tableStart + pos + 1
      return new SelectionRange(
        doc.resolve(from),
        doc.resolve(from + cell.content.size),
      )
    })

    const instance = new CellSelectionBase($anchorCell, $headCell)
    this._instance = instance
  }

  get $anchorCell() {
    return this._instance.$anchorCell
  }

  get $headCell() {
    return this._instance.$headCell
  }

  map(doc: Node, mapping: Mappable): CellSelectionBase | Selection {
    return this._instance.map(doc, mapping)
  }

  content(): Slice {
    return this._instance.content()
  }

  replace(tr: Transaction, content?: Slice): void {
    return this._instance.replace(tr, content)
  }

  replaceWith(tr: Transaction, node: Node): void {
    return this._instance.replaceWith(tr, node)
  }

  forEachCell(f: (node: Node, pos: number) => void): void {
    return this._instance.forEachCell(f)
  }

  isColSelection(): boolean {
    return this._instance.isColSelection()
  }

  isRowSelection(): boolean {
    return this._instance.isRowSelection()
  }

  eq(other: unknown): boolean {
    return this._instance.eq(other)
  }

  static colSelection($anchorCell: ResolvedPos, $headCell?: ResolvedPos): CellSelection {
    return new CellSelection($anchorCell, $headCell)
  }

  static rowSelection($anchorCell: ResolvedPos, $headCell?: ResolvedPos): CellSelection {
    return new CellSelection($anchorCell, $headCell)
  }

  toJSON(): CellSelectionJSON {
    return this._instance.toJSON()
  }

  static fromJSON(doc: Node, json: CellSelectionJSON): CellSelection {
    return new CellSelection(doc.resolve(json.anchor), doc.resolve(json.head))
  }

  getBookmark() {
    return this._instance.getBookmark()
  }

  get $anchor() {
    return this._instance.$anchor
  }

  get $head() {
    return this._instance.$head
  }

  get ranges() {
    return this._instance.ranges
  }

  get anchor() {
    return this._instance.anchor
  }

  get head() {
    return this._instance.head
  }

  get from() {
    return this._instance.from
  }

  get to() {
    return this._instance.to
  }

  get $from() {
    return this._instance.$from
  }

  get $to() {
    return this._instance.$to
  }

  get empty() {
    return this._instance.empty
  }

  get visible() {
    return this._instance.visible
  }
}
export function handleMouseDown(
  view: EditorView,
  startEvent: MouseEvent,
): void {
  if (startEvent.ctrlKey || startEvent.metaKey)
    return

  const startDOMCell = domInCell(view, startEvent.target as unknown as Node)
  let $anchor = null
  if (startEvent.shiftKey && view.state.selection instanceof CellSelection) {
    // Adding to an existing cell selection
    setCellSelection(view.state.selection.$anchorCell, startEvent)
    startEvent.preventDefault()
  }
  else {
    if (startEvent.shiftKey && startDOMCell) {
    // Adding to a selection that starts in another cell (causing a
    // cell selection to be created).
      const newAnchor = cellAround(view.state.selection.$anchor)
      if (newAnchor && cellUnderMouse(view, startEvent)?.pos !== newAnchor.pos) {
        $anchor = newAnchor
        setCellSelection(newAnchor, startEvent)
        startEvent.preventDefault()
      }
    }

    if (!$anchor && !startDOMCell) {
    // Not in a cell, let the default behavior happen.
      return
    }
  }

  // Create and dispatch a cell selection between the given anchor and
  // the position under the mouse.
  function setCellSelection($anchor: ResolvedPos, event: MouseEvent): void {
    let $head = cellUnderMouse(view, event)
    const starting = tableEditingKey.getState(view.state) == null
    if (!$head || !inSameTable($anchor, $head)) {
      if (starting)
        $head = $anchor
      else return
    }
    const selection = new CellSelection($anchor, $head)
    if (starting || !view.state.selection.eq(selection)) {
      const tr = view.state.tr.setSelection(selection)
      if (starting)
        tr.setMeta(tableEditingKey, $anchor.pos)
      view.dispatch(tr)
    }
  }

  // Stop listening to mouse motion events.
  function stop(): void {
    view.root.removeEventListener("mouseup", stop)
    view.root.removeEventListener("dragstart", stop)
    view.root.removeEventListener("mousemove", move)
    if (tableEditingKey.getState(view.state) != null)
      view.dispatch(view.state.tr.setMeta(tableEditingKey, -1))
  }

  function move(_event: Event): void {
    const event = _event as MouseEvent
    const anchor = tableEditingKey.getState(view.state)
    let $anchor
    if (anchor != null) {
      // Continuing an existing cross-cell selection
      $anchor = view.state.doc.resolve(anchor)
    }
    else if (domInCell(view, event.target as unknown as Node) !== startDOMCell) {
      // Moving out of the initial cell -- start a new cell selection
      $anchor = cellUnderMouse(view, startEvent)
      if (!$anchor)
        return stop()
    }
    if ($anchor)
      setCellSelection($anchor, event)
  }

  view.root.addEventListener("mouseup", stop)
  view.root.addEventListener("dragstart", stop)
  view.root.addEventListener("mousemove", move)
}
